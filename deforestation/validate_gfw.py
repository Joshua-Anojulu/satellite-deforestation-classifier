"""
Validate detected forest loss against Global Forest Watch / Hansen Global Forest
Change (GFC) "lossyear" data.

The GFC lossyear raster encodes, per ~30 m pixel, the year of tree-cover loss
(0 = no loss, 1 = 2001, ... , N = 2000+N). We aggregate it onto our 64x64 patch
grid: a cell is a reference "loss" if ANY GFC pixel inside it has a loss year in
(year_a, year_b]. Then we compare to the model's detected change mask ->
precision / recall / F1 / IoU. That agreement is the paper's core quantitative
result.

By default it streams the correct 10x10-degree GFC tile directly from Google
Storage (no full download) and reads only the small window covering the scene.

Run:
    python -m deforestation.validate_gfw <change_mask.npz> --year-a 2016 --year-b 2024
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Default GFC tile covering Rondonia study area (00N_070W = covers 0..10S, 70..60W).
DEFAULT_GFC = ("/vsicurl/https://storage.googleapis.com/earthenginepartners-hansen/"
               "GFC-2024-v1.12/Hansen_GFC-2024-v1.12_lossyear_00N_070W.tif")


def align_and_score(change_mask_npz: str, gfc_path: str, year_a: int, year_b: int,
                    out_json: str = None, min_loss_frac: float = 0.0) -> dict:
    data = np.load(change_mask_npz, allow_pickle=True)
    change = data["change"].astype(bool)
    n_rows, n_cols = int(data["grid_shape"][0]), int(data["grid_shape"][1])
    grid_rc = data["grid_rc"]
    geo_bounds = data["geo_bounds"]
    scene_crs = str(data["crs"])
    lo, hi = (year_a - 2000), (year_b - 2000)  # GFC lossyear encoding

    # Overall scene bounds in scene CRS.
    left = geo_bounds[:, 0].min(); bottom = geo_bounds[:, 1].min()
    right = geo_bounds[:, 2].max(); top = geo_bounds[:, 3].max()

    ref = np.zeros((n_rows, n_cols), dtype=bool)
    with rasterio.open(gfc_path) as gfc:
        # Read just the window covering the scene (one streamed read).
        gl, gb, gr, gt = transform_bounds(scene_crs, gfc.crs, left, bottom, right, top)
        win = from_bounds(gl, gb, gr, gt, gfc.transform)
        sub = gfc.read(1, window=win)
        sub_tf = gfc.window_transform(win)
        Hs, Ws = sub.shape

        for (r, c), (cl, cb, cr_, ct) in zip(grid_rc, geo_bounds):
            # Project this cell's bounds to GFC CRS, then to sub-array pixel indices.
            wl, wb, wr, wt = transform_bounds(scene_crs, gfc.crs, cl, cb, cr_, ct)
            r0, c0 = rowcol(sub_tf, wl, wt)   # top-left pixel
            r1, c1 = rowcol(sub_tf, wr, wb)   # bottom-right pixel
            r0, r1 = sorted((max(0, r0), min(Hs, r1)))
            c0, c1 = sorted((max(0, c0), min(Ws, c1)))
            block = sub[r0:r1, c0:c1]
            if block.size:
                loss_frac = ((block > lo) & (block <= hi)).mean()
                # A reference "loss cell" requires at least min_loss_frac of its
                # GFC pixels lost in-window, matching the patch-scale (whole 640 m
                # cell) change the model can detect. min_loss_frac=0 -> any pixel.
                if loss_frac > min_loss_frac:
                    ref[int(r), int(c)] = True

    tp = int((change & ref).sum())
    fp = int((change & ~ref).sum())
    fn = int((~change & ref).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    result = {
        "year_a": year_a, "year_b": year_b, "min_loss_frac": min_loss_frac,
        "model_detected_cells": int(change.sum()),
        "gfw_reference_cells": int(ref.sum()),
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4), "iou": round(iou, 4),
    }
    print("Validation vs Global Forest Watch (Hansen GFC lossyear):")
    for k, v in result.items():
        print(f"  {k:22s}: {v}")
    if out_json:
        with open(out_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved -> {out_json}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Validate change mask vs Hansen GFC lossyear.")
    ap.add_argument("change_mask_npz", help="*_mask.npz from change_detection.py")
    ap.add_argument("--gfc", default=DEFAULT_GFC,
                    help="GFC lossyear raster (local path or /vsicurl URL). Default: 00N_070W tile.")
    ap.add_argument("--year-a", type=int, required=True, help="Earlier year, e.g. 2016")
    ap.add_argument("--year-b", type=int, required=True, help="Later year, e.g. 2024")
    ap.add_argument("--out-json", default=None, help="Optional path to save result JSON")
    ap.add_argument("--min-loss-frac", type=float, default=0.0,
                    help="Min fraction of a cell's GFC pixels lost to count as reference loss (0=any).")
    args = ap.parse_args()
    align_and_score(args.change_mask_npz, args.gfc, args.year_a, args.year_b,
                    args.out_json, args.min_loss_frac)
