"""
Tile a Sentinel-2 true-color GeoTIFF into georeferenced 64x64 patches, rendered
to MATCH EuroSAT's radiometry so the EuroSAT-trained classifier behaves correctly.

Why radiometric matching is essential
--------------------------------------
EuroSAT was built from hazier, less atmospherically-corrected Sentinel-2 imagery
(a noticeable blue cast; global RGB mean ~ (86, 97, 103)). A modern Copernicus
L2A composite is atmospherically corrected (haze removed), so a naive
reflectance->8-bit render looks washed-out/cyan to the model and forest gets
misclassified as water. We fix this with per-channel MOMENT MATCHING: linearly
rescale each channel of the scene so its mean/std match EuroSAT's global stats.
Each date is matched to the same EuroSAT reference, which also normalizes the two
dates to a common radiometry for fair change detection.

(Verified empirically: without matching, a 2016 Rondonia forest scene classified
as ~72% SeaLake; with matching, ~25% Forest + vegetation/pasture/crop, ~1% water.)

Input  : an RGB GeoTIFF with bands in order (B04=red, B03=green, B02=blue).
Output : an .npz with patches (N,64,64,3 uint8), (row,col) grid indices,
         geographic bounds, grid shape and CRS.
"""
import argparse

import numpy as np
import rasterio
from rasterio.windows import Window, bounds as window_bounds

PATCH = 64

# EuroSAT global per-channel (R,G,B) mean/std, measured over a 600-image sample
# spanning all 10 classes of the local EuroSAT_RGB dataset. This is the target
# radiometry every scene is matched to. (Recompute with tools/eurosat_stats if
# the dataset changes.)
EUROSAT_MEAN = np.array([86.4, 96.6, 103.2], dtype=np.float32)
EUROSAT_STD = np.array([49.7, 34.0, 29.2], dtype=np.float32)


def _moment_match(scene: np.ndarray) -> np.ndarray:
    """scene: (3,H,W) raw reflectance, natural R,G,B order. Return matched (3,H,W) uint8."""
    out = np.empty_like(scene, dtype=np.float32)
    flat = scene.reshape(3, -1)
    src_mean = flat.mean(1)
    src_std = flat.std(1)
    for c in range(3):
        out[c] = (scene[c] - src_mean[c]) / (src_std[c] + 1e-6) * EUROSAT_STD[c] + EUROSAT_MEAN[c]
    return np.clip(out, 0, 255).astype(np.uint8)


def patchify(tif_path: str, out_npz: str, stride: int = PATCH) -> None:
    with rasterio.open(tif_path) as src:
        if src.count < 3:
            raise ValueError(f"Expected >=3 bands (B04,B03,B02), got {src.count}")
        crs = str(src.crs)
        transform = src.transform
        scene = src.read([1, 2, 3]).astype(np.float32)  # (3,H,W) natural R,G,B

        matched = _moment_match(scene)                  # (3,H,W) uint8
        img = np.transpose(matched, (1, 2, 0))          # (H,W,3)

        # Slide a 64px (640m) window with the given stride. stride==PATCH gives
        # non-overlapping tiles; stride<PATCH oversamples for a finer change grid
        # while keeping the model's expected 640m footprint (no scale mismatch).
        row_starts = list(range(0, src.height - PATCH + 1, stride))
        col_starts = list(range(0, src.width - PATCH + 1, stride))
        n_rows, n_cols = len(row_starts), len(col_starts)
        patches, grid_rc, geo_bounds = [], [], []
        for r, y in enumerate(row_starts):
            for c, x in enumerate(col_starts):
                patches.append(img[y:y+PATCH, x:x+PATCH, :])
                grid_rc.append((r, c))
                win = Window(x, y, PATCH, PATCH)
                geo_bounds.append(window_bounds(win, transform))  # (left,bottom,right,top)

    np.savez_compressed(
        out_npz,
        patches=np.stack(patches).astype(np.uint8),
        grid_rc=np.array(grid_rc, dtype=np.int32),
        geo_bounds=np.array(geo_bounds, dtype=np.float64),
        grid_shape=np.array([n_rows, n_cols], dtype=np.int32),
        crs=np.array(crs),
    )
    print(f"Wrote {len(patches)} patches ({n_rows}x{n_cols} grid), EuroSAT-matched -> {out_npz}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tile + EuroSAT-match a Sentinel-2 RGB GeoTIFF.")
    ap.add_argument("tif", help="Path to RGB GeoTIFF (bands B04,B03,B02)")
    ap.add_argument("out", help="Output .npz path")
    ap.add_argument("--stride", type=int, default=PATCH,
                    help=f"Window stride in px (default {PATCH}=non-overlapping; 32=2x finer grid).")
    args = ap.parse_args()
    patchify(args.tif, args.out, args.stride)
