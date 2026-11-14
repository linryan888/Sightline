"""
Cut longer phone videos into 5-second clips for the SightLine test set.

Record a few longer videos around your day (e.g. 1-2 minutes at each of 5-8 places),
put them in one folder, and run:

  python split_clips.py raw_videos clips

Each video becomes clips named <video>_000.mp4, <video>_005.mp4, ... (the number is the
start second), so file-name order = time order and clip_id stays unique.
Videos are processed in name order; name them so that order matches the order you filmed them
(e.g. 01_cafe.mp4, 02_walk.mp4, ...). Output has no audio.
"""

import argparse
import sys
from pathlib import Path

import cv2

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder of long videos")
    ap.add_argument("dst", help="output folder for 5-second clips")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--max-side", type=int, default=1280, help="downscale so the long side is at most this")
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    videos = sorted(p for p in src.iterdir() if p.suffix.lower() in VIDEO_EXTS) if src.is_dir() else []
    if not videos:
        sys.exit(f"No videos found in '{src}'.")
    dst.mkdir(parents=True, exist_ok=True)

    total = 0
    for v in videos:
        cap = cv2.VideoCapture(str(v))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        per = int(round(fps * args.seconds))
        writer, n, idx = None, 0, 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            h, w = fr.shape[:2]
            s = args.max_side / max(h, w)
            if s < 1:
                fr = cv2.resize(fr, (int(w * s) // 2 * 2, int(h * s) // 2 * 2))
            if n % per == 0:
                if writer:
                    writer.release()
                    total += 1
                start = int(round(n / fps))
                out = dst / f"{v.stem}_{start:03d}.mp4"
                writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                         (fr.shape[1], fr.shape[0]))
                idx += 1
            writer.write(fr)
            n += 1
        if writer:
            writer.release()
            # drop a tiny leftover piece (< 2 s) at the end of the video
            if n % per and n % per < 2 * fps:
                out.unlink(missing_ok=True)
                idx -= 1
            else:
                total += 1
        cap.release()
        print(f"{v.name}: {n / fps:.0f}s -> {idx} clips")
    print(f"\nDone: {total} clips in {dst}")


if __name__ == "__main__":
    main()
