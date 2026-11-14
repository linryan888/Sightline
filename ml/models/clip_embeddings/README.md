# SIG-63: ML scoring pipeline MVP (Karthik)

Given a day of video, give every 5-second window a score from 0 to 1 for how much it belongs in a
60-second recap, pick 6-12 varied windows, and stitch a preview `recap.mp4`.

## Setup

```
pip install torch open_clip_torch opencv-python numpy scipy pyyaml pillow
```

The first run downloads the CLIP weights (about 600 MB, once).

## Run

```
python run.py --video DIR --config config.yaml --out OUT
python run.py --video DIR --config config.yaml --out OUT --ratings ratings.csv --top10 top10.csv
```

- `DIR` is one video or a folder holding one day's videos.
- Name videos `YYYYMMDD_HHMMSS.mp4` so the pipeline knows the time of day (the same desk at 9am and at 3pm
  are then treated as different moments). Otherwise the videos are treated as back to back, in name order.
- `--random-init` skips the CLIP download and uses random weights. It is only for testing that the plumbing runs.

From Python (what the backend would call):

```python
from scoring import score_video
score_video("20261113_090000.mp4")   # -> [{"start_seconds": 0.0, "end_seconds": 5.0, "score": 0.87}, ...]
```

Scores from `score_video` are ranked within that one video. For a whole day pass every video to `score_day`
so scores are comparable.

### Rating windows for the accuracy check

```
python contact_sheet.py --video DIR --template out/ratings_template.csv --out out   # thumbnail sheets
cp out/ratings_template.csv ratings.csv                                             # copy: run.py overwrites the template
python fill_ratings.py out/ratings_template.csv ratings.csv 34251...                # one 1-5 digit per window
python run.py --video DIR --out out --ratings ratings.csv --top10 top10.csv --no-recap
```

`top10.csv` has the columns `video,time_seconds`.

## Outputs (in `--out`)

| File | What |
|---|---|
| `scores.csv` | `video, start_seconds, end_seconds`, raw measurements (`raw_*`), within-day ranks, `minute_of_day`, `score` |
| `selected.csv` | the windows picked for the recap |
| `recap.mp4` | preview recap (no audio) |
| `ratings_template.csv` | blank sheet: one row per window, fill the `rating` column (1-5) and pass it back with `--ratings` |
| `results.md` | weights used, accuracy, runtime per stage, CPU or GPU |

## Files

| File | Job |
|---|---|
| `run.py` | the one command; calls everything below in order and writes the outputs |
| `config.yaml` | all weights and settings |
| `windows.py` | find videos, cut 5 s windows (same rule as `backend/windows.py`), read start time from the file name |
| `signals.py` | measure each window: sharpness, and CLIP prompt score plus the embedding |
| `scoring.py` | percentile ranks, weighted blend, `score_day`, `score_video` |
| `select_recap.py` | MMR pick of 6-12 windows, stitch `recap.mp4` |
| `evaluate.py` | Spearman correlation and top-10 recall against human ratings |
| `contact_sheet.py` | thumbnail sheets of every window, for rating them at a glance |
| `fill_ratings.py` | turns a string of 1-5 digits (one per window) into a ratings file |

## How it works

1. **Windows.** Each video is split into 5 s windows (a pair of numbers, no files are written). A leftover tail
   under 1 s is dropped.
2. **Measure.** For each window, 3 frames are taken from the middle of 3 equal slices and shrunk to 640 px.
   - `quality`: variance of the Laplacian (an edge detector). Sharp frames score high, blurry or dark ones low.
   - `clip`: CLIP ViT-B/32 (`laion2b_s34b_b79k`) compares the window to "good moment" prompts and "boring" prompts.
     Raw score = similarity to the best good prompt minus similarity to the best boring prompt.
   - `novelty`: 1 minus the cosine similarity between the window's CLIP fingerprint and the day's average fingerprint.
3. **Rank.** Each signal is turned into a within-day percentile (sort, number 1..N, divide by N), so signals in
   different units can be blended and the lowest window of the day gets about 0 and the highest gets 1.
4. **Blend.** `score = weighted sum of the ranks`, weights from `config.yaml`. A signal that is identical for every
   window is dropped and the others are scaled up.
5. **Pick.** MMR picks windows one at a time: `lambda * score - (1 - lambda) * redundancy`, where redundancy is
   CLIP similarity to windows already picked, faded by how far apart they are in time. No two picks within 10 s
   of each other in the same video, and windows below `min_score` are only used to reach 6 windows.
6. **Stitch.** The picked windows are copied in time order into `recap.mp4`.

## Stack and why

- OpenCV for reading video: one library for seeking, frames and the sharpness maths.
- OpenCLIP ViT-B/32 with the LAION weights: small and fast on CPU, reuses SIG-22, and the same weights as the
  text-prompt scoring in SIG-23 so text and image vectors are comparable.
