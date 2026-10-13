"""
SightLine - ML Build #2: cluster clips by scene/location + zero-shot relevance score
==================================================================================

What it does
  1. Embeds every clip with CLIP (or loads embeddings from ML Build #1 with --embeddings)
  2. Clusters the embeddings with k-means, agglomerative (cosine), and HDBSCAN
     and picks the number of clusters with the silhouette score
  3. Makes a contact sheet per method (thumbnails grouped by cluster) + a UMAP plot
  4. Zero-shot scores every clip against text prompts and reports which prompts
     actually separate interesting clips from boring ones
  5. Outputs the top-scoring clip in each cluster

Everything is keyed by clip_id (the clip's file name).

Usage
  python sightline_cluster.py clips
  python sightline_cluster.py clips --labels labels.csv            # adds prompt AUCs + location agreement
  python sightline_cluster.py clips --embeddings embeddings.npy    # reuse ML Build #1 embeddings (+ index CSV)
  python sightline_cluster.py clips --prompts prompts.txt          # your own prompts

Outputs (in --out, default cluster_output/)
  clips.csv             one row per clip_id: cluster for each method, relevance, similarity to every prompt
  top_per_cluster.csv   best clip in each cluster, for each method
  prompt_report.csv     how well each prompt separates interesting vs boring clips
  summary.json          silhouette scores, chosen k, chosen method, metrics
  embeddings.npz        clip_ids + embeddings (same format --embeddings reads)
  contact_<method>.png  thumbnails grouped by cluster
  umap.png              2D map of the clips, colored by cluster for each method
  silhouette.png        silhouette score vs k
  report.html           everything above in one page
  labels_template.csv   fill this in by eye, then rerun with --labels
"""

import argparse
import base64
import csv
import json
import sys
import warnings
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}

# "+" = what an interesting moment looks like, "-" = what a boring one looks like.
DEFAULT_PROMPTS = [
    "+ people talking at a table",
    "+ friends laughing together",
    "+ a scenic outdoor view",
    "+ a plate of delicious food",
    "+ a crowd at a live event",
    "+ a cute pet",
    "- an empty hallway",
    "- a blank wall",
    "- the ground while walking",
    "- a computer screen at a desk",
]
TEMPLATE = "a first-person photo of {}"  # glasses footage is first-person; set --no-template to disable

PALETTE = ["#2a6fdb", "#e0592a", "#1f9e6e", "#c43d8f", "#8a6d1f", "#5b4bc4", "#d1453b",
           "#2b8fa3", "#7a9e1f", "#a35b2b", "#4d4d4d", "#b0306a", "#3d7a3d", "#6b4fa0"]
NOISE_COLOR = "#b5b5b5"


# ---------------------------------------------------------------- loading

def list_clips(folder):
    folder = Path(folder)
    if not folder.is_dir():
        sys.exit(f"'{folder}' is not a folder of clips.")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if len(files) < 4:
        sys.exit(f"Found {len(files)} clips in '{folder}'. Need at least 4 to cluster.")
    return files


