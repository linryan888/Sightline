"""
python run.py --video DIR --config config.yaml --out OUT [--log gt_log.csv --top10 top10.csv]

Writes to OUT:
  scores.csv    video, start_seconds, end_seconds, each signal (raw + within-day percentile), event, score
  selected.csv  the windows picked for the preview recap
  recap.mp4     the preview recap
  results.md    weights used, accuracy (if ground truth given), runtime per stage, CPU/GPU
"""

import argparse
import csv
import platform
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so imports work from any folder

import evaluate                                            # noqa: E402
from pipeline import SIGNALS, Timer, list_videos, load_config, probe, score_day  # noqa: E402
from select_recap import select_windows, stitch           # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="SightLine scoring pipeline (SIG-64)")
    ap.add_argument("--video", required=True, help="a video file or a folder of one day's videos")
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    ap.add_argument("--out", default="out")
    ap.add_argument("--log", help="ground-truth log CSV (file, 1-5 'would want in my recap')")
    ap.add_argument("--top10", help="top-10 moments CSV (file, time)")
    ap.add_argument("--no-recap", action="store_true", help="skip making recap.mp4")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    videos = list_videos(args.video)
    if not videos:
        sys.exit(f"No videos found in {args.video}")
    footage_min = sum(probe(v)[0] for v in videos) / 60
    print(f"{len(videos)} video(s), {footage_min:.1f} min of footage")

    timer = Timer()
    t_total = time.perf_counter()
    rows, weights = score_day(videos, cfg, timer=timer)

    # --- pick + stitch the preview recap
    t = time.perf_counter()
    picked = select_windows(rows, cfg)
    timer.add("select", t)
    if not args.no_recap:
        t = time.perf_counter()
        stitch(rows, picked, out / "recap.mp4")
        timer.add("stitch_recap", t)
    total = time.perf_counter() - t_total

    # --- outputs keyed by video + window
    cols = (["video", "start_seconds", "end_seconds"] + [f"raw_{s}" for s in SIGNALS]
            + list(SIGNALS) + ["event", "minute_of_day", "score"])
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([round(r[c], 4) if isinstance(r[c], float) else r[c] for c in cols])
    with open(out / "selected.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order", "video", "start_seconds", "end_seconds", "event", "score"])
        for k, i in enumerate(picked, 1):
            r = rows[i]
            w.writerow([k, r["video"], r["start_seconds"], r["end_seconds"], r["event"], r["score"]])
    shutil.copy(args.config, out / "config.yaml")

    # --- accuracy
    acc = {}
    if args.log:
        acc.update(evaluate.spearman(rows, evaluate.load_ratings(args.log)))
    if args.top10:
        acc.update(evaluate.recall(rows, picked, evaluate.load_moments(args.top10),
                                   cfg["evaluation"]["moment_tolerance_seconds"]))

    # --- report
    import torch
    device = (f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available()
              else f"CPU ({platform.processor() or platform.machine()})")
    n_events = len({r["event"] for r in rows})
    lines = [
        "# Run results", "",
        f"- Videos: {len(videos)} · footage: {footage_min:.1f} min · windows: {len(rows)} · "
        f"events: {n_events} · recap windows: {len(picked)}",
        f"- Device: {device}",
        f"- Weights used (after dropping constant signals): {weights}", "",
        "## Accuracy", "",
    ]
    if acc:
        if "spearman_windows" in acc:
            lines += [f"- Spearman, window score vs. its video's 1-5 rating: "
                      f"**{acc['spearman_windows']}** ({acc['windows_rated']} windows)",
                      f"- Spearman, video mean score vs. rating: **{acc['spearman_videos']}**"]
        if "recall" in acc:
            lines += [f"- Top-10 recall: **{acc['found']}/{acc['moments']}** moments in the "
                      f"{len(picked)} picked windows",
                      f"- Missed: {', '.join(acc['missed']) or 'none'}"]
    else:
        lines.append("- Not measured (run with --log and --top10 once the SIG-62 ground truth exists).")
    lines += ["", "## Runtime", "", "| Stage | Seconds |", "|---|---|"]
    lines += [f"| {k} | {v:.1f} |" for k, v in timer.seconds.items()]
    lines += [f"| **total** | **{total:.1f}** |", "",
              f"{total / max(footage_min, 1e-9):.1f} s of compute per minute of footage."]
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(lines[2:]))
    print(f"\nTop windows:")
    for r in sorted(rows, key=lambda r: -r["score"])[:5]:
        print(f"  {r['score']:.3f}  {r['video']} {r['start_seconds']:.0f}-{r['end_seconds']:.0f}s  "
              + " ".join(f"{s}={r[s]:.2f}" for s in SIGNALS))
    print(f"\nWrote {out / 'scores.csv'}, {out / 'selected.csv'}, {out / 'results.md'}"
          + ("" if args.no_recap else f", {out / 'recap.mp4'}"))


if __name__ == "__main__":
    main()