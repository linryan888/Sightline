"""
python run.py --video DIR --config config.yaml --out OUT [--ratings ratings.csv --top10 top10.csv]

Reads a day's videos, scores every 5-second window from 0 to 1, picks a preview recap.
Writes to OUT:
  scores.csv            video, start_seconds, end_seconds, raw measurements, ranks, minute_of_day, score
  selected.csv          the windows picked for the recap
  recap.mp4             the preview recap (no audio)
  ratings_template.csv  a blank sheet to rate windows 1-5 yourself (for the accuracy check)
  results.md            weights used, accuracy (if ratings given), runtime per stage, CPU/GPU
"""

import argparse
import csv
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so imports work from any folder

import evaluate                                            # noqa: E402
from scoring import SIGNALS, Timer, load_config, score_day  # noqa: E402
from select_recap import select_windows, stitch            # noqa: E402
from windows import list_videos, video_info                # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="SightLine scoring pipeline (SIG-63)")
    ap.add_argument("--video", required=True, help="a video file, or a folder holding one day's videos")
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    ap.add_argument("--out", default="out")
    ap.add_argument("--ratings", help="CSV with columns video, rating (1-5) and optionally start_seconds")
    ap.add_argument("--top10", help="CSV with columns video, time_seconds for the top 10 moments")
    ap.add_argument("--no-recap", action="store_true", help="skip making recap.mp4")
    ap.add_argument("--random-init", action="store_true",
                    help="testing only: use random CLIP weights instead of downloading real ones")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    videos = list_videos(args.video)
    if not videos:
        sys.exit(f"No videos found in {args.video}")
    footage_min = sum(video_info(v)[1] for v in videos) / 60
    print(f"{len(videos)} video(s), {footage_min:.1f} min of footage")

    timer = Timer()
    t_total = time.perf_counter()
    rows, weights = score_day(videos, cfg, timer=timer, random_init=args.random_init)
    if not rows:
        sys.exit("No windows could be scored.")

    t = time.perf_counter()
    picked = select_windows(rows, cfg)
    timer.add("select", t)
    if not args.no_recap:
        t = time.perf_counter()
        stitch(rows, picked, out / "recap.mp4")
        timer.add("stitch_recap", t)
    total = time.perf_counter() - t_total

    # ---- outputs
    cols = (["video", "start_seconds", "end_seconds"] + [f"raw_{s}" for s in SIGNALS]
            + list(SIGNALS) + ["minute_of_day", "score"])
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([round(r[c], 4) if isinstance(r[c], float) else r[c] for c in cols])
    with open(out / "selected.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order", "video", "start_seconds", "end_seconds", "score"])
        for k, i in enumerate(picked, 1):
            r = rows[i]
            w.writerow([k, r["video"], r["start_seconds"], r["end_seconds"], r["score"]])
    evaluate.write_template(rows, out / "ratings_template.csv")
    shutil.copy(args.config, out / "config.yaml")

    # ---- accuracy (only if the human ratings exist)
    acc = {}
    if args.ratings:
        acc.update(evaluate.spearman(rows, evaluate.load_ratings(args.ratings)))
    if args.top10:
        acc.update(evaluate.recall(rows, picked, evaluate.load_moments(args.top10),
                                   cfg["evaluation"]["moment_tolerance_seconds"]))

    # ---- report
    import torch
    device = f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU"
    lines = ["# Run results", "",
             f"- Videos: {len(videos)} | footage: {footage_min:.1f} min | windows scored: {len(rows)} "
             f"| recap windows: {len(picked)}",
             f"- Device: {device}",
             f"- Weights used: {weights}", "", "## Accuracy", ""]
    if acc.get("spearman") is not None or "windows_rated" in acc:
        lines.append(f"- Spearman (score vs your rating): **{acc['spearman']}** over {acc['windows_rated']} rated windows")
    if "moments" in acc:
        lines.append(f"- Top-10 recall: **{acc['found']}/{acc['moments']}** moments inside the {len(picked)} picked windows")
        lines.append(f"- Missed: {', '.join(acc['missed']) or 'none'}")
    if not acc:
        lines.append("- Not measured yet. Fill in ratings_template.csv and rerun with --ratings (and --top10).")
    lines += ["", "## Runtime", "", "| Stage | Seconds |", "|---|---|"]
    lines += [f"| {k} | {v:.1f} |" for k, v in timer.seconds.items()]
    lines += [f"| **total** | **{total:.1f}** |", "",
              f"{total / max(footage_min, 1e-9):.1f} s of compute per minute of footage."]
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(lines[2:]))
    print("\nTop 5 windows:")
    for r in sorted(rows, key=lambda r: -r["score"])[:5]:
        print(f"  {r['score']:.3f}  {r['video']} {r['start_seconds']:.0f}-{r['end_seconds']:.0f}s  "
              + " ".join(f"{s}={r[s]:.2f}" for s in SIGNALS))
    print(f"\nWrote files to {out}/")


if __name__ == "__main__":
    main()
