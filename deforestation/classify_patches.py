"""
Classify every patch from patchify.py with the EuroSAT-trained model and build
a land-cover grid.

Output .npz contains:
  label_grid : (n_rows, n_cols) int  predicted class index per cell (-1 = empty)
  conf_grid  : (n_rows, n_cols) float softmax confidence of the predicted class
  grid_shape, geo_bounds, grid_rc, crs : passed through for mapping/validation
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path
import config
from src.model import build_model
from src.data import build_transforms
from src.utils import get_device


def classify(patches_npz: str, out_npz: str, batch_size: int = 128) -> None:
    device = get_device()
    if not config.BEST_CKPT.exists():
        raise FileNotFoundError(f"No checkpoint at {config.BEST_CKPT}. Train the classifier first.")

    model = build_model().to(device)
    ckpt = torch.load(config.BEST_CKPT, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    _, eval_transform = build_transforms()  # same preprocessing as training/eval

    data = np.load(patches_npz, allow_pickle=True)
    patches = data["patches"]            # (N,64,64,3) uint8
    n_rows, n_cols = data["grid_shape"]

    preds = np.empty(len(patches), dtype=np.int64)
    confs = np.empty(len(patches), dtype=np.float32)

    with torch.no_grad():
        for start in range(0, len(patches), batch_size):
            chunk = patches[start:start + batch_size]
            tensors = torch.stack([eval_transform(Image.fromarray(p)) for p in chunk]).to(device)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                logits = model(tensors)
            probs = torch.softmax(logits.float(), dim=1)
            conf, pred = probs.max(dim=1)
            preds[start:start + len(chunk)] = pred.cpu().numpy()
            confs[start:start + len(chunk)] = conf.cpu().numpy()

    label_grid = -np.ones((n_rows, n_cols), dtype=np.int64)
    conf_grid = np.zeros((n_rows, n_cols), dtype=np.float32)
    for (r, c), p, cf in zip(data["grid_rc"], preds, confs):
        label_grid[r, c] = p
        conf_grid[r, c] = cf

    np.savez_compressed(
        out_npz,
        label_grid=label_grid, conf_grid=conf_grid,
        grid_shape=data["grid_shape"], geo_bounds=data["geo_bounds"],
        grid_rc=data["grid_rc"], crs=data["crs"],
    )
    counts = {config.CLASS_NAMES[i]: int((preds == i).sum()) for i in range(config.NUM_CLASSES)}
    print(f"Classified {len(patches)} patches -> {out_npz}")
    for name, n in counts.items():
        print(f"  {name:22s}: {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Classify Sentinel-2 patches into a land-cover grid.")
    ap.add_argument("patches_npz", help="Output of patchify.py")
    ap.add_argument("out", help="Output land-cover .npz")
    ap.add_argument("--batch-size", type=int, default=128)
    args = ap.parse_args()
    classify(args.patches_npz, args.out, args.batch_size)
