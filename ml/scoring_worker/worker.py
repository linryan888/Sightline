"""
SightLine scoring worker (SIG-68)

Finds windows in Supabase that have no score yet, downloads each chunk's video once,
scores the windows with the SIG-64 pipeline (../scoring_shreyas), and writes the scores back.

    python worker.py --once     # score everything that's waiting, then exit
    python worker.py --loop     # keep checking for new windows every 60 seconds

Needs a .env file next to this script (never commit it):
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_KEY=<the secret / service_role key, same as backend's>
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scoring_shreyas"))   # reuse the SIG-64 pipeline code
from pipeline import Models, Timer, combine, load_config, probe, process_video  # noqa: E402

BUCKET = "footage"
BATCH = 200


def connect():
    """Supabase client from the URL and key in .env."""
    load_dotenv(HERE / ".env")
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY. Put them in ml/scoring_worker/.env")
    return create_client(url, key)


def fetch_unscored(sb, skip_chunks):
    """Up to 200 windows with no score, each with its chunk's storage path.
    Chunks that already failed in this run are skipped so they can't block the rest."""
    q = sb.table("windows").select("*, chunks(storage_path)").is_("score", "null")
    if skip_chunks:
        q = q.not_.in_("chunk_id", list(skip_chunks))
    return q.limit(BATCH).execute().data


def unscored_windows_of(sb, chunk_id):
    """Every unscored window of one chunk. A chunk is always scored in one go, because each
    score is a percentile within the chunk and needs all of the chunk's windows together."""
    return (sb.table("windows").select("*").eq("chunk_id", chunk_id)
            .is_("score", "null").order("start_seconds").execute().data)


def download(sb, storage_path, folder):
    """Copies one video from the footage bucket into a temp folder."""
    path = Path(folder) / Path(storage_path).name
    path.write_bytes(sb.storage.from_(BUCKET).download(storage_path))
    return path


def score_chunk(video, wins, models, cfg):
    """Raw signals for exactly these windows -> percentiles within the chunk -> score 0-1.
    Returns {window_id: score}."""
    good = [w for w in wins if float(w["end_seconds"]) > float(w["start_seconds"])]
    scores = {w["id"]: 0.0 for w in wins if w not in good}     # empty/backwards windows get 0
    if not good:
        return scores
    windows = [(float(w["start_seconds"]), float(w["end_seconds"])) for w in good]
    rows = process_video(video, models, cfg, Timer(), windows=windows)
    weights = combine(rows, cfg)
    if sum(weights.values()) == 0:   # every signal identical (e.g. one window): nothing to rank by
        scores.update({w["id"]: 0.5 for w in good})
    else:
        scores.update({w["id"]: r["score"] for w, r in zip(good, rows)})
    return scores


def save(sb, scores):
    """Writes each score to its window row (one small update per window)."""
    for window_id, s in scores.items():
        res = sb.table("windows").update({"score": s}).eq("id", window_id).execute()
        if not res.data:
            raise PermissionError(
                "Supabase updated 0 rows. The key can't write to `windows` because of "
                "row-level security; use the secret/service_role key in .env.")


def run_once(sb, cfg, state):
    """Scores windows until none are left. Returns how many were scored."""
    failed, done = set(), 0
    while True:
        chunks = {}
        for w in fetch_unscored(sb, failed):
            if w.get("chunks"):
                chunks.setdefault(w["chunk_id"], w["chunks"]["storage_path"])
        if not chunks:
            return done
        if "models" not in state:            # load the models only when there's work to do
            print("Loading models...")
            state["models"] = Models(cfg)
        for chunk_id, storage_path in chunks.items():
            try:
                wins = unscored_windows_of(sb, chunk_id)
                t0 = time.perf_counter()
                with tempfile.TemporaryDirectory() as tmp:
                    video = download(sb, storage_path, tmp)
                    t1 = time.perf_counter()
                    minutes = probe(video)[0] / 60
                    scores = score_chunk(video, wins, state["models"], cfg)
                t2 = time.perf_counter()
                save(sb, scores)
                t3 = time.perf_counter()
            except PermissionError:
                raise                            # wrong key: no point trying other chunks
            except Exception as e:               # bad video, network blip...: skip it this run
                print(f"  chunk {chunk_id[:8]}: FAILED ({type(e).__name__}: {e})")
                failed.add(chunk_id)
                continue
            done += len(scores)
            state["minutes"] = state.get("minutes", 0.0) + minutes
            state["seconds"] = state.get("seconds", 0.0) + (t3 - t0)
            print(f"  chunk {chunk_id[:8]}: {len(scores)} windows, {minutes:.1f} min of video | "
                  f"download {t1 - t0:.1f}s, score {t2 - t1:.1f}s, save {t3 - t2:.1f}s | "
                  f"{(t3 - t0) / max(minutes, 1e-9):.0f}s per minute of video")


def main():
    ap = argparse.ArgumentParser(description="SightLine scoring worker (SIG-68)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="score everything waiting, then exit")
    mode.add_argument("--loop", action="store_true", help="keep checking every --interval seconds")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--config", default=str(HERE.parent / "scoring_shreyas" / "config.yaml"))
    args = ap.parse_args()

    sb = connect()
    cfg = load_config(args.config)
    state = {}
    while True:
        try:
            n = run_once(sb, cfg, state)
            if n:
                print(f"Scored {n} window(s). Total so far: {state['minutes']:.1f} min of video in "
                      f"{state['seconds']:.0f}s ({state['seconds'] / state['minutes']:.0f}s per minute).")
            elif args.once:
                print("Nothing to score. (If you expected windows, check SUPABASE_KEY is the "
                      "secret key: with the anon key, row-level security hides every row.)")
        except PermissionError as e:
            sys.exit(str(e))
        except Exception as e:                   # e.g. Supabase unreachable: report, try again later
            if args.once:
                raise
            print(f"Run failed ({type(e).__name__}: {e}); retrying in {args.interval}s")
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()