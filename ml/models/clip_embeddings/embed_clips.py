"""SIG-22: CLIP clip embedding pipeline.

For every short video clip in a folder:
  1. sample N evenly spaced frames,
  2. embed each frame with a pretrained CLIP image encoder,
  3. average the frame embeddings, then L2-normalize -> one unit vector per clip,
  4. save embeddings.npy + index.csv (keyed by clip_id = file name).

Also records time per clip and peak memory (timing.json).

Example:
    python embed_clips.py --clips ./clips --out ./out --n-frames 6
"""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def sample_frames(path, n_frames):
    """Return up to n_frames RGB PIL images, evenly spaced across the clip.

    Frames are taken at the centre of n equal segments, so a 5 s clip with
    n=4 samples roughly t = 0.6, 1.9, 3.1, 4.4 s. This avoids the very first
    and very last frame, which are often blurry or black.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    if total > 0:
        idxs = np.unique(((np.arange(n_frames) + 0.5) / n_frames * total).astype(int))
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, bgr = cap.read()
            if ok:
                frames.append(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    if not frames:
        # Frame count unavailable or seeking failed: read everything, then pick.
        cap.release()
        cap = cv2.VideoCapture(str(path))
        allf = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            allf.append(bgr)
        if allf:
            idxs = np.unique(((np.arange(n_frames) + 0.5) / n_frames * len(allf)).astype(int))
            frames = [Image.fromarray(cv2.cvtColor(allf[i], cv2.COLOR_BGR2RGB)) for i in idxs]
    cap.release()
    return frames


def load_model(model_name, pretrained, device, random_init=False):
    import open_clip

    if random_init:
        print("WARNING: random-init weights. Plumbing test only, embeddings are meaningless.")
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=None)
    else:
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    model = model.to(device).eval()
    return model, preprocess


def peak_rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024  # macOS bytes, Linux KB


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", required=True, help="folder of video clips")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--n-frames", type=int, default=6, help="frames sampled per clip (try 4-8)")
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="openai")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--random-init", action="store_true", help="skip weight download; for plumbing tests only")
    args = ap.parse_args()

    clips = sorted(p for p in Path(args.clips).iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if not clips:
        sys.exit(f"no video files found in {args.clips}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    model, preprocess = load_model(args.model, args.pretrained, args.device, args.random_init)

    vecs, rows, decode_t, encode_t, clip_t = [], [], [], [], []
    for i, path in enumerate(clips):
        t0 = time.perf_counter()
        frames = sample_frames(path, args.n_frames)
        t1 = time.perf_counter()
        if not frames:
            print(f"skip {path.name}: no frames could be read")
            continue
        batch = torch.stack([preprocess(f) for f in frames]).to(args.device)
        with torch.no_grad():
            feats = model.encode_image(batch).float()      # (n_frames, D)
        if args.device == "cuda":
            torch.cuda.synchronize()
        t2 = time.perf_counter()
        v = feats.mean(dim=0)                               # average frames
        v = v / v.norm()                                    # L2-normalize -> unit length
        vecs.append(v.cpu().numpy())
        rows.append({"clip_id": path.name, "row": len(vecs) - 1, "n_frames_used": len(frames)})
        decode_t.append(t1 - t0)
        encode_t.append(t2 - t1)
        clip_t.append(t2 - t0)
        if (i + 1) % 10 == 0 or i + 1 == len(clips):
            print(f"{i + 1}/{len(clips)} clips")

    emb = np.stack(vecs).astype(np.float32)
    np.save(out / "embeddings.npy", emb)
    pd.DataFrame(rows).to_csv(out / "index.csv", index=False)

    timing = {
        "device": args.device,
        "model": f"{args.model}/{args.pretrained}" + (" (random init)" if args.random_init else ""),
        "n_clips": len(vecs),
        "n_frames_per_clip": args.n_frames,
        "embedding_dim": int(emb.shape[1]),
        "mean_sec_per_clip": float(np.mean(clip_t)),
        "mean_sec_decode_per_clip": float(np.mean(decode_t)),
        "mean_sec_encode_per_clip": float(np.mean(encode_t)),
        "total_sec": float(np.sum(clip_t)),
        "peak_rss_mb": peak_rss_mb(),
        "torch_threads": torch.get_num_threads(),
    }
    (out / "timing.json").write_text(json.dumps(timing, indent=2))
    print(json.dumps(timing, indent=2))
    print(f"saved {emb.shape} -> {out / 'embeddings.npy'}")


if __name__ == "__main__":
    main()
