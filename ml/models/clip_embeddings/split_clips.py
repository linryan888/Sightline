"""Cut a long video into 5-second clips using OpenCV (no ffmpeg needed).

Example:
    python split_clips.py --video day.mp4 --out clips --prefix day1
Writes clips/day1_0000.mp4, clips/day1_0001.mp4, ... Any leftover piece shorter
than a full clip is dropped.
"""
import argparse
from pathlib import Path

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="clips")
    ap.add_argument("--prefix", default="clip")
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    per_clip = round(fps * args.seconds)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n_clips, frames_in_clip, writer = 0, 0, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if writer is None:
            path = out / f"{args.prefix}_{n_clips:04d}.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            frames_in_clip = 0
        writer.write(frame)
        frames_in_clip += 1
        if frames_in_clip == per_clip:
            writer.release()
            writer = None
            n_clips += 1
    if writer is not None:
        writer.release()
        (out / f"{args.prefix}_{n_clips:04d}.mp4").unlink(missing_ok=True)
    cap.release()
    print(f"wrote {n_clips} clips of {args.seconds}s to {out}/")


if __name__ == "__main__":
    main()
