"""
SightLine scoring pipeline (SIG-64) - Shreyas

Gives every 5-second window of a day's video a score from 0 to 1 for how much it
belongs in a 60-second recap.

    score_video("20261028_093000.mp4")      -> [{start_seconds, end_seconds, score}, ...]
    score_day(["a.mp4", "b.mp4", ...], cfg) -> one dict per window, with every signal

Steps for each video:
  1. split into 5 s windows (same rule as the backend: last window stops at the end)
  2. decode 2 frames/second + the audio track (ffmpeg, bundled with imageio-ffmpeg)
  3. signals per window:
       clip    - CLIP: how much more it looks like the "moment" prompts than the "boring" ones
       people  - YOLO11 + ByteTrack: number of *different* people (track IDs), so one person
                 seen in 10 frames counts once
       speech  - Silero VAD: fraction of the window with someone talking
       quality - sharpness (variance of the Laplacian): blurry/dark footage is low
Then for the whole day:
  4. turn each signal into a within-day percentile (0-1); "nobody there" / "no speech" stay 0
  5. score = weighted sum of the percentiles (weights in config.yaml)
  6. group windows into events with HDBSCAN on [CLIP embedding, time of day]
"""

import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import rankdata

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")
SIGNALS = ("clip", "people", "speech", "quality")
ZERO_MEANS_NOTHING = ("people", "speech")   # 0 people / 0 speech must stay 0 after normalizing
logging.getLogger("imageio_ffmpeg").setLevel(logging.ERROR)  # hides a harmless "frame size" notice


# ----------------------------------------------------------------------------- setup

def load_config(path=None):
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_videos(path):
    """A folder -> its videos sorted by name (= by start time if named YYYYMMDD_HHMMSS)."""
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS)


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Timer:
    """Adds up how long each stage takes, across all videos."""
    def __init__(self):
        self.seconds = {}

    def add(self, stage, start):
        self.seconds[stage] = self.seconds.get(stage, 0.0) + time.perf_counter() - start


# ----------------------------------------------------------------------------- video + windows

