# CLIP clustering + zero-shot scoring (ML Build #2, SIG-23)

Groups clips by scene/location using CLIP embeddings and gives each clip a first
zero-shot relevance score. All outputs are keyed by `clip_id` (the clip's file name).

## Setup

```
python -m pip install -r requirements.txt
```

## Run

```
python sightline_cluster.py <clips_folder>                          # embeds clips itself
python sightline_cluster.py <clips_folder> --labels labels.csv      # + prompt AUCs and location agreement
python sightline_cluster.py <clips_folder> --embeddings emb.npy     # reuse ML Build #1 output (.npy + index CSV, .parquet, .npz, .csv)
python sightline_cluster.py <clips_folder> --prompts prompts.txt    # custom prompts, one per line starting with + or -
```

`labels.csv` columns: `clip_id, interesting (1/0), location`. The first run writes a blank
`cluster_output/labels_template.csv` to fill in.

To make a test set from longer phone videos (5-second clips, named in time order):

```
python split_clips.py raw_videos clips
```

## Outputs (`cluster_output/`)

| File | Contents |
|---|---|
| `clips.csv` | per `clip_id`: cluster for k-means / agglomerative / HDBSCAN, relevance, similarity to each prompt |
| `top_per_cluster.csv` | highest-relevance clip in each cluster, per method |
| `prompt_report.csv` | per prompt: AUC vs. labels, usefulness, spread, top/bottom clips |
| `summary.json` | silhouette scores, chosen k, contiguity, location ARI, relevance AUC |
| `contact_<method>.png` | thumbnails grouped by cluster |
| `umap.png`, `silhouette.png` | 2D map of embeddings; silhouette vs. k |
| `report.html` | everything in one page |
| `embeddings.npz` | `clip_ids` + `embeddings` |

## Method

- Embeddings: CLIP ViT-B/32 (`open_clip`, LAION-2B weights), mean of 4 evenly spaced frames, L2-normalized.
- Clustering: k-means and agglomerative (cosine, average linkage) swept over k = 2..12, k chosen by
  silhouette (cosine); HDBSCAN picks its own k and can mark clips as noise.
- Extra checks: contiguity (share of back-to-back clips in the same cluster) and adjusted Rand index
  against hand-labelled locations.
- Zero-shot relevance: softmax over all prompts (logit scale 100); relevance = probability mass on
  "interesting" prompts. Prompts are wrapped as "a first-person photo of …" (`--no-template` to disable).