def read_frames(path, n):
    """n frames spread evenly through the clip (skipping the very start/end), plus the middle frame."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = total / fps if total else 5.0
    times = np.linspace(0, dur, n + 2)[1:-1]
    frames = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        s = 448 / max(h, w)
        if s < 1:
            fr = cv2.resize(fr, (int(w * s), int(h * s)))
        frames.append(Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames


def load_clip_model(name, pretrained):
    import open_clip
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CLIP {name} ({pretrained or 'random weights'}) on {device}...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        name, pretrained=pretrained or None, device=device)
    model.eval()
    return model, preprocess, open_clip.get_tokenizer(name), device


def embed_images(model, preprocess, device, images, bs=32):
    import torch
    out = []
    with torch.no_grad():
        for i in range(0, len(images), bs):
            x = torch.stack([preprocess(im) for im in images[i:i + bs]]).to(device)
            e = model.encode_image(x).float()
            out.append(torch.nn.functional.normalize(e, dim=-1).cpu())
    return torch.cat(out).numpy()


def embed_texts(model, tokenizer, device, texts):
    import torch
    with torch.no_grad():
        e = model.encode_text(tokenizer(texts).to(device)).float()
        return torch.nn.functional.normalize(e, dim=-1).cpu().numpy()


def l2norm(x):
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)


def _index_ids(index_path):
    """Index CSV from ML Build #1: needs a clip_id column (row i = row i of the .npy)."""
    with open(index_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or "clip_id" not in rows[0]:
        sys.exit(f"{index_path} needs a 'clip_id' column.")
    if "row" in rows[0]:  # optional explicit row number
        rows.sort(key=lambda r: int(r["row"]))
    return [r["clip_id"].strip() for r in rows]


def load_embeddings(path, clip_ids, index=None):
    """Reads ML Build #1 output. Accepts:
       .npy + index CSV (clip_id column)  - Build #1's suggested format
       .parquet  (clip_id column + an 'embedding' list column, or numeric columns)
       .npz      (clip_ids + embeddings arrays - what this script saves)
       .csv      (clip_id, e0, e1, ...)"""
    path = Path(path)
    if path.suffix == ".npy":
        emb = np.load(path)
        if index is None:  # look for an index CSV next to the .npy
            cands = [path.with_suffix(".csv"), path.with_name(path.stem + "_index.csv"),
                     path.parent / "index.csv"] + sorted(path.parent.glob("*index*.csv"))
            index = next((c for c in cands if c.exists()), None)
            if index is None:
                sys.exit(f"Found {path.name} but no index CSV next to it. Pass it with --index.")
        ids = _index_ids(index)
        if len(ids) != len(emb):
            sys.exit(f"{index} has {len(ids)} rows but {path.name} has {len(emb)} embeddings.")
    elif path.suffix == ".parquet":
        import pandas as pd
        df = pd.read_parquet(path)
        if "clip_id" not in df.columns:
            sys.exit(f"{path} needs a 'clip_id' column.")
        ids = df["clip_id"].astype(str).tolist()
        vec_col = next((c for c in ("embedding", "embeddings", "vector") if c in df.columns), None)
        if vec_col:
            emb = np.stack(df[vec_col].map(np.asarray).tolist())
        else:
            emb = df.drop(columns=["clip_id"]).select_dtypes("number").to_numpy()
    elif path.suffix == ".npz":
        d = np.load(path, allow_pickle=True)
        ids = [str(x) for x in d["clip_ids"]]
        emb = d["embeddings"]
    else:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        ids = [r[0] for r in rows[1:]]
        emb = np.array([[float(v) for v in r[1:]] for r in rows[1:]])
    lookup = dict(zip(ids, emb))
    missing = [c for c in clip_ids if c not in lookup]
    if missing:
        sys.exit(f"--embeddings is missing {len(missing)} clips, e.g. {missing[:3]}")
    return l2norm(np.stack([lookup[c] for c in clip_ids]).astype(np.float32))


def read_prompts(path):
    lines = DEFAULT_PROMPTS
    if path:
        lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    prompts = []
    for l in lines:
        if l[0] not in "+-":
            sys.exit(f"Prompt lines must start with + or -: '{l}'")
        prompts.append((l[1:].strip(), 1 if l[0] == "+" else -1))
    return prompts


def read_labels(path, clip_ids):
    """labels.csv columns: clip_id, interesting (1/0 or blank), location (free text or blank)."""
    if not path:
        return {}, {}
    interesting, location = {}, {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cid = (r.get("clip_id") or "").strip()
            if cid not in clip_ids:
                continue
            v = (r.get("interesting") or "").strip()
            if v in ("0", "1"):
                interesting[cid] = int(v)
            loc = (r.get("location") or "").strip()
            if loc:
                location[cid] = loc
    print(f"Labels: {len(interesting)} interesting/boring, {len(location)} locations.")
    return interesting, location


# ---------------------------------------------------------------- clustering

def run_clustering(X, k_min, k_max, min_cluster_size):
    from sklearn.cluster import HDBSCAN, AgglomerativeClustering, KMeans
    from sklearn.metrics import silhouette_score

    n = len(X)
    k_max = min(k_max, n - 1)
    ks = list(range(k_min, k_max + 1))
    results, sweep = {}, {"k": ks, "kmeans": [], "agglomerative": []}

    def sil(labels):
        mask = labels >= 0
        if len(set(labels[mask])) < 2 or mask.sum() < 3:
            return float("nan")
        return float(silhouette_score(X[mask], labels[mask], metric="cosine"))

    for name in ("kmeans", "agglomerative"):
        best = None
        for k in ks:
            if name == "kmeans":
                lab = KMeans(n_clusters=k, n_init=20, random_state=0).fit_predict(X)
            else:
                lab = AgglomerativeClustering(n_clusters=k, metric="cosine",
                                              linkage="average").fit_predict(X)
            s = sil(lab)
            sweep[name].append(s)
            if best is None or (s > best[0]):
                best = (s, k, lab)
        results[name] = {"labels": best[2], "k": best[1], "silhouette": best[0]}

    # HDBSCAN picks k by itself; -1 = noise (clip didn't fit any group)
    lab = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=1,
                  metric="euclidean").fit_predict(X)  # euclidean on unit vectors ~ cosine
    results["hdbscan"] = {"labels": lab, "k": int(len(set(lab) - {-1})),
                          "silhouette": sil(lab), "noise": int((lab == -1).sum())}
    return results, sweep


def contiguity(labels):
    """Share of neighbouring clips (in file/time order) that land in the same cluster.
    Clips from one place are usually filmed back to back, so higher = more event-like clusters."""
    same = [labels[i] == labels[i + 1] for i in range(len(labels) - 1) if labels[i] >= 0 and labels[i + 1] >= 0]
    return float(np.mean(same)) if same else float("nan")


def location_agreement(labels, clip_ids, location):
    from sklearn.metrics import adjusted_rand_score
    idx = [i for i, c in enumerate(clip_ids) if c in location]
    if len(idx) < 4:
        return float("nan")
    return float(adjusted_rand_score([location[clip_ids[i]] for i in idx], [labels[i] for i in idx]))


# ---------------------------------------------------------------- scoring

def zero_shot(X, T, polarity, logit_scale=100.0):
    """CLIP zero-shot: softmax over all prompts. relevance = probability mass on '+' prompts."""
    sims = X @ T.T
    z = logit_scale * sims
    z -= z.max(1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(1, keepdims=True)
    relevance = p[:, np.array(polarity) > 0].sum(1)
    return sims, relevance


def prompt_report(sims, prompts, relevance, clip_ids, interesting):
    from sklearn.metrics import roc_auc_score
    rows = []
    y_idx = [i for i, c in enumerate(clip_ids) if c in interesting]
    y = np.array([interesting[clip_ids[i]] for i in y_idx])
    have_labels = len(y_idx) >= 4 and 0 < y.sum() < len(y)

    def auc(v):
        return float(roc_auc_score(y, v[y_idx])) if have_labels else float("nan")

    for j, (text, pol) in enumerate(prompts):
        col = sims[:, j]
        order = np.argsort(-col)
        a = auc(col)
        # a '+' prompt should score interesting clips higher (AUC > 0.5);
        # a '-' prompt should score them lower (AUC < 0.5). "useful" folds both into one number.
        useful = (a if pol > 0 else 1 - a) if have_labels else float("nan")
        rows.append({
            "prompt": text, "type": "interesting" if pol > 0 else "boring",
            "auc": a, "usefulness": useful, "spread": float(col.std()),
            "top3": ", ".join(clip_ids[i] for i in order[:3]),
            "bottom3": ", ".join(clip_ids[i] for i in order[-3:]),
        })
    overall = {"relevance_auc": auc(relevance), "labeled_clips": len(y_idx) if have_labels else 0}
    return rows, overall


# ---------------------------------------------------------------- visuals

def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(thumbs, clip_ids, labels, relevance, title, path, tw=200, cols=6):
    th = int(tw * 9 / 16)
    groups = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)
    order = sorted(groups, key=lambda g: (g == -1, g))  # noise last
    f_title, f_head, f_cap = font(26), font(18), font(13)
    pad, cap_h, head_h = 14, 34, 34
    rows_needed = sum(-(-len(groups[g]) // cols) for g in order)
    W = pad * 2 + cols * (tw + pad)
    H = 60 + len(order) * (head_h + pad) + rows_needed * (th + cap_h + pad) + pad
    sheet = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(sheet)
    d.text((pad, 16), title, fill="#111", font=f_title)
    y = 60
    for g in order:
        members = sorted(groups[g], key=lambda i: -relevance[i])
        color = NOISE_COLOR if g == -1 else PALETTE[g % len(PALETTE)]
        name = "Noise (didn't fit a group)" if g == -1 else f"Cluster {g}"
        d.rectangle([pad, y + 6, pad + 14, y + 20], fill=color)
        d.text((pad + 22, y + 2), f"{name}  ·  {len(members)} clips", fill="#111", font=f_head)
        y += head_h
        for n, i in enumerate(members):
            r, c = divmod(n, cols)
            x0, y0 = pad + c * (tw + pad), y + r * (th + cap_h + pad)
            im = thumbs[i].copy()
            im.thumbnail((tw, th))
            box = Image.new("RGB", (tw, th), "#eee")
            box.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
            sheet.paste(box, (x0, y0))
            if n == 0 and g != -1:
                d.rectangle([x0 - 3, y0 - 3, x0 + tw + 2, y0 + th + 2], outline=color, width=4)
            cid = clip_ids[i] if len(clip_ids[i]) <= 26 else clip_ids[i][:24] + "…"
            d.text((x0, y0 + th + 3), cid, fill="#222", font=f_cap)
            d.text((x0, y0 + th + 18), f"relevance {relevance[i]:.2f}" + ("  ★ top" if n == 0 and g != -1 else ""),
                   fill="#666", font=f_cap)
        y += -(-len(members) // cols) * (th + cap_h + pad) + pad
    sheet.save(path)


def projection_2d(X):
    try:
        import umap
        n_nb = max(2, min(15, len(X) - 1))
        xy = umap.UMAP(n_neighbors=n_nb, min_dist=0.2, metric="cosine", random_state=0).fit_transform(X)
        return xy, "UMAP"
    except Exception as e:  # umap-learn not installed / not supported on this Python
        print(f"UMAP unavailable ({type(e).__name__}); using t-SNE instead.")
        from sklearn.manifold import TSNE
        xy = TSNE(n_components=2, perplexity=max(2, min(10, len(X) // 3)), metric="cosine",
                  init="pca", random_state=0).fit_transform(X)
        return xy, "t-SNE"


def plot_map(xy, method_name, results, clip_ids, relevance, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(results)
    fig, axes = plt.subplots(1, len(names), figsize=(6.2 * len(names), 6), dpi=110)
    for ax, name in zip(np.atleast_1d(axes), names):
        lab = results[name]["labels"]
        colors = [NOISE_COLOR if l == -1 else PALETTE[l % len(PALETTE)] for l in lab]
        sizes = 40 + 260 * (relevance - relevance.min()) / (np.ptp(relevance) + 1e-8)
        ax.scatter(xy[:, 0], xy[:, 1], c=colors, s=sizes, edgecolors="white", linewidths=1, alpha=0.9)
        for i, cid in enumerate(clip_ids):
            ax.annotate(Path(cid).stem[:14], xy[i], fontsize=7, color="#333",
                        xytext=(4, 4), textcoords="offset points")
        s = results[name]["silhouette"]
        ax.set_title(f"{name}  (k={results[name]['k']}, silhouette={s:.2f})", fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#ddd")
    fig.suptitle(f"{method_name} of CLIP embeddings — color = cluster, size = relevance", fontsize=13)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_silhouette(sweep, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=110)
    ax.plot(sweep["k"], sweep["kmeans"], marker="o", color=PALETTE[0], label="k-means")
    ax.plot(sweep["k"], sweep["agglomerative"], marker="s", color=PALETTE[1], label="agglomerative (cosine)")
    ax.set_xlabel("number of clusters (k)")
    ax.set_ylabel("silhouette score (higher = cleaner groups)")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def b64_png(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def b64_thumb(img, w=150):
    im = img.copy()
    im.thumbnail((w, w))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def fmt(v, nd=2):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def write_html(path, out, summary, results, prompt_rows, top_rows, thumbs, clip_ids):
    import html as h
    method_rows = "".join(
        f"<tr><td>{n}</td><td>{r['k']}</td><td>{fmt(r['silhouette'])}</td>"
        f"<td>{fmt(summary['methods'][n]['contiguity'])}</td><td>{fmt(summary['methods'][n]['location_ari'])}</td>"
        f"<td>{r.get('noise', 0)}</td></tr>" for n, r in results.items())
    prompt_html = "".join(
        f"<tr><td>{h.escape(p['prompt'])}</td><td>{p['type']}</td><td>{fmt(p['auc'])}</td>"
        f"<td>{fmt(p['usefulness'])}</td><td>{fmt(p['spread'], 3)}</td>"
        f"<td>{h.escape(p['top3'])}</td><td>{h.escape(p['bottom3'])}</td></tr>" for p in prompt_rows)
    idx = {c: i for i, c in enumerate(clip_ids)}
    top_html = "".join(
        f"<div class='card'><img src='data:image/jpeg;base64,{b64_thumb(thumbs[idx[t['clip_id']]])}'>"
        f"<div><b>Cluster {t['cluster']}</b> · {t['size']} clips<br>{h.escape(t['clip_id'])}<br>"
        f"<small>relevance {float(t['relevance']):.2f}</small></div></div>"
        for t in top_rows if t["method"] == summary["primary_method"])
    sheets = "".join(f"<h3>{n}</h3><img class='wide' src='data:image/png;base64,{b64_png(out / f'contact_{n}.png')}'>"
                     for n in results)
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SightLine Clustering</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px auto;max-width:1300px;padding:0 16px;color:#1b1b1f;background:#fafafa}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:14px;margin-bottom:8px}}
td,th{{border-bottom:1px solid #e5e5e5;padding:7px 9px;text-align:left}} th{{background:#f2f2f2}}
img.wide{{max-width:100%;border:1px solid #e5e5e5;border-radius:6px;background:#fff}}
.cards{{display:flex;flex-wrap:wrap;gap:12px}} .card{{background:#fff;border:1px solid #e5e5e5;border-radius:8px;
padding:8px;display:flex;gap:10px;align-items:center;font-size:13px}} .card img{{border-radius:6px}}
.note{{color:#555;font-size:14px;max-width:900px}}
</style></head><body>
<h1>SightLine — clip clustering &amp; zero-shot relevance</h1>
<p class="note">{summary['n_clips']} clips · embeddings: {h.escape(summary['embedding_source'])} ·
primary method: <b>{summary['primary_method']}</b></p>
<h2>Clustering methods</h2>
<p class="note">Silhouette: how cleanly clips separate into groups (−1 to 1). Contiguity: share of back-to-back clips
that land in the same cluster (higher = clusters look like real events). Location ARI: agreement with your hand
labels (1 = perfect, 0 = random; needs --labels).</p>
<table><tr><th>Method</th><th>k</th><th>Silhouette</th><th>Contiguity</th><th>Location ARI</th><th>Noise clips</th></tr>
{method_rows}</table>
<img class="wide" src="data:image/png;base64,{b64_png(out / 'silhouette.png')}">
<h2>{summary['projection']} map</h2>
<img class="wide" src="data:image/png;base64,{b64_png(out / 'umap.png')}">
<h2>Top clip per cluster ({summary['primary_method']})</h2><div class="cards">{top_html}</div>
<h2>Prompts</h2>
<p class="note">Relevance AUC (all prompts combined): <b>{fmt(summary['scoring']['relevance_auc'])}</b>
(0.5 = coin flip, 1.0 = perfect; needs --labels). Usefulness folds direction in: for an "interesting" prompt it's
the AUC, for a "boring" prompt it's 1 − AUC, so higher is always better. Spread = how much the prompt's score
varies across clips (near zero = prompt sees everything the same).</p>
<table><tr><th>Prompt</th><th>Type</th><th>AUC</th><th>Usefulness</th><th>Spread</th><th>Top 3 clips</th><th>Bottom 3 clips</th></tr>
{prompt_html}</table>
<h2>Contact sheets</h2><p class="note">Each cluster's highest-relevance clip is outlined and marked ★.</p>
{sheets}
</body></html>"""
    Path(path).write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="SightLine clustering + zero-shot scoring")
    ap.add_argument("clips", help="folder of clips (clip_id = file name)")
    ap.add_argument("--out", default="cluster_output")
    ap.add_argument("--embeddings", help="ML Build #1 embeddings: .npy (+ index CSV), .parquet, .npz or .csv")
    ap.add_argument("--index", help="index CSV for a .npy embeddings file (found automatically if next to it)")
    ap.add_argument("--labels", help="CSV with clip_id, interesting (1/0), location")
    ap.add_argument("--prompts", help="text file, one prompt per line starting with + or -")
    ap.add_argument("--frames", type=int, default=4, help="frames per clip to average (default 4, like Build #1)")
    ap.add_argument("--k-min", type=int, default=2)
    ap.add_argument("--k-max", type=int, default=12)
    ap.add_argument("--min-cluster-size", type=int, default=2, help="HDBSCAN smallest group")
    ap.add_argument("--primary", choices=["auto", "kmeans", "agglomerative", "hdbscan"], default="auto",
                    help="method used for the headline top-per-cluster list (auto = best silhouette)")
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="laion2b_s34b_b79k")
    ap.add_argument("--no-template", action="store_true", help="use prompts exactly as written")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = list_clips(args.clips)
    clip_ids = [f.name for f in files]
    print(f"Found {len(files)} clips.")

    # 1. frames + embeddings
    print("Reading frames...")
    frames = [read_frames(f, args.frames) for f in files]
    bad = [clip_ids[i] for i, fr in enumerate(frames) if not fr]
    if bad:
        sys.exit(f"Couldn't read frames from: {bad}")
    thumbs = [fr[len(fr) // 2] for fr in frames]

    model, preprocess, tokenizer, device = load_clip_model(args.model, args.pretrained)
    if args.embeddings:
        X = load_embeddings(args.embeddings, clip_ids, args.index)
        source = f"loaded from {args.embeddings}"
    else:
        print("Embedding frames...")
        flat = [im for fr in frames for im in fr]
        E = embed_images(model, preprocess, device, flat)
        X, k = [], 0
        for fr in frames:
            X.append(E[k:k + len(fr)].mean(0)); k += len(fr)
        X = l2norm(np.stack(X))
        source = f"CLIP {args.model}/{args.pretrained}, mean of {args.frames} frames per clip"
    np.savez(out / "embeddings.npz", clip_ids=np.array(clip_ids), embeddings=X)

    # 2. clustering
    print("Clustering...")
    results, sweep = run_clustering(X, args.k_min, args.k_max, args.min_cluster_size)
    interesting, location = read_labels(args.labels, set(clip_ids))
    methods = {}
    for name, r in results.items():
        methods[name] = {"k": r["k"], "silhouette": r["silhouette"], "noise": r.get("noise", 0),
                         "contiguity": contiguity(r["labels"]),
                         "location_ari": location_agreement(r["labels"], clip_ids, location)}
    if args.primary == "auto":
        scored = {n: m["silhouette"] for n, m in methods.items()
                  if not np.isnan(m["silhouette"]) and m["noise"] <= len(clip_ids) * 0.25}
        primary = max(scored, key=scored.get) if scored else "agglomerative"
    else:
        primary = args.primary

    # 3. zero-shot scoring
    prompts = read_prompts(args.prompts)
    texts = [p if args.no_template else TEMPLATE.format(p) for p, _ in prompts]
    T = embed_texts(model, tokenizer, device, texts)
    sims, relevance = zero_shot(X, T, [pol for _, pol in prompts])
    p_rows, overall = prompt_report(sims, prompts, relevance, clip_ids, interesting)

    # 4. top clip per cluster
    top_rows = []
    for name, r in results.items():
        lab = r["labels"]
        for g in sorted(set(lab) - {-1}):
            members = np.where(lab == g)[0]
            best = members[np.argmax(relevance[members])]
            top_rows.append({"method": name, "cluster": int(g), "size": len(members),
                             "clip_id": clip_ids[best], "relevance": f"{relevance[best]:.4f}"})

    # 5. outputs keyed by clip_id
    with open(out / "clips.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "cluster_kmeans", "cluster_agglomerative", "cluster_hdbscan", "relevance"]
                   + [f"sim: {p}" for p, _ in prompts])
        for i, cid in enumerate(clip_ids):
            w.writerow([cid] + [int(results[n]["labels"][i]) for n in ("kmeans", "agglomerative", "hdbscan")]
                       + [f"{relevance[i]:.4f}"] + [f"{s:.4f}" for s in sims[i]])
    with open(out / "top_per_cluster.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["method", "cluster", "size", "clip_id", "relevance"])
        w.writeheader(); w.writerows(top_rows)
    with open(out / "prompt_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(p_rows[0]))
        w.writeheader(); w.writerows(p_rows)
    if not (out / "labels_template.csv").exists():
        with open(out / "labels_template.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["clip_id", "interesting", "location"])
            for cid in clip_ids:
                w.writerow([cid, "", ""])

    def clean(v):
        return None if isinstance(v, float) and np.isnan(v) else v
    summary = {
        "n_clips": len(clip_ids), "embedding_source": source, "primary_method": primary,
        "methods": {n: {k: clean(v) for k, v in m.items()} for n, m in methods.items()},
        "silhouette_sweep": {k: [clean(x) for x in v] if k != "k" else v for k, v in sweep.items()},
        "scoring": {"relevance_auc": clean(overall["relevance_auc"]),
                    "labeled_clips": overall["labeled_clips"],
                    "prompt_template": None if args.no_template else TEMPLATE},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # 6. visuals
    print("Drawing contact sheets and map...")
    for name, r in results.items():
        title = f"{name}: k={r['k']}, silhouette={fmt(r['silhouette'])}"
        contact_sheet(thumbs, clip_ids, r["labels"], relevance, title, out / f"contact_{name}.png")
    xy, proj = projection_2d(X)
    summary["projection"] = proj
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_map(xy, proj, results, clip_ids, relevance, out / "umap.png")
    plot_silhouette(sweep, out / "silhouette.png")
    write_html(out / "report.html", out, summary, results, p_rows, top_rows, thumbs, clip_ids)

    # 7. console summary
    print("\nClustering (silhouette, higher = cleaner):")
    for n, m in methods.items():
        extra = f", noise={m['noise']}" if n == "hdbscan" else ""
        print(f"  {n:<14} k={m['k']:<3} silhouette={fmt(m['silhouette'])}  contiguity={fmt(m['contiguity'])}"
              f"  location ARI={fmt(m['location_ari'])}{extra}")
    print(f"  primary method: {primary}")
    print("\nPrompts (usefulness needs --labels; spread = how much the prompt varies across clips):")
    for p in sorted(p_rows, key=lambda r: -(r["usefulness"] if not np.isnan(r["usefulness"]) else r["spread"])):
        print(f"  [{p['type'][:4]}] usefulness={fmt(p['usefulness'])} spread={fmt(p['spread'], 3)}  {p['prompt']}")
    if not np.isnan(overall["relevance_auc"]):
        print(f"  combined relevance AUC = {overall['relevance_auc']:.2f}")
    else:
        print(f"  -> fill in {out / 'labels_template.csv'}, save it as labels.csv, rerun with --labels labels.csv")
    print(f"\nTop clip per cluster ({primary}):")
    for t in top_rows:
        if t["method"] == primary:
            print(f"  cluster {t['cluster']:<3} ({t['size']} clips)  {t['clip_id']}  relevance={float(t['relevance']):.2f}")
    print(f"\nDone. Open {out / 'report.html'}")


if __name__ == "__main__":
    main()
