"""
Makes thumbnail sheets of every window so you can rate them at a glance.

    python contact_sheet.py --video DIR --template out/ratings_template.csv --out out

Writes out/contact_sheet_1.png, out/contact_sheet_2.png, ... Each thumbnail shows the middle frame
of one window, labelled with its row number (1 = first row of the template), the video and the start second.
Rate each window 1-5 ("would I want this in my recap?") in a COPY of the template, then pass it to run.py.
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows import list_videos  # noqa: E402

CELL_W, CELL_H, LABEL_H, COLS, ROWS_PER_PAGE = 320, 180, 24, 6, 4


def thumbnail(cap, fps, start, end):
    """Middle frame of the window, fitted inside CELL_W x CELL_H (black bars if the shape differs)."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, int((start + end) / 2 * fps))
    ok, frame = cap.read()
    cell = np.zeros((CELL_H, CELL_W, 3), np.uint8)
    if not ok:
        return cell
    h, w = frame.shape[:2]
    scale = min(CELL_W / w, CELL_H / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    y0, x0 = (CELL_H - nh) // 2, (CELL_W - nw) // 2
    cell[y0:y0 + nh, x0:x0 + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    return cell


def main():
    ap = argparse.ArgumentParser(description="Thumbnail sheets for rating windows")
    ap.add_argument("--video", required=True, help="the same folder (or file) you gave run.py")
    ap.add_argument("--template", required=True, help="out/ratings_template.csv from run.py")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    paths = {p.name: p for p in list_videos(args.video)}
    with open(args.template, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cells, caps = [], {}
    for n, r in enumerate(rows, 1):
        name = r["video"]
        if name not in caps:
            cap = cv2.VideoCapture(str(paths[name]))
            caps[name] = (cap, cap.get(cv2.CAP_PROP_FPS))
        cap, fps = caps[name]
        thumb = thumbnail(cap, fps, float(r["start_seconds"]), float(r["end_seconds"]))
        label = np.full((LABEL_H, CELL_W, 3), 40, np.uint8)
        text = f"{n}  {Path(name).stem}  {float(r['start_seconds']):g}s"
        cv2.putText(label, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cells.append(np.vstack([label, thumb]))
    for cap, _ in caps.values():
        cap.release()

    per_page = COLS * ROWS_PER_PAGE
    for page, i in enumerate(range(0, len(cells), per_page), 1):
        chunk = cells[i:i + per_page]
        chunk += [np.zeros_like(cells[0])] * (-len(chunk) % COLS)      # pad the last row
        grid = np.vstack([np.hstack(chunk[j:j + COLS]) for j in range(0, len(chunk), COLS)])
        path = out / f"contact_sheet_{page}.png"
        cv2.imwrite(str(path), grid)
        print(f"wrote {path}  (windows {i + 1}-{min(i + per_page, len(cells))})")


if __name__ == "__main__":
    main()
