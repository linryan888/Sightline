"""SIG-22 sanity check: for 3 clips, list the 3 nearest neighbours by cosine similarity.

Writes neighbors.csv and a contact sheet PNG (middle frame of each clip) so you
can eyeball whether the neighbours look alike.

Example:
    python knn_check.py --clips ./clips --out ./out
    python knn_check.py --clips ./clips --out ./out --query clip_0003.mp4 clip_0017.mp4 clip_0030.mp4
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw


def mid_frame(path, size=(224, 126)):
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(total // 2, 0))
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        return Image.new("RGB", size, "black")
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).resize(size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", nargs=3, help="three clip_ids; default is 3 random clips")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out)
    emb = np.load(out / "embeddings.npy")
    idx = pd.read_csv(out / "index.csv")
    ids = idx["clip_id"].tolist()
    assert np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-4), "embeddings are not unit length"

    if args.query:
        queries = [ids.index(q) for q in args.query]
    else:
        queries = np.random.default_rng(args.seed).choice(len(ids), size=3, replace=False).tolist()

    sims = emb @ emb.T  # unit vectors, so dot product == cosine similarity
    rows = []
    sheet = Image.new("RGB", (224 * (args.k + 1), (126 + 18) * len(queries)), "white")
    draw = ImageDraw.Draw(sheet)
    for r, q in enumerate(queries):
        order = [j for j in np.argsort(-sims[q]) if j != q][: args.k]
        for rank, j in enumerate([q] + order):
            label = "QUERY" if rank == 0 else f"#{rank} sim={sims[q, j]:.3f}"
            sheet.paste(mid_frame(Path(args.clips) / ids[j]), (224 * rank, (126 + 18) * r + 18))
            draw.text((224 * rank + 4, (126 + 18) * r + 3), f"{label} {ids[j][:20]}", fill="black")
            if rank > 0:
                rows.append({"query": ids[q], "rank": rank, "neighbor": ids[j], "cosine": float(sims[q, j])})
    pd.DataFrame(rows).to_csv(out / "neighbors.csv", index=False)
    sheet.save(out / "neighbors.png")
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"saved {out / 'neighbors.csv'} and {out / 'neighbors.png'}")


if __name__ == "__main__":
    main()
