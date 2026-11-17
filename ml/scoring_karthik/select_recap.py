"""
Step 5: pick 6-12 windows for a preview recap and stitch them into recap.mp4.

This is only so you can watch and judge your scores; the real selection will live in the backend.

Picking uses MMR (Maximal Marginal Relevance): repeatedly take the window with the best
    value = lambda * score  -  (1 - lambda) * redundancy
where redundancy = how similar it is to the windows already picked. Similarity is CLIP cosine
similarity, faded by how far apart the two windows are in time, so the same desk at 9am and 3pm
is not treated as a repeat. lambda = 1 means "just take the top scores", lower means "more varied".
"""

import math

import cv2
import numpy as np


def select_windows(rows, cfg):
    """Return the indexes (into rows) of the picked windows, in the order they happened."""
    sel = cfg["selection"]
    lam, time_scale = sel["mmr_lambda"], cfg["time_scale_minutes"]
    n = min(sel["n_windows"], len(rows))
    n_min = min(sel["min_windows"], n)
    gap = sel["min_gap_seconds"]

    score = np.array([r["score"] for r in rows])
    emb = np.stack([r["embedding"] for r in rows])
    minutes = np.array([r["minute_of_day"] for r in rows])

    picked = []
    while len(picked) < n:
        best, best_val = None, -math.inf
        for i, r in enumerate(rows):
            if i in picked:
                continue
            # weak windows are only allowed while we still need them to reach the minimum recap length
            if score[i] < sel["min_score"] and len(picked) >= n_min:
                continue
            # skip windows too close to an already-picked one in the same video
            if any(rows[j]["video"] == r["video"]
                   and abs(rows[j]["start_seconds"] - r["start_seconds"]) < gap for j in picked):
                continue
            redundancy = 0.0
            if picked:
                sim = emb[picked] @ emb[i]                                   # look-alike?
                fade = np.exp(-np.abs(minutes[picked] - minutes[i]) / time_scale)   # close in time?
                redundancy = float(np.max(sim * fade))
            value = lam * score[i] - (1 - lam) * redundancy
            if value > best_val:
                best, best_val = i, value
        if best is None:
            if len(picked) < n_min and gap > 0:
                gap = 0            # too strict to reach the minimum recap length: loosen the gap rule
                continue
            break
        picked.append(best)
    return sorted(picked, key=lambda i: (minutes[i], rows[i]["start_seconds"]))


def _letterbox(frame, width, height):
    """Fit a frame inside width x height without stretching it; fill the rest with black."""
    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y0, x0 = (height - new_h) // 2, (width - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = cv2.resize(frame, (new_w, new_h))
    return canvas


def stitch(rows, picked, out_path, out_fps=30.0):
    """Copy each picked window's frames, in order, into one mp4 (no audio).
    Every frame is fitted to the size of the first picked frame so differently shaped videos can be joined."""
    if not picked:
        return None
    first = rows[picked[0]]
    cap = cv2.VideoCapture(first["path"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(first["start_seconds"] * cap.get(cv2.CAP_PROP_FPS)))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Cannot read {first['path']}")
    height, width = frame.shape[:2]

    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (width, height))
    for i in picked:
        r = rows[i]
        cap = cv2.VideoCapture(r["path"])
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(r["start_seconds"] * src_fps))
        n_src = int((r["end_seconds"] - r["start_seconds"]) * src_fps)
        credit = 0.0
        for _ in range(n_src):
            ok, frame = cap.read()
            if not ok:
                break
            credit += out_fps / src_fps          # convert the video's frame rate to out_fps:
            while credit >= 1.0:                 # repeat or drop frames so the speed stays correct
                writer.write(_letterbox(frame, width, height))
                credit -= 1.0
        cap.release()
    writer.release()
    return out_path
