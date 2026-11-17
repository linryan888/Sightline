"""
Step 1: find the videos, cut each into 5-second windows, and work out when each one started.

A "window" is just a pair of numbers (start_seconds, end_seconds). We never write the
pieces to disk; later steps read the frames that fall inside each range.

The rules match the backend splitter (backend/windows.py): window i starts at i * size
(rounded to 3 decimals, so tiny errors don't pile up) and the last window stops at the
end of the video.
"""

import re
from datetime import datetime
from pathlib import Path

import cv2

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def list_videos(path):
    """A single video file, or every video in a folder sorted by name."""
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS)


def video_info(path):
    """Return (fps, duration_in_seconds), read from the file's header."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if not fps or fps <= 0 or frames <= 0:
        raise RuntimeError(f"Video has no readable length: {path}")
    return fps, frames / fps


def make_windows(duration, size=5.0, min_length=1.0):
    """[(0, 5), (5, 10), ...]. The last window is cut at the end of the video.
    A leftover tail shorter than min_length seconds is dropped (almost no content to score)."""
    if size <= 0:
        raise ValueError("window size must be positive")
    windows = []
    i = 0
    while True:
        start = round(i * size, 3)        # i * size, not "add 5 over and over", avoids float drift
        if start >= duration:
            break
        end = round(min(start + size, duration), 3)
        if end - start >= min_length:
            windows.append((start, end))
        i += 1
    return windows


def start_clock(path):
    """Clock time (seconds since 1970) the video started, read from a YYYYMMDD_HHMMSS file name.
    Returns None if the file isn't named that way."""
    m = re.search(r"(\d{8})_(\d{6})", Path(path).stem)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    except ValueError:
        return None


def add_day_minutes(rows):
    """Give every window row a 'minute_of_day': minutes since the first window of the day.

    If every video has a clock time in its file name, use it (so a desk at 9am and the same
    desk at 3pm are 6 hours apart). Otherwise treat the videos as back to back, in name order.
    Rows must be grouped by video, in order."""
    if rows and all(r["clock"] is not None for r in rows):
        first = min(r["clock"] for r in rows)
        for r in rows:
            r["minute_of_day"] = round((r["clock"] - first) / 60.0, 2)
        return
    offset, last_video, last_end = 0.0, None, 0.0
    for r in rows:
        if r["video"] != last_video:
            offset += last_end          # start of a new video = where the previous one ended
            last_video = r["video"]
        r["minute_of_day"] = round((offset + r["start_seconds"]) / 60.0, 2)
        last_end = r["end_seconds"]
