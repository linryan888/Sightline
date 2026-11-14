"""
Step 6: how well do our scores match a human's opinion?

ratings.csv  - columns: video, rating (1-5 "would want in my recap"), and optionally start_seconds.
               With start_seconds the rating belongs to that one window; without it, to the whole video.
               Blank ratings are ignored, so you can fill in the template run.py writes.
top10.csv    - columns: video, time_seconds (a number, or m:ss, or h:mm:ss) for each of the top 10 moments.

Spearman  - rank correlation between our window scores and the ratings (1 = same order, 0 = unrelated,
            -1 = opposite order).
Recall    - how many of the top-10 moments fall inside (or within a couple of seconds of) a picked window.
"""

import csv
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _key(name):
    """File names are compared without folder, extension or capitals: 'A/IMG_1.MOV' == 'img_1'."""
    return Path(str(name).strip()).stem.lower()


def _seconds(text):
    """'75', '1:15' and '0:01:15' all mean 75 seconds."""
    total = 0.0
    for part in str(text).strip().split(":"):
        total = total * 60 + float(part)
    return total


def load_ratings(path):
    """Returns {(video, start_seconds or None): rating}."""
    out = {}
    for r in _read(path):
        if not (r.get("rating") or "").strip():
            continue
        start = (r.get("start_seconds") or "").strip()
        out[(_key(r["video"]), float(start) if start else None)] = float(r["rating"])
    return out


def load_moments(path):
    """Returns [(video, seconds), ...]."""
    return [(_key(r["video"]), _seconds(r["time_seconds"]))
            for r in _read(path) if (r.get("video") or "").strip() and (r.get("time_seconds") or "").strip()]


def spearman(rows, ratings):
    """Rank correlation between each rated window's score and its rating."""
    scores, truth = [], []
    for r in rows:
        v = _key(r["video"])
        rating = ratings.get((v, float(r["start_seconds"])), ratings.get((v, None)))
        if rating is not None:
            scores.append(r["score"])
            truth.append(rating)
    result = {"windows_rated": len(scores), "spearman": None}
    if len(scores) >= 3 and len(set(truth)) > 1 and len(set(scores)) > 1:
        result["spearman"] = round(float(spearmanr(scores, truth).statistic), 3)
    return result


def recall(rows, picked, moments, tolerance):
    """How many of the filmer's top moments are inside (or near) a picked window."""
    found = []
    for video, t in moments:
        found.append(any(
            _key(rows[i]["video"]) == video
            and rows[i]["start_seconds"] - tolerance <= t <= rows[i]["end_seconds"] + tolerance
            for i in picked))
    return {"moments": len(moments), "found": int(sum(found)),
            "missed": [f"{v} @ {t:.0f}s" for (v, t), ok in zip(moments, found) if not ok]}


def write_template(rows, path):
    """A blank rating sheet with one row per window. Fill in the rating column (1-5) and pass it back with --ratings."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["video", "start_seconds", "end_seconds", "rating"])
        for r in rows:
            w.writerow([r["video"], r["start_seconds"], r["end_seconds"], ""])
