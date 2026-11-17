# Run results

- Videos: 3 | footage: 3.4 min | windows scored: 41 | recap windows: 12
- Device: CPU
- Weights used: {'clip': 0.5, 'novelty': 0.2, 'quality': 0.3}

## Accuracy

- Spearman (score vs your rating): **0.893** over 41 rated windows
- Top-10 recall: **9/10** moments inside the 12 picked windows
- Missed: clip @ 2s

## Runtime

| Stage | Seconds |
|---|---|
| load_model | 4.6 |
| read_frames | 79.3 |
| quality | 0.1 |
| clip | 2.5 |
| rank_and_blend | 0.0 |
| select | 0.0 |
| **total** | **86.6** |

25.6 s of compute per minute of footage.
