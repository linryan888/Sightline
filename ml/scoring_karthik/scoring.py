"""
Steps 3 and 4: turn raw measurements into ranks, then blend them into one score per window.

    score_day([video1, video2, ...], cfg)  -> one dict per window with every signal and the score
    score_video("a.mp4")                   -> [{start_seconds, end_seconds, score}, ...]   (backend format)

The three signals:
  clip     - CLIP prompt score: looks like a good moment vs a boring one
  novelty  - 1 minus cosine similarity to the day's average fingerprint: unlike the typical moment
  quality  - sharpness of the frames
Each is converted to a within-day percentile rank (0 to 1), then blended with the weights from config.yaml.
"""

import time
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.stats import rankdata

from signals import ClipScorer, sample_frames, sharpness
from windows import add_day_minutes, make_windows, start_clock, video_info

SIGNALS = ("clip", "novelty", "quality")
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


def load_config(path=None):
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Timer:
    """Adds up how long each stage takes, across all videos."""

    def __init__(self):
        self.seconds = {}

    def add(self, stage, start):
        self.seconds[stage] = self.seconds.get(stage, 0.0) + time.perf_counter() - start


def process_video(path, scorer, cfg, timer, log=print):
    """Raw measurements for every window of one video. Returns one dict per window."""
    fps, duration = video_info(path)
    windows = make_windows(duration, cfg["window_seconds"], cfg["min_window_seconds"])
    clock0 = start_clock(path)
    cap = cv2.VideoCapture(str(path))
    rows, skipped = [], 0
    for start, end in windows:
        t = time.perf_counter()
        frames = sample_frames(cap, fps, start, end, cfg["frames_per_window"], cfg["frame_long_side"])
        timer.add("read_frames", t)
        if not frames:                       # nothing could be read: don't invent a score for it
            skipped += 1
            continue
        t = time.perf_counter()
        quality = sharpness(frames)
        timer.add("quality", t)
        t = time.perf_counter()
        emb = scorer.embed(frames)
        clip_raw = scorer.prompt_score(emb)
        timer.add("clip", t)
        rows.append({
            "video": Path(path).name,
            "path": str(path),
            "start_seconds": start,
            "end_seconds": end,
            "clock": (clock0 + start) if clock0 is not None else None,
            "raw_clip": clip_raw,
            "raw_quality": quality,
            "embedding": emb,
        })
    cap.release()
    if skipped:
        log(f"  skipped {skipped} unreadable window(s) in {Path(path).name}")
    return rows


def add_novelty(rows):
    """raw_novelty = 1 - cosine(window fingerprint, the day's average fingerprint).
    A window that looks like everything else is near 0; an unusual one is higher."""
    emb = np.stack([r["embedding"] for r in rows])
    centroid = emb.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
    for r, e in zip(rows, emb):
        r["raw_novelty"] = float(1.0 - e @ centroid)


def percentile(values):
    """Within-day percentile rank: sort, number the rows 1..N, divide by N.
    Lowest window gets 1/N, highest gets 1.0. Ties share their average position."""
    x = np.asarray(values, dtype=float)
    return rankdata(x, method="average") / len(x)


def combine(rows, cfg):
    """Rank every signal across the day, then take the weighted sum.
    A signal that is identical for every window carries no information, so it is dropped and
    the other weights are scaled up to still add to 1. Returns the weights actually used."""
    weights = {s: float(cfg["weights"][s]) for s in SIGNALS}
    for s in SIGNALS:
        raw = np.array([r[f"raw_{s}"] for r in rows], dtype=float)
        if np.ptp(raw) == 0:
            weights[s] = 0.0
            ranks = np.zeros(len(rows))
        else:
            ranks = percentile(raw)
        for r, v in zip(rows, ranks):
            r[s] = float(v)
    total = sum(weights.values()) or 1.0
    for r in rows:
        r["score"] = round(sum(weights[s] * r[s] for s in SIGNALS) / total, 4)
    return {s: round(w / total, 3) for s, w in weights.items()}


def score_day(video_paths, cfg=None, scorer=None, timer=None, log=print, random_init=False):
    """Score every window of a day's videos. Ranking happens across ALL of them together,
    so scores are comparable within the day."""
    cfg = cfg or load_config()
    timer = timer or Timer()
    if scorer is None:
        t = time.perf_counter()
        scorer = ClipScorer(cfg["clip"], random_init=random_init)
        timer.add("load_model", t)
    rows = []
    for i, p in enumerate(video_paths, 1):
        log(f"[{i}/{len(video_paths)}] {Path(p).name}")
        rows += process_video(p, scorer, cfg, timer, log=log)
    if not rows:
        return rows, {}
    t = time.perf_counter()
    add_day_minutes(rows)
    add_novelty(rows)
    weights = combine(rows, cfg)
    timer.add("rank_and_blend", t)
    return rows, weights


def score_video(video_path, config_path=None):
    """What the backend would call: one video in, one score per window out.
    Scores are ranked within this one video; for a whole day pass every video to score_day."""
    rows, _ = score_day([Path(video_path)], load_config(config_path), log=lambda *_: None)
    return [{"start_seconds": r["start_seconds"], "end_seconds": r["end_seconds"],
             "score": r["score"]} for r in rows]
