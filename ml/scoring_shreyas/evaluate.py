"""
Accuracy against the filmer's ground truth (SIG-62).

ground-truth log CSV  - one row per video:  file, ..., "would want in my recap" (1-5)
top-10 moments CSV    - one row per moment: file, time within the video (seconds, m:ss or h:mm:ss)

Column names are matched loosely (any header containing "file"; "recap" or "rating"; "time"),
so the spreadsheet can be exported as-is.

  Spearman  - rank correlation between each window's score and the rating of the video it's in
              (also reported per video: the video's mean window score vs. its rating)
  Recall    - how many of the 10 moments fall inside (or within a few seconds of) a picked window
"""

import csv
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _col(row, *words):
    for key in row:
        if key and any(w in key.lower() for w in words):
            return key
    raise KeyError(f"no column containing {words} in {list(row)}")


def _key(name):
    return Path(str(name).strip()).stem.lower()


def _seconds(text):
    parts = [float(p) for p in str(text).strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def load_ratings(path):
    rows = _read(path)
    fcol, rcol = _col(rows[0], "file"), _col(rows[0], "recap", "rating")
    out = {}
    for r in rows:
        try:
            out[_key(r[fcol])] = float(r[rcol])
        except (TypeError, ValueError):
            continue
    return out


def load_moments(path):
    rows = _read(path)
    fcol, tcol = _col(rows[0], "file"), _col(rows[0], "time", "sec")
    return [(_key(r[fcol]), _seconds(r[tcol])) for r in rows if r[fcol] and r[tcol]]


def spearman(rows, ratings):
    pairs = [(r["score"], ratings[_key(r["video"])]) for r in rows if _key(r["video"]) in ratings]
    out = {"windows_rated": len(pairs), "spearman_windows": None, "spearman_videos": None}
    if len(pairs) >= 3:
        s, y = zip(*pairs)
        out["spearman_windows"] = round(float(spearmanr(s, y).statistic), 3)
    per_video = {}
    for r in rows:
        if _key(r["video"]) in ratings:
            per_video.setdefault(_key(r["video"]), []).append(r["score"])
    if len(per_video) >= 3:
        vids = sorted(per_video)
        out["spearman_videos"] = round(float(spearmanr(
            [np.mean(per_video[v]) for v in vids], [ratings[v] for v in vids]).statistic), 3)
    return out


def recall(rows, picked, moments, tolerance):
    found = []
    for video, t in moments:
        hit = any(_key(rows[i]["video"]) == video and
                  rows[i]["start_seconds"] - tolerance <= t <= rows[i]["end_seconds"] + tolerance
                  for i in picked)
        found.append(hit)
    return {"moments": len(moments), "found": int(sum(found)),
            "recall": round(sum(found) / len(moments), 3) if moments else None,
            "missed": [f"{v} @ {t:.0f}s" for (v, t), h in zip(moments, found) if not h]}