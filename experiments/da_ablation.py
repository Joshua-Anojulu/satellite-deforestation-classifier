"""
Controlled, labeled domain-adaptation ablation.

Problem: we have no labeled Sentinel-2 ground truth, so we cannot directly measure
how well each adaptation method recovers accuracy on the real target domain. We
therefore construct a CONTROLLED domain shift: take the held-out, labeled EuroSAT
RGB test set and apply a realistic, NONLINEAR radiometric corruption that mimics
the measured EuroSAT->L2A gap (per-channel gamma + gain + offset + blue/red haze).
Because the shift is nonlinear, a per-channel linear method cannot trivially invert
it, so the comparison between methods is meaningful.

We then evaluate the RGB classifier under five conditions:
  clean            - upper bound (no shift)
  shifted, none    - lower bound (shift, no adaptation)
  shifted, moment  - per-channel mean/std matching to EuroSAT global stats
  shifted, hist    - per-channel histogram (CDF) matching to an EuroSAT reference
  shifted, adabn   - recompute BatchNorm running stats on the shifted domain

Run:  python -m experiments.da_ablation
"""
import copy

import numpy as np
import torch
from PIL import Image

import config
from src.data import build_datasets, build_transforms
from src.model import build_model
from src.utils import get_device, set_seed

# Synthetic shift parameters (R,G,B), tuned to mimic the real EuroSAT->L2A gap
# observed on Sentinel-2 (haze removed -> less blue, relatively more red, mild
# contrast/gamma change). Applied to uint8 images in [0,255].
GAMMA = np.array([0.85, 1.00, 1.20])   # per-channel gamma (nonlinear)
GAIN = np.array([1.25, 1.05, 0.80])    # per-channel multiplicative gain
OFFSET = np.array([8.0, 2.0, -10.0])   # per-channel additive offset
HAZE = np.array([-12.0, -4.0, 6.0])    # subtract blue haze / add warmth (approx)


def apply_shift(img_u8: np.ndarray) -> np.ndarray:
    """img_u8: (H,W,3) uint8 -> shifted (H,W,3) uint8."""
    x = img_u8.astype(np.float32)
    x = ((x / 255.0) ** GAMMA) * 255.0
    x = x * GAIN + OFFSET + HAZE
    return np.clip(x, 0, 255).astype(np.uint8)


def moment_match(img_u8, tgt_mean, tgt_std):
    x = img_u8.astype(np.float32)
    m = x.reshape(-1, 3).mean(0); s = x.reshape(-1, 3).std(0) + 1e-6
    x = (x - m) / s * tgt_std + tgt_mean
    return np.clip(x, 0, 255).astype(np.uint8)


def hist_match(img_u8, ref_cdfs):
    """Per-channel CDF matching to reference CDFs (list of 3 arrays len 256)."""
    out = np.empty_like(img_u8)
    for c in range(3):
        src = img_u8[..., c].ravel()
        hist = np.bincount(src, minlength=256).astype(np.float64)
        src_cdf = np.cumsum(hist) / hist.sum()
        lut = np.interp(src_cdf, ref_cdfs[c], np.arange(256)).astype(np.uint8)
        out[..., c] = lut[img_u8[..., c]]
    return out


def _eval(model, imgs_u8, labels, tf, device):
    model.eval()
    preds = []
    with torch.no_grad():
        for k in range(0, len(imgs_u8), 256):
            batch = imgs_u8[k:k+256]
            t = torch.stack([tf(Image.fromarray(im)) for im in batch]).to(device)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                out = model(t)
            preds.extend(out.argmax(1).cpu().numpy())
    return (np.array(preds) == labels).mean()


def _adabn_eval(model, imgs_u8, labels, tf, device):
    """Recompute BatchNorm running stats on the (shifted) domain, then evaluate."""
    m = copy.deepcopy(model)
    for mod in m.modules():
        if isinstance(mod, torch.nn.BatchNorm2d):
            mod.reset_running_stats()
            mod.momentum = None  # cumulative average -> exact domain stats
    m.train()
    with torch.no_grad():
        for k in range(0, len(imgs_u8), 256):
            batch = imgs_u8[k:k+256]
            t = torch.stack([tf(Image.fromarray(im)) for im in batch]).to(device)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                m(t)
    return _eval(m, imgs_u8, labels, tf, device)


def main():
    set_seed(config.SEED)
    device = get_device()
    _, eval_tf = build_transforms()

    # Held-out labeled EuroSAT test set as uint8 RGB.
    _, _, test_ds = build_datasets()
    base, idx = test_ds.base, test_ds.indices
    imgs, labels = [], []
    for i in idx:
        path, lab = base.samples[i]
        imgs.append(np.array(base.loader(path).convert("RGB"))); labels.append(lab)
    labels = np.array(labels)
    print(f"Test images: {len(imgs)}")

    # Reference stats / CDFs from clean EuroSAT (source domain).
    clean_stack = np.stack(imgs).reshape(-1, 3)
    tgt_mean = clean_stack.mean(0); tgt_std = clean_stack.std(0)
    ref_cdfs = []
    for c in range(3):
        h = np.bincount(np.stack(imgs)[..., c].ravel(), minlength=256).astype(np.float64)
        ref_cdfs.append(np.cumsum(h) / h.sum())

    shifted = [apply_shift(im) for im in imgs]

    model = build_model().to(device)
    ck = torch.load(config.BEST_CKPT, map_location=device)
    model.load_state_dict(ck["model_state"])

    results = {}
    results["clean (upper bound)"] = _eval(model, imgs, labels, eval_tf, device)
    results["shifted, no adaptation"] = _eval(model, shifted, labels, eval_tf, device)
    results["shifted, moment match"] = _eval(model, [moment_match(im, tgt_mean, tgt_std) for im in shifted], labels, eval_tf, device)
    results["shifted, histogram match"] = _eval(model, [hist_match(im, ref_cdfs) for im in shifted], labels, eval_tf, device)
    results["shifted, AdaBN"] = _adabn_eval(model, shifted, labels, eval_tf, device)

    print("\nDomain-adaptation ablation (EuroSAT RGB classifier, controlled shift):")
    print(f"  {'condition':28s}  accuracy   recovery")
    base_acc = results["clean (upper bound)"]; low = results["shifted, no adaptation"]
    import json
    for k, v in results.items():
        rec = "" if k.startswith("clean") else f"{(v-low)/(base_acc-low)*100:5.1f}% of gap"
        print(f"  {k:28s}   {v:.4f}    {rec}")
    with open(config.OUTPUT_DIR / "da_ablation.json", "w") as f:
        json.dump({k: float(v) for k, v in results.items()}, f, indent=2)
    print(f"\nSaved -> {config.OUTPUT_DIR / 'da_ablation.json'}")


if __name__ == "__main__":
    main()