- SciPy `rankdata` for percentile ranks: robust to outliers and needs no units.
- No YOLO, speech or captioning: each extra model adds runtime and another weight to tune, so they are left out
  until they are shown to move the accuracy numbers.

## Signals and weights (all in `config.yaml`, 5 tuned numbers)

| Setting | Value | Meaning |
|---|---|---|
| `weights.clip` | 0.50 | looks like a good moment, not a boring one |
| `weights.novelty` | 0.20 | unlike the average moment of the day |
| `weights.quality` | 0.30 | sharp footage beats blurry |
| `time_scale_minutes` | 30 | windows this far apart count as different moments even if they look the same |
| `selection.mmr_lambda` | 0.7 | 1.0 = pick the top scores, 0.0 = pick the most varied |

These are starting values, not tuned yet.

## Results

Run on my own phone footage (3 videos: 2 iPhone videos of a classroom and a hallway, plus the Venice stock clip).

- Machine / device: MacBook Pro (Apple silicon, M2 Pro), CPU only
- Footage: 3.4 min, 41 windows scored, 12 picked for the recap
- Runtime per stage (seconds):

  | Stage | Seconds |
  |---|---|
  | load_model | 4.5 |
  | read_frames | 78.9 |
  | quality | 0.1 |
  | clip | 2.6 |
  | rank_and_blend | 0.0 |
  | select | 0.0 |
  | stitch_recap | 123.6 |
  | **total** | **209.7** |

  That is 62 s of compute per minute of footage (86.6 s total, 26 s per minute, without the recap).
  CLIP itself is only 2.6 s; almost all the time is reading frames and writing the recap video.
- Spearman vs ratings: **0.893** over 41 rated windows
- Top-10 recall: **9/10** (missed: `clip.mp4` at 2 s)

Caveat on both accuracy numbers: the 1-5 ratings and the top-10 list were drafted by Claude from the contact
sheets (`contact_sheet.py`), not by the person who filmed, so they measure agreement with that judgement. The
weights were set by hand before the ratings existed, so nothing is tuned to them. The test footage is mostly
two kinds of scene (a classroom with people, an empty hallway), which is an easy split, and about half of the
ratings are 1, so a high Spearman mostly says "classroom beats hallway". Real accuracy needs the SIG-62 ground truth.

## What is wrong with the recap after watching it

Overall it looked good on a first watch. Looking at `selected.csv` and the thumbnails, three problems:

1. **Near-duplicate picks.** Picks 7, 8 and 9 (`IMG_8384` at 5 s, 20 s and 35 s) are all the same flyer board.
   MMR let them through because the 10 s minimum gap only blocks neighbouring windows, the time fade
   (`time_scale_minutes: 30`) treats shots a minute apart as the same moment, and at `mmr_lambda: 0.7` a good score
   outweighs the redundancy penalty.
2. **Filler from a weak video.** The hallway video gave 5 of the 12 picks, with scores only 0.50-0.68: the flyer
   board three times, a dark purple room and an empty classroom. When a video has few good moments, the pipeline still
   takes its "least boring" windows instead of leaving the recap shorter.
3. **Near-identical windows are thinned out, which costs recall.** The three windows of the Venice alley look the same,
   so only one was picked, and the top-10 moment at 2 s was missed. This is the diversity step working as intended.

The recap also has no audio, so conversations are not represented beyond what the picture shows.

## Top 3 improvements I would make next

1. **Group windows into events and cap picks per event.** Cluster on fingerprint plus time of day (HDBSCAN) and let
   one event fill at most about a third of the recap. This directly fixes the repeated flyer board and gives the
   "same desk, different time" rule a real mechanism.
2. **Cut video-handling time.** Reading frames (79 s) and stitching (124 s) are 97% of the runtime. Read frames
   sequentially instead of seeking inside HEVC `.MOV` files, and encode the recap at a lower resolution (or with ffmpeg).
3. **Add people and speech signals and tune on real ground truth.** YOLO with tracking and voice activity detection
   would cover conversations, which the current signals understand least. Tune weights and prompts against the SIG-62
   ratings, checking each signal's effect on Spearman and recall.

## Limitations

- The stitched recap has no audio.
- Ranks are relative to the day: a boring day still has a "best" window. `min_score` and the 6-window minimum
  only partly guard against that.
- Averaging 3 frames loses order and misses anything that happens between sampled frames.
- Ratings in the ground-truth log are per video, so per-window accuracy is only approximate.
- Tested on only 3.4 minutes of footage from one building; with file names that carry no clock time, the videos
  were treated as back to back, so the time-of-day handling was not exercised on real data.
