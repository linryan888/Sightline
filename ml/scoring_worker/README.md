# Scoring worker (SIG-68)

Finds windows in Supabase with no score, downloads each chunk's video once from the `footage`
bucket, scores the windows with the SIG-64 pipeline (`../scoring_shreyas`), and writes each
score (0–1) back to `windows.score`.

## Setup

```
cd ml/scoring_worker
python -m pip install -r requirements.txt
copy .env.example .env        (Mac/Linux: cp .env.example .env)
```

Fill in `.env` with the project URL and the **secret / service_role key** (ask Backend).
`.env` is git-ignored; never commit it or paste the key into a chat.

> Every table has row-level security on with no policies (`backend/schema.sql`), so the public
> anon key can't see or update any rows. With it the worker prints "Nothing to score", and if a
> write is blocked it stops with a clear error instead of failing silently.

## Run

```
python worker.py --once     # score everything waiting, then exit
python worker.py --loop     # keep checking every 60 s (change with --interval)
```

Each chunk prints how many windows it scored and how long download, scoring and saving took.

## How it works

1. Ask for up to 200 windows where `score` is null, with their chunk's `storage_path`.
2. For each chunk in that batch, fetch **all** of its unscored windows, so a chunk is scored in
   one go.
3. Download the chunk once into a temp folder (deleted afterwards).
4. Run the SIG-64 signals (CLIP, YOLO11 people tracking, Silero speech, sharpness) on exactly
   those windows' `start_seconds`–`end_seconds`. The windows come from the database, so the
   worker follows Backend's window length (currently 2.5 s) automatically.
5. Turn each signal into a percentile **within the chunk**, then take the weighted sum, giving a score from 0 to 1.
   - Windows with `end_seconds <= start_seconds` get 0.
   - If every signal is identical (e.g. a chunk with one window), every window gets 0.5.
6. `update({"score": s}).eq("id", window_id)` for each window.
7. Repeat until no unscored windows are left.

**Re-running is safe:** only rows with `score = null` are picked up, so nothing is ever scored
twice. A chunk that fails (missing file, unreadable video) is skipped for the rest of that run and
retried on the next run; it never blocks the other chunks.

## Testing before automatic splitting lands

1. Start the backend and open `http://localhost:8000/docs`.
2. Use `POST /chunks/upload` to upload a video. Copy the chunk `id` from the response.
3. In the Supabase Table Editor → `windows`, insert a few rows with that `chunk_id`, e.g.
   `0–2.5`, `2.5–5`, `5–7.5`, leaving `score` empty.
4. Run `python worker.py --once`. The rows should get scores, and a second run should print
   "Nothing to score".

## Timing

Measured on a desktop CPU (no GPU), on a 30.5 s test video (chunk `068de4f3`) with 2.5 s windows:

| Run | Windows | Download | Score | Save | Per minute of video |
|---|---|---|---|---|---|
| 1 (first run, models loading) | 4 | 0.8 s | 5.2 s | 0.9 s | 13 s |
| 2 | 9 | 0.2 s | 2.7 s | 1.1 s | **8 s** |

About **8 s per minute of video** on CPU, so a 60–90 min day takes roughly 8–12 minutes. The first
run also downloads CLIP (~600 MB) and YOLO once. Saving is about 0.1 s per window with single
updates, fast enough without batching. On an older laptop CPU the same pipeline ran at ~35 s per
minute (SIG-64), mostly YOLO.

## Requests for Backend

- **`signals jsonb` column on `windows`:** I'd like to store each window's raw signals,
  `{"clip": ..., "people": ..., "speech": ..., "quality": ...}`. Right now scores are percentiles
  within one chunk. With raw signals saved, scores could be re-normalized across a user's
  whole day (and weights re-tuned) without re-running the models.
- **A chunk start time** (`start_time` on `chunks`), so the pipeline knows the time of day.
- Very short tail windows (e.g. 30–30.5 s) get noisy scores because they hold only 1 frame.
  Suggest the splitter merges a tail shorter than 1 s into the previous window.