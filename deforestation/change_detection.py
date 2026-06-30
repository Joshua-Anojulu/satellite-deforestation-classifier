"""
Compare two land-cover grids (year A vs year B) and flag deforestation:
cells classified Forest in A but a deforestation-target class in B.

Outputs:
  * a change-map PNG (paper figure)
  * a CSV of detected events with geographic centroids (lon/lat or CRS coords)
  * an .npz boolean change mask aligned to the grid (for GFW validation)
"""
import argparse
import csv
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

FOREST_IDX = [config.CLASS_NAMES.index(c) for c in config.FOREST_CLASSES]
TARGET_IDX = [config.CLASS_NAMES.index(c) for c in config.DEFORESTATION_TARGETS]


def detect(grid_a_npz: str, grid_b_npz: str, out_prefix: str, min_conf: float = 0.0) -> None:
    a = np.load(grid_a_npz, allow_pickle=True)
    b = np.load(grid_b_npz, allow_pickle=True)
    if not np.array_equal(a["grid_shape"], b["grid_shape"]):
        raise ValueError("Grid shapes differ; the two dates must cover the same extent/grid.")

    la, lb = a["label_grid"], b["label_grid"]
    ca, cb = a["conf_grid"], b["conf_grid"]

    was_forest = np.isin(la, FOREST_IDX) & (ca >= min_conf)
    became_target = np.isin(lb, TARGET_IDX) & (cb >= min_conf)
    change = was_forest & became_target

    n_change = int(change.sum())
    n_forest_a = int(was_forest.sum())
    print(f"Forest cells in A: {n_forest_a}")
    print(f"Forest->non-forest (deforestation) cells: {n_change} "
          f"({100*n_change/max(n_forest_a,1):.1f}% of A's forest)")

    # Map grid cells -> geographic centroids using per-cell bounds.
    bounds_by_rc = {(int(r), int(c)): tuple(bnd)
                    for (r, c), bnd in zip(a["grid_rc"], a["geo_bounds"])}
    rows, cols = np.where(change)
    out_prefix = Path(out_prefix)
    csv_path = out_prefix.with_name(out_prefix.name + "_events.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row", "col", "centroid_x", "centroid_y", "from_class", "to_class", "crs"])
        for r, c in zip(rows, cols):
            left, bottom, right, top = bounds_by_rc[(int(r), int(c))]
            w.writerow([int(r), int(c), (left + right) / 2, (bottom + top) / 2,
                        config.CLASS_NAMES[la[r, c]], config.CLASS_NAMES[lb[r, c]], str(a["crs"])])

    # Change-map figure: forest (green), loss (red), other (grey).
    rgb = np.full((*la.shape, 3), 0.85, dtype=np.float32)
    rgb[was_forest] = [0.1, 0.5, 0.1]
    rgb[change] = [0.85, 0.1, 0.1]
    plt.figure(figsize=(8, 8))
    plt.imshow(rgb)
    plt.title(f"Detected forest loss (red): {n_change} cells")
    plt.axis("off")
    fig_path = out_prefix.with_name(out_prefix.name + "_changemap.png")
    plt.tight_layout()
    plt.savefig(fig_path, dpi=150)

    np.savez_compressed(out_prefix.with_name(out_prefix.name + "_mask.npz"),
                        change=change, was_forest=was_forest,
                        grid_shape=a["grid_shape"], geo_bounds=a["geo_bounds"],
                        grid_rc=a["grid_rc"], crs=a["crs"])
    print(f"Wrote events CSV -> {csv_path}")
    print(f"Wrote change map  -> {fig_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Detect Forest->non-Forest change between two dates.")
    ap.add_argument("grid_a", help="Land-cover .npz for the EARLIER date")
    ap.add_argument("grid_b", help="Land-cover .npz for the LATER date")
    ap.add_argument("out_prefix", help="Output path prefix (no extension)")
    ap.add_argument("--min-conf", type=float, default=0.0,
                    help="Ignore predictions below this softmax confidence.")
    args = ap.parse_args()
    detect(args.grid_a, args.grid_b, args.out_prefix, args.min_conf)