def probe(path):
    """Duration in seconds and whether the file has audio, read from ffmpeg's header printout."""
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, errors="ignore").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    if not m:
        raise RuntimeError(f"ffmpeg can't read {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s), "Audio:" in out


def make_windows(duration, size):
    """[(0,5), (5,10), ...]; the last window is cut at the end of the video."""
    starts = np.arange(0.0, duration, size)
    return [(float(s), float(min(s + size, duration))) for s in starts if duration - s > 1e-3]


def start_time_of(path):
    """Clock time the video started, from a YYYYMMDD_HHMMSS file name (None if not named that way)."""
    m = re.search(r"(\d{8})_(\d{6})", Path(path).stem)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def read_frames(path, fps, long_side):
    """Yields (time_in_seconds, RGB frame) at `fps` frames per second, downscaled.
    ffmpeg does the decoding/scaling, which is much faster than reading every frame in Python."""
    import imageio_ffmpeg
    scale = (f"scale='if(gt(iw,ih),{long_side},-2)':'if(gt(iw,ih),-2,{long_side})'")
    gen = imageio_ffmpeg.read_frames(str(path), output_params=["-vf", f"fps={fps},{scale}"])
    meta = next(gen)
    w, h = meta["size"]
    for i, raw in enumerate(gen):
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        yield (i + 0.5) / fps, frame        # the fps filter samples the middle of each 1/fps slot


def read_audio(path, has_audio, sr=16000):
    """Mono 16 kHz float audio (what Silero VAD expects). Silence if the file has no audio."""
    if not has_audio:
        return np.zeros(0, dtype=np.float32)
    raw = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                          "-ar", str(sr), "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


# ----------------------------------------------------------------------------- models

class Models:
    """Loads each model once and reuses it for every video."""

    def __init__(self, cfg):
        import open_clip
        import torch
        from silero_vad import load_silero_vad

        self.cfg = cfg
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        c = cfg["clip"]
        self.clip, _, self.preprocess = open_clip.create_model_and_transforms(
            c["model"], pretrained=c["pretrained"] or None, device=self.device)
        self.clip.eval()
        tok = open_clip.get_tokenizer(c["model"])
        with torch.no_grad():
            def enc(texts):
                e = self.clip.encode_text(tok(texts).to(self.device)).float()
                return torch.nn.functional.normalize(e, dim=-1).cpu().numpy()
            self.pos = enc(c["positive_prompts"])
            self.neg = enc(c["negative_prompts"])
        self.vad = load_silero_vad()

    def new_tracker(self):
        """A fresh YOLO model per video, so track IDs restart at each video."""
        from ultralytics import YOLO
        return YOLO(self.cfg["people"]["model"])

    def embed(self, images):
        """CLIP image embeddings, unit length."""
        from PIL import Image
        torch = self.torch
        out = []
        with torch.no_grad():
            for i in range(0, len(images), 32):
                x = torch.stack([self.preprocess(Image.fromarray(im)) for im in images[i:i + 32]])
                e = self.clip.encode_image(x.to(self.device)).float()
                out.append(torch.nn.functional.normalize(e, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.pos.shape[1]), np.float32)


# ----------------------------------------------------------------------------- per-video signals

def sharpness(frame):
    """Variance of the Laplacian: high for sharp, detailed frames; low for blur and darkness."""
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def speech_fraction(audio, vad, windows, threshold, sr=16000):
    """Share of each window covered by speech segments from Silero VAD."""
    if len(audio) < sr:  # under a second of audio -> no speech
        return [0.0] * len(windows)
    import torch
    from silero_vad import get_speech_timestamps
    segs = get_speech_timestamps(torch.from_numpy(audio.copy()), vad, sampling_rate=sr,
                                 threshold=threshold, return_seconds=True)
    out = []
    for s, e in windows:
        talk = sum(max(0.0, min(e, g["end"]) - max(s, g["start"])) for g in segs)
        out.append(talk / (e - s))
    return out


def process_video(path, models, cfg, timer):
    """All raw signals for one video. Returns one dict per window."""
    pc = cfg["people"]
    size, fps = cfg["window_seconds"], cfg["sample_fps"]
    duration, has_audio = probe(path)
    windows = make_windows(duration, size)
    t0_clock = start_time_of(path)

    # --- frames: YOLO tracking on every sampled frame, keep a few per window for CLIP
    t = time.perf_counter()
    tracker = models.new_tracker()
    per_window = [{"tracks": {}, "sharp": [], "clip_frames": []} for _ in windows]
    k = cfg["clip_frames_per_window"]
    yolo_time = 0.0
    portrait = False
    for ts, frame in read_frames(path, fps, cfg["frame_long_side"]):
        portrait = frame.shape[0] > frame.shape[1]
        w = min(int(ts // size), len(windows) - 1)
        win = per_window[w]
        y0 = time.perf_counter()
        res = tracker.track(frame[:, :, ::-1], persist=True, tracker=pc["tracker"], classes=[0],
                            conf=pc["conf"], verbose=False)[0]   # YOLO wants BGR; class 0 = person
        yolo_time += time.perf_counter() - y0
        if res.boxes is not None and res.boxes.id is not None:
            for tid in res.boxes.id.int().tolist():
                win["tracks"][tid] = win["tracks"].get(tid, 0) + 1
        win["sharp"].append(sharpness(frame))
        win["clip_frames"].append(frame)
    timer.add("decode_frames", t)
    timer.seconds["decode_frames"] -= yolo_time
    timer.seconds["people_yolo"] = timer.seconds.get("people_yolo", 0.0) + yolo_time

    # --- CLIP: k evenly spaced frames per window -> one averaged embedding per window
    t = time.perf_counter()
    chosen, owner = [], []
    for i, win in enumerate(per_window):
        frames = win.pop("clip_frames")
        if frames:
            idx = np.linspace(0, len(frames) - 1, min(k, len(frames))).round().astype(int)
            chosen += [frames[j] for j in idx]
            owner += [i] * len(idx)
    emb_frames = models.embed(chosen)
    owner = np.array(owner)
    dim = models.pos.shape[1]
    emb = np.zeros((len(windows), dim), np.float32)
    clip_raw = np.zeros(len(windows))
    for i in range(len(windows)):
        e = emb_frames[owner == i]
        if len(e) == 0:
            continue
        # how much closer each frame is to its best "moment" prompt than its best "boring" prompt
        clip_raw[i] = float(np.mean((e @ models.pos.T).max(1) - (e @ models.neg.T).max(1)))
        m = e.mean(0)
        emb[i] = m / (np.linalg.norm(m) + 1e-8)
    timer.add("clip", t)

    # --- speech
    t = time.perf_counter()
    audio = read_audio(path, has_audio)
    speech = speech_fraction(audio, models.vad, windows, cfg["speech"]["threshold"])
    timer.add("speech_vad", t)

    rows = []
    for i, (s, e) in enumerate(windows):
        win = per_window[i]
        people = sum(1 for n in win["tracks"].values() if n >= pc["min_track_frames"])
        rows.append({
            "video": Path(path).name,
            "start_seconds": round(s, 3),
            "end_seconds": round(e, 3),
            "clock": (t0_clock.timestamp() + s) if t0_clock else None,
            "raw_clip": clip_raw[i],
            "raw_people": min(people, pc["max_count"]),
            "raw_speech": speech[i],
            "raw_quality": float(np.log1p(np.median(win["sharp"]))) if win["sharp"] else 0.0,
            "embedding": emb[i],
            "path": str(path),
            "portrait": portrait,
        })
    return rows


# ----------------------------------------------------------------------------- whole day

def percentile(x, zero_means_nothing):
    """Within-day percentile rank in (0, 1]. Ties share a rank.
    For people/speech, windows with nothing detected stay at exactly 0."""
    x = np.asarray(x, dtype=float)
    p = rankdata(x, method="average") / len(x)
    if zero_means_nothing:
        p[x <= 0] = 0.0
    return p


def combine(rows, cfg):
    """Percentile-normalize every signal across the day, then take the weighted sum.
    A signal that's identical for every window (e.g. no audio at all) is dropped and the
    other weights are scaled up so they still add to 1."""
    weights = {s: float(cfg["weights"][s]) for s in SIGNALS}
    used = {}
    for s in SIGNALS:
        raw = np.array([r[f"raw_{s}"] for r in rows], dtype=float)
        if np.ptp(raw) == 0:
            weights[s] = 0.0
            pct = np.zeros(len(rows))
        else:
            pct = percentile(raw, s in ZERO_MEANS_NOTHING)
        for r, v in zip(rows, pct):
            r[s] = float(v)
        used[s] = weights[s]
    total = sum(weights.values()) or 1.0
    for r in rows:
        r["score"] = round(sum(weights[s] * r[s] for s in SIGNALS) / total, 4)
    return {s: round(w / total, 3) for s, w in used.items()}


def day_minutes(rows):
    """Minutes since the first window of the day. Uses clock time from the file names when every
    video has one; otherwise treats the videos as back to back in name order."""
    if all(r["clock"] is not None for r in rows):
        t = np.array([r["clock"] for r in rows])
        return (t - t.min()) / 60.0
    out, offset, last_video, last_end = [], 0.0, None, 0.0
    for r in rows:
        if r["video"] != last_video:
            offset += last_end
            last_video = r["video"]
        out.append((offset + r["start_seconds"]) / 60.0)
        last_end = r["end_seconds"]
    return np.array(out)


def group_events(rows, cfg):
    """HDBSCAN on [CLIP embedding, minutes / time_scale]. Adding time means two windows that look
    the same but are hours apart land in different events. Windows that fit no event (-1) each
    become their own one-window event."""
    from sklearn.cluster import HDBSCAN
    ec = cfg["events"]
    minutes = day_minutes(rows)
    for r, m in zip(rows, minutes):
        r["minute_of_day"] = round(float(m), 2)
    if len(rows) < max(2, ec["min_event_windows"]):
        labels = np.arange(len(rows))
    else:
        X = np.hstack([np.stack([r["embedding"] for r in rows]),
                       (minutes / ec["time_scale_minutes"])[:, None]])
        labels = HDBSCAN(min_cluster_size=ec["min_event_windows"], min_samples=1).fit_predict(X)
    next_id = int(labels.max()) + 1 if len(labels) else 0
    for r, lab in zip(rows, labels):
        if lab == -1:
            lab, next_id = next_id, next_id + 1
        r["event"] = int(lab)


def score_day(video_paths, cfg=None, models=None, timer=None, log=print):
    """Scores every window of a day's videos. Normalization happens across all of them."""
    cfg = cfg or load_config()
    timer = timer or Timer()
    t = time.perf_counter()
    models = models or Models(cfg)
    timer.add("load_models", t)
    rows = []
    for i, p in enumerate(video_paths, 1):
        log(f"[{i}/{len(video_paths)}] {Path(p).name}")
        rows += process_video(p, models, cfg, timer)
    if not rows:
        return rows, {}
    t = time.perf_counter()
    weights = combine(rows, cfg)
    group_events(rows, cfg)
    timer.add("combine_and_events", t)
    return rows, weights


def score_video(video_path, config_path=None):
    """What the backend calls: one video in, one score per 5 s window out (normalized within that
    video). For a full day, pass every video to score_day instead so scores are comparable."""
    rows, _ = score_day([Path(video_path)], load_config(config_path), log=lambda *_: None)
    return [{"start_seconds": r["start_seconds"], "end_seconds": r["end_seconds"],
             "score": r["score"]} for r in rows]