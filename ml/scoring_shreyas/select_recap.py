"""
Preview recap: pick 6-12 windows that are high-scoring AND spread across the day, then stitch
them into recap.mp4. This is only for watching/judging the scores; the real selection will live
in the backend.

Selection = Maximal Marginal Relevance (MMR), as recommended in SIG-28:
    pick the window with the best   lambda * score - (1 - lambda) * redundancy
where redundancy = how similar it is to the windows already picked. Similarity is CLIP cosine
similarity, faded by time apart, so the same desk at 9am and 3pm isn't treated as a repeat.
Extra rules: no event gets more than ~1/3 of the recap, no two picks within 10 s of each other
in the same video, a quiet day (fewer than 4 events) gets a 30 s recap instead of 60 s, and
windows below min_score are only used if needed to reach that 30 s minimum.
"""

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from pipeline import ffmpeg_exe, probe


def select_windows(rows, cfg):
    sc, time_scale = cfg["selection"], cfg["events"]["time_scale_minutes"]
    sizes = {}
    for r in rows:
        sizes[r["event"]] = sizes.get(r["event"], 0) + 1
    real_events = sum(1 for n in sizes.values() if n >= 2)
    n = sc["n_windows"] if real_events >= 4 else sc["n_windows_quiet_day"]
    n = min(n, len(rows))
    cap = max(1, math.ceil(n * sc["max_share_per_event"]))

    score = np.array([r["score"] for r in rows])
    emb = np.stack([r["embedding"] for r in rows])
    minutes = np.array([r["minute_of_day"] for r in rows])
    lam = sc["mmr_lambda"]

    n_min = min(sc["n_windows_quiet_day"], n)
    picked, per_event = [], {}
    while len(picked) < n:
        best, best_val = None, -np.inf
        for i, r in enumerate(rows):
            if i in picked or per_event.get(r["event"], 0) >= cap:
                continue
            # weak windows are only allowed while we still need them to reach the 30 s minimum
            if score[i] < sc.get("min_score", 0.0) and len(picked) >= n_min:
                continue
            if any(rows[j]["video"] == r["video"] and
                   abs(rows[j]["start_seconds"] - r["start_seconds"]) < sc["min_gap_seconds"]
                   for j in picked):
                continue
            redundancy = 0.0
            if picked:
                sim = emb[picked] @ emb[i]
                fade = np.exp(-np.abs(minutes[picked] - minutes[i]) / time_scale)
                redundancy = float(np.max(sim * fade))
            val = lam * score[i] - (1 - lam) * redundancy
            if val > best_val:
                best, best_val = i, val
        if best is None:
            if cap >= n:          # nothing left that's good enough and not too close to a pick
                break
            cap += 1              # event caps blocked everything: loosen them and retry
            continue
        picked.append(best)
        per_event[rows[best]["event"]] = per_event.get(rows[best]["event"], 0) + 1

    return sorted(picked, key=lambda i: (minutes[i], rows[i]["start_seconds"]))


def stitch(rows, picked, out_path):
    """Cuts each picked window (with its audio) and joins them into one mp4.
    Every piece is re-encoded to the same size/fps/codec so they can be joined without glitches."""
    if not picked:
        return None
    ff = ffmpeg_exe()
    portrait = sum(rows[i]["portrait"] for i in picked) > len(picked) / 2
    W, H = (720, 1280) if portrait else (1280, 720)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for k, i in enumerate(picked):
            r = rows[i]
            dur = r["end_seconds"] - r["start_seconds"]
            _, has_audio = probe(r["path"])
            part = Path(tmp) / f"part_{k:02d}.mp4"
            cmd = [ff, "-v", "error", "-y", "-ss", str(r["start_seconds"]), "-t", str(dur),
                   "-i", r["path"]]
            if not has_audio:      # add silence so every piece has an audio track
                cmd += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo"]
            cmd += ["-vf", vf, "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(part)]
            subprocess.run(cmd, check=True)
            parts.append(part)
        listing = Path(tmp) / "parts.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-c", "copy", str(out_path)], check=True)
    return out_path