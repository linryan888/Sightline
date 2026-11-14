"""
Step 2: measure each window.

Two measurements come from here:
  quality  - how sharp the frames are (plain math on pixels, no model)
  clip     - how much the window looks like a "good moment" versus a "boring" one (CLIP)
CLIP also gives us an embedding (the 512-number fingerprint from SIG-22), which scoring.py
uses for the third signal, novelty.
"""

import cv2
import numpy as np


def sample_frames(cap, fps, start, end, n, long_side):
    """Grab n frames from one window: the middle of n equal slices (skips blurry first/last frames).
    Frames are shrunk so the longer side is `long_side` pixels, so every video is judged at the
    same resolution. Returns a list of BGR frames (may be shorter than n if a read fails)."""
    frames = []
    slice_len = (end - start) / n
    for k in range(n):
        t = start + (k + 0.5) * slice_len
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))   # jump straight to that frame
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = long_side / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        frames.append(frame)
    return frames


def sharpness(frames):
    """Variance of the Laplacian, a standard blur measure.
    The Laplacian highlights edges (places where brightness changes fast). A sharp frame has strong
    edges so the variance is high; a blurry or dark frame is flat so it is low.
    We take the median over the window's frames, then log1p so huge values don't dominate."""
    values = []
    for f in frames:
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        values.append(cv2.Laplacian(gray, cv2.CV_64F).var())
    return float(np.log1p(np.median(values)))


class ClipScorer:
    """Loads CLIP once and reuses it for every window."""

    def __init__(self, cfg_clip, random_init=False):
        import open_clip
        import torch

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        pretrained = None if random_init else cfg_clip["pretrained"]   # random_init is for testing only
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            cfg_clip["model"], pretrained=pretrained, device=self.device)
        self.model.eval()                                  # inference mode, not training
        tokenizer = open_clip.get_tokenizer(cfg_clip["model"])
        with torch.no_grad():
            self.pos = self._encode_text(tokenizer, cfg_clip["positive_prompts"])
            self.neg = self._encode_text(tokenizer, cfg_clip["negative_prompts"])

    def _encode_text(self, tokenizer, prompts):
        """Prompts -> unit-length 512-number vectors, shape (n_prompts, 512)."""
        torch = self.torch
        vecs = self.model.encode_text(tokenizer(prompts).to(self.device)).float()
        return torch.nn.functional.normalize(vecs, dim=-1).cpu().numpy()

    def embed(self, frames_bgr):
        """One unit-length 512-number fingerprint for the window: embed each frame, average, rescale."""
        from PIL import Image
        torch = self.torch
        batch = torch.stack([
            self.preprocess(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))   # BGR -> RGB -> PIL
            for f in frames_bgr
        ]).to(self.device)
        with torch.no_grad():
            vecs = self.model.encode_image(batch).float()
            vecs = torch.nn.functional.normalize(vecs, dim=-1)
        mean = vecs.mean(dim=0)
        mean = mean / (mean.norm() + 1e-8)
        return mean.cpu().numpy()

    def prompt_score(self, emb):
        """How much closer the window is to its best 'good moment' prompt than to its best 'boring' prompt.
        Positive = looks like a good moment, negative = looks boring. Both vectors have length 1,
        so the dot product is the cosine similarity."""
        return float((emb @ self.pos.T).max() - (emb @ self.neg.T).max())
