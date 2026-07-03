"""
NDVI-difference deforestation baseline (standard non-ML method).

For two-date 4-band scenes (B04=red, B03=green, B02=blue, B08=NIR), compute
NDVI = (NIR - Red) / (NIR + Red) per pixel, aggregate to the SAME 64px /
stride-32 grid used by the CNN pipeline (mean NDVI per cell), and flag a cell as
deforestation if it was forest-like in 2016 (NDVI_A >= forest_thr) and its NDVI
dropped by more than drop_thr by 2024. Output is a change-mask .npz compatible
with validate_gfw.py, so the baseline is benchmarked against Global Forest Watch
exactly like the CNN.

Run:  python -m deforestation.ndvi_baseline <A_4band.tif> <B_4band.tif> <out_mask.npz>
"""
import argparse

import numpy as np
import rasterio
from rasterio.windows import Window, bounds as window_bounds

PATCH, STRIDE = 64, 32


def _otsu(values: np.ndarray) -> float:
    """Otsu's threshold on a 1-D array (maximize between-class variance).

    Used to pick a per-scene 'forest' NDVI cutoff instead of a fixed constant, so
    the baseline adapts to biome phenology (e.g. dry/deciduous forest has lower
    NDVI than wet evergreen forest and would be missed by a fixed 0.6 threshold).
    """
    v = values[np.isfinite(values)]
    hist, edges = np.histogram(v, bins=256, range=(-0.2, 1.0))
    hist = hist.astype(np.float64)
    w = hist.sum()
    if w == 0:
        return 0.6
    p = hist / w
    centers = (edges[:-1] + edges[1:]) / 2
    omega = np.cumsum(p)
    mu = np.cumsum(p * centers)
    mu_t = mu[-1]
    denom = omega * (1 - omega)
    denom[denom == 0] = 1e-12
    sigma_b2 = (mu_t * omega - mu) ** 2 / denom
    return float(centers[np.argmax(sigma_b2)])


def _ndvi(path):
    with rasterio.open(path) as s:
        red = s.read(1).astype(np.float32)
        nir = s.read(4).astype(np.float32)
        transform, crs = s.transform, str(s.crs)
        H, W = s.height, s.width
    ndvi = (nir - red) / (nir + red + 1e-6)
    return ndvi, transform, crs, H, W


def baseline(tif_a, tif_b, out_npz, forest_thr=None, drop_thr=0.2):
    """forest_thr=None -> pick it per-scene with Otsu (clamped to [0.35,0.70]) so
    the baseline is fair across biomes. Pass a float to force a fixed threshold."""
    na, transform, crs, H, W = _ndvi(tif_a)
    nb, *_ = _ndvi(tif_b)

    rows = list(range(0, H - PATCH + 1, STRIDE))
    cols = list(range(0, W - PATCH + 1, STRIDE))
    n_rows, n_cols = len(rows), len(cols)
    meanA = np.zeros((n_rows, n_cols), np.float32)
    meanB = np.zeros((n_rows, n_cols), np.float32)
    grid_rc, geo_bounds = [], []
    for r, y in enumerate(rows):
        for c, x in enumerate(cols):
            meanA[r, c] = na[y:y+PATCH, x:x+PATCH].mean()
            meanB[r, c] = nb[y:y+PATCH, x:x+PATCH].mean()
            grid_rc.append((r, c))
            geo_bounds.append(window_bounds(Window(x, y, PATCH, PATCH), transform))

    if forest_thr is None:
        forest_thr = float(np.clip(_otsu(meanA.ravel()), 0.35, 0.70))
        thr_src = "Otsu (adaptive)"
    else:
        thr_src = "fixed"
    was_forest = meanA >= forest_thr
    change = was_forest & ((meanA - meanB) >= drop_thr)
    print(f"NDVI baseline: forest cells {int(was_forest.sum())}, "
          f"loss cells {int(change.sum())} (forest_thr={forest_thr:.3f} [{thr_src}], drop={drop_thr})")

    np.savez_compressed(
        out_npz, change=change, was_forest=was_forest,
        grid_shape=np.array([n_rows, n_cols]),
        geo_bounds=np.array(geo_bounds, dtype=np.float64),
        grid_rc=np.array(grid_rc, dtype=np.int32), crs=np.array(crs))
    print(f"Wrote -> {out_npz}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tif_a"); ap.add_argument("tif_b"); ap.add_argument("out")
    ap.add_argument("--forest-thr", type=float, default=None,
                    help="Fixed forest NDVI threshold; omit for per-scene Otsu (adaptive).")
    ap.add_argument("--drop-thr", type=float, default=0.2)
    args = ap.parse_args()
    baseline(args.tif_a, args.tif_b, args.out, args.forest_thr, args.drop_thr)
