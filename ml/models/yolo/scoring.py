"""
YOLO object-based clip scoring (ML Build #3, SIG-24).

Runs a pretrained YOLO model with built-in tracking (ByteTrack) on every clip in
CLIPS, turns the detections into per-clip features, and combines them into a
0-1 score. Results are written to yolo_scores_<model>.csv, one row per clip,
keyed by clip_id and sorted from highest to lowest score.

Pipeline:
  1. run_tracking       - sample frames per second and track objects
  2. clip_features      - max/avg people, distinct object classes, avg confidence
  3. activity_features  - how many tracked objects enter, leave, or move
  4. add_scores         - weighted sum of the capped features -> score in [0, 1]

Usage
    python scoring.py
Change MODEL / DEVICE below to compare models or CPU vs GPU.
"""


import csv
import numpy as np
import os
import time
import cv2
from ultralytics import YOLO

CLIPS = "clips"                
MODEL = "yolov8n.pt"           
DEVICE = "cpu"             
TRACKER = "bytetrack.yaml"   

# --- feature settings ---
TARGET_FPS = 10     # frames per second to sample from each clip
CONF = 0.4          # min confidence for a detection to count as a person / class
MIN_LEN = 3         # tracks seen in fewer frames than this are ignored as noise
MOVE_FRAC = 0.05    # a track "moved" if it traveled more than 5% of the frame diagonal
EDGE = 2            # tracks starting/ending within this many frames of the clip start/end don't count as enter/leave
BORDER = 0.05       # a track only "enters"/"leaves" if its box touches this outer 5% of the frame
CLASS_FRAC = 0.10   # a class only counts if it shows up in at least 10% of frames (and at least MIN_LEN frames)


WEIGHTS = {
    "activity": 0.45,
    "avg_people": 0.25,
    "distinct_classes": 0.20,
    "avg_conf": 0.10,
}

# fixed caps for scoring
CAPS = {
    "activity": 25,          
    "avg_people": 5.0,
    "distinct_classes": 4,
    "avg_conf": 1.0,
}

# Task 1
def run_tracking(model, path):
    """Track objects in one clip.

    Returns (frames, W, H, seconds): a list with one dict per sampled frame
    (class, confidence, xywh boxes, track ids), the frame size, and how long
    tracking took.
    """
    # pick a stride so we sample about TARGET_FPS frames per second, whatever the clip's fps
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    s = round(fps / TARGET_FPS)
    if s < 1:
        s = 1

    frames = []
    W = 0
    H = 0
    start = time.perf_counter()
    for f in model.track(source=path, imgsz=1280, vid_stride=s, tracker=TRACKER, device=DEVICE, stream=True, verbose=False):
        H, W = f.orig_shape
        boxes = f.boxes

        frame = {}
        frame["class"] = boxes.cls.int().tolist()
        frame["confidence"] = boxes.conf.tolist()
        frame["xywh"] = boxes.xywh.tolist()     
        if boxes.id is None:                  
            frame["ids"] = None
        else:
            frame["ids"] = boxes.id.int().tolist()
        frames.append(frame)
    seconds = time.perf_counter() - start

    return frames, W, H, seconds


# Task 2
def clip_features(frames, names):
    """Per-clip detection features: people counts, distinct classes, avg confidence.

    names maps a class index to its COCO name (model.names).
    """
    people_counts = []
    class_frames = {}  
    confs = []

    for f in frames:
        people = 0
        seen_this_frame = []
        for i in range(len(f["class"])):
            c = f["class"][i]
            conf = f["confidence"][i]
            confs.append(conf)
            if conf >= CONF:
                if c not in seen_this_frame:
                    seen_this_frame.append(c)
                if c == 0:      # class 0 is person in COCO
                    people += 1
        for c in seen_this_frame:
            if c not in class_frames:
                class_frames[c] = 0
            class_frames[c] += 1
        people_counts.append(people)

    # drop classes that only flicker in for a frame
    min_frames = max(MIN_LEN, CLASS_FRAC * len(frames))
    class_names = []
    dropped_names = []
    for c in class_frames:
        if class_frames[c] >= min_frames:
            class_names.append(names[c])
        else:
            dropped_names.append(names[c])
    class_names.sort()
    dropped_names.sort()

    if len(confs) > 0:
        avg_conf = sum(confs) / len(confs)
    else:
        avg_conf = 0.0

    features = {}
    if len(people_counts) > 0:
        features["max_people"] = max(people_counts)
        features["avg_people"] = round(sum(people_counts) / len(people_counts), 3)
    else:
        features["max_people"] = 0
        features["avg_people"] = 0.0
    features["distinct_classes"] = len(class_names)
    features["classes"] = " ".join(class_names)
    features["dropped_classes"] = " ".join(dropped_names)  
    features["avg_conf"] = round(avg_conf, 3)
    return features


