# YOLOv8 object-based clip scoring (ML Build #3, SIG-24)

Scores each clip by what YOLO sees in it (people, objects, and how much they move) and
combines that into a first 0–1 score. All outputs are keyed by `clip_id` (the clip's file name).

## Setup

```
python -m pip install -r requirements.txt
```

## Run

```
python scoring.py
```

Run it from this folder. It writes `yolo_scores_<model>.csv` (e.g. `yolo_scores_yolov8n.csv`),
one row per clip, sorted from highest to lowest score, and prints speed plus the top 5 / bottom 5.
To compare setups, change `MODEL` (`yolov8n.pt` / `yolo11n.pt`), `DEVICE` (`cpu` / `mps` / `cuda`)
or `TRACKER` (`bytetrack.yaml` / `botsort.yaml`).

## Method

1. **Detection + tracking.** Each clip is run through `model.track` with ByteTrack, sampling about
   10 frames per second.
2. **Clip features** (detections with confidence ≥ 0.4):
   - `max_people` / `avg_people`: people per sampled frame.
   - `distinct_classes`: number of different COCO classes. A class only counts if it shows up in at
     least 10% of the frames (and at least 3). Classes that only flicker in for a frame or two were
     almost always false detections. 
   - `avg_conf`: average confidence of all returned boxes.
3. **Activity** (from tracking). Tracks shorter than 3 frames are ignored as noise. For each track:
   - **entered**: it first appears after the first couple of frames *and* its box touches the outer
     5% of the frame.
   - **left**: it disappears before the last couple of frames *and* its box touches the outer 5%.
   - **moved**: its center moved more than 5% of the frame diagonal from start to end.
   - `activity = entered + left + moved`.
4. **Score.** Each feature is divided by a fixed cap and clipped to 1, then combined with weights:

   | Feature | Weight | Cap |
   |---|---|---|
   | `activity` | 0.45 | 25 events per clip |
   | `avg_people` | 0.25 | 5 people |
   | `distinct_classes` | 0.20 | 4 classes |
   | `avg_conf` | 0.10 | 1.0 |

   The weights add up to 1, so the score is always between 0 and 1.

## Results

33 clips: biking (3), concert (5), conversation (1), crowd (2), desert (5), desert with car (5),
dogs (6), hallway (3), skiing (3). These are stock clips used to test. Will switch to sightline clips later.

### Why these weights

- **Activity gets the most weight (0.45).** The ticket asks for change across frames, and
  YOLO also detects things that are just sitting there. A clip where things come and go or move
  around is more likely to be worth keeping than a static one.
- **People are next (0.25).** People being in the clip is also important. They are capped at 5 so that a crowd of 20 doesn't count four times as much as a group of 5.
- **Distinct classes (0.20)** reward scenes with more going on. They're only trustworthy because of the
  10% frame filter; without it, false classes inflated this feature.
- **Confidence is low (0.10).** It mostly says how clear the footage is.

### Top 5 / bottom 5

**yolov8n**

| Rank | Score | Clip | Classes |
|---|---|---|---|
| 1 | 0.9436 | crowd_00.mp4 | backpack, handbag, horse, person |
| 2 | 0.8957 | crowd_01.mp4 | backpack, chair, person |
| 3 | 0.8787 | conversation_00.mp4 | chair, cup, dining table, laptop, person, potted plant |
| 4 | 0.5161 | concert_02.mp4 | person |
| 5 | 0.4404 | concert_03.mp4 | person, tv |
| … | | | |
| 29 | 0.0139 | hallway_02.mp4 | (none) |
| 30 | 0.0137 | desert_04.mp4 | (none) |
| 31 | 0.0130 | desert_02.mp4 | (none) |
| 32 | 0.0121 | desert_00.mp4 | (none) |
| 33 | 0.0112 | desert_01.mp4 | (none) |

**yolo11n**

| Rank | Score | Clip | Classes |
|---|---|---|---|
| 1 | 0.8941 | crowd_01.mp4 | backpack, handbag, person |
| 2 | 0.8827 | conversation_00.mp4 | chair, cup, dining table, laptop, person, potted plant |
| 3 | 0.8463 | crowd_00.mp4 | backpack, person |
| 4 | 0.5920 | skiing_01.mp4 | person, skis, snowboard |
| 5 | 0.4633 | skiing_02.mp4 | person, skis, snowboard |
| … | | | |
| 29 | 0.0170 | biking_00.mp4 | (none) |
| 30 | 0.0132 | desert_00.mp4 | (none) |
| 31 | 0.0000 | desert_01.mp4 | (none) |
| 32 | 0.0000 | desert_02.mp4 | (none) |
| 33 | 0.0000 | desert_04.mp4 | (none) |

Full rankings are in `yolo_scores_yolov8n.csv` and `yolo_scores_yolo11n.csv`.

### Does the ranking feel right?

- **Top:** the crowds and the conversation are the clips with the most people and the most going on,
  so they belong near the top. The capping keeps them close together (0.85–0.94) instead of
  one crowd running away with it.
- **Bottom:** the empty desert and hallway shots are correctly at the bottom. YOLO finds nothing in
  them, which is what we'd want from a "nothing happened" clip.
- Skiing ranks higher with yolo11n (4th and 5th) because it detects skis and snowboards in enough frames.
  yolov8n mostly misses them, so concerts take those spots instead.
- Dogs score low (~0.16, ranked 10–17) even though they're lively clips. The camera follows the
  dog, so it stays in the same part of the frame and gets almost no "moved" credit. They're also
  not people, so they get nothing from the people feature.
- Some clips from concert are not ranked at the top. They're dark, so confidence is low and aren't able to identify people with high confidence.

### Failure cases

- **False classes that persist.** The frame filter removes one-off mistakes, but not ones that repeat:
  "horse" still shows up in crowd_00 with yolov8n, "cow" in dogs_00 (about 20 frames), and the car in
  the desert clips is labeled "boat."
- **Motion blur.** Bikes are fast and blurred, so bicycles are only detected in 2–3 frames and get
  filtered out. All three biking clips land in the bottom half (ranks 25–27 with yolov8n), and
  biking_00 is in yolo11n's bottom 5.
- **Low light.** Dark concert clips get low confidence and fewer detections, so they score lower than
  similar brighter clips.
- **Things that aren't COCO classes.** Scenery like deserts and hallways has nothing YOLO can detect,
  so those clips score about 0.

### Speed

ByteTrack, 33 clips sampled at about 10 fps, `imgsz=1280`. Times are tracking only (model load excluded).

| Model | Device | Seconds per clip | Frames per second |
|---|---|---|---|
| yolov8n | CPU | 2.692 | 20.5 |
| yolov8n | GPU (mps) | 0.744 | 74.1 |
| yolo11n | CPU | 2.907 | 19.0 |
| yolo11n | GPU (mps) | 0.759 | 72.6 |

The GPU is about 3.6× faster than CPU for both models. yolov8n and yolo11n run at almost the same speed
(v8n slightly faster). Scores were identical on CPU and GPU.

### ByteTrack vs BoT-SORT

yolov8n on GPU (mps), same clips and settings, only the tracker changed:

| Tracker | Seconds per clip | Frames per second |
|---|---|---|
| ByteTrack | 0.744 | 74.1 |
| BoT-SORT | 1.481 | 37.2 |

BoT-SORT is about half the speed (it also estimates camera motion between frames). The top 3 and bottom 5 were
the same, and crowd clips had slightly fewer ID switches (120 vs 130 track IDs on crowd_00). Concerts
ranked a little higher and the desert-with-car clips dropped to near 0 because the car wasn't tracked as
moving. 