# Task 3
def at_border(box, W, H):
    x, y, w, h = box
    mx = BORDER * W
    my = BORDER * H
    return x - w / 2 < mx or x + w / 2 > W - mx or y - h / 2 < my or y + h / 2 > H - my


def activity_features(frames, W, H):
    n = len(frames)
    diag = (W ** 2 + H ** 2) ** 0.5

    tracks = {}
    for i in range(n):
        frame = frames[i]
        if frame["ids"] is None:
            continue
        for j in range(len(frame["ids"])):
            tid = frame["ids"][j]
            box = frame["xywh"][j]
            if tid not in tracks:
                tracks[tid] = []
            tracks[tid].append((i, box[0], box[1], box))

    entered = 0
    left = 0
    moved = 0
    for tid in tracks:
        points = tracks[tid]
        if len(points) < MIN_LEN:
            continue

        first = points[0]
        last = points[-1]

        # a new ID in the middle of the frame is usually the tracker losing someone
        # in a crowd, not a real entrance, so only count it at the frame border
        if first[0] > EDGE and at_border(first[3], W, H):
            entered += 1
        if last[0] < n - 1 - EDGE and at_border(last[3], W, H):
            left += 1

        dx = last[1] - first[1]
        dy = last[2] - first[2]
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if diag > 0 and dist / diag > MOVE_FRAC:
            moved += 1

    features = {}
    features["entered"] = entered
    features["left"] = left
    features["moved"] = moved
    features["activity"] = entered + left + moved
    features["raw_track_ids"] = len(tracks)     # includes ID switches, useful for spotting tracker churn
    return features


# Task 4
def add_scores(rows):
    """Add a 0-1 "score" to each row: each feature is scaled to 0-1 by its cap, then weighted."""
    for row in rows:
        score = 0.0
        for name in WEIGHTS:
            norm = min(row[name] / CAPS[name], 1.0)
            score += WEIGHTS[name] * norm
        row["score"] = round(score, 4)

def get_score(row):
    return row["score"]

def main():
    model = YOLO(MODEL)
    model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=DEVICE, verbose=False)

    clip_files = []
    for f in os.listdir(CLIPS):
        if f.lower().endswith(".mp4") or f.lower().endswith(".mov"):
            clip_files.append(f)
    clip_files.sort()

    print(len(clip_files), "clips")
    print(clip_files)

    rows = []
    for f in clip_files:
        path = os.path.join(CLIPS, f)
        frames, W, H, seconds = run_tracking(model, path)
        print(f, len(frames), "frames", round(seconds, 2), "s")
        clip = clip_features(frames, model.names)
        print(f, clip)
        act = activity_features(frames, W, H)
        print(f, act)

        row = {}
        row["clip_id"] = f
        for key in clip:
            row[key] = clip[key]
        for key in act:
            row[key] = act[key]
        row["frames"] = len(frames)
        row["seconds"] = round(seconds, 3)

        rows.append(row)
        print(f, "done")


    add_scores(rows)
    rows.sort(key=get_score, reverse=True)

    out_file = "yolo_scores_" + MODEL.replace(".pt", "") + ".csv"
    with open(out_file, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("wrote", out_file)

    # Task 5
    total_seconds = 0.0
    total_frames = 0
    for row in rows:
        total_seconds += row["seconds"]
        total_frames += row["frames"]

    print()
    print("Model:", MODEL, " Device:", DEVICE, " Tracker:", TRACKER)
    print("Seconds per clip:", round(total_seconds / len(rows), 3))
    print("Frames per second:", round(total_frames / total_seconds, 1))

    print()
    print("Top 5:")
    for row in rows[:5]:
        print(" ", row["score"], row["clip_id"], "(" + row["classes"] + ")")

    print("Bottom 5:")
    for row in rows[-5:]:
        print(" ", row["score"], row["clip_id"], "(" + row["classes"] + ")")


if __name__ == "__main__":
    main()
