"""General pixel-center Hansen reference builder kept separate from the detector paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds, intersection

from .hansen import pixel_center_indices


def build_reference(cell_bounds: np.ndarray, cell_crs: str, gfc_path: str,
                    band: str = "lossyear", value_lo: int | None = None,
                    value_hi: int | None = None, min_fraction: float = 0.0
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate any Hansen band/window with explicit L6 center inclusion.

    The interval is ``(value_lo, value_hi]`` when bounds are supplied.  With no
    value bounds, nonzero band values are counted.  Fractions and thresholded
    booleans are returned so callers can audit the exact numerator.
    """
    bounds = np.asarray(cell_bounds, dtype=float)
    if bounds.ndim != 2 or bounds.shape[1] != 4:
        raise ValueError("cell_bounds must be N x (left,bottom,right,top).")
    with rasterio.open(gfc_path) as source:
        projected = np.asarray([
            transform_bounds(cell_crs, source.crs, *cell, densify_pts=5) for cell in bounds
        ])
        union = (projected[:, 0].min(), projected[:, 1].min(),
                 projected[:, 2].max(), projected[:, 3].max())
        floating = from_bounds(*union, source.transform)
        col0 = int(np.floor(floating.col_off)); row0 = int(np.floor(floating.row_off))
        col1 = int(np.ceil(floating.col_off + floating.width))
        row1 = int(np.ceil(floating.row_off + floating.height))
        window = intersection(
            Window(col0, row0, col1 - col0, row1 - row0),
            Window(0, 0, source.width, source.height),
        )
        values = source.read(1, window=window)
        transform = source.window_transform(window)
        fractions = np.zeros(len(bounds), dtype=np.float64)
        for index, cell in enumerate(projected):
            rows, cols = pixel_center_indices(transform, values.shape, tuple(cell))
            if rows.size == 0 or cols.size == 0:
                continue
            block = values[np.ix_(rows, cols)]
            if value_lo is None and value_hi is None:
                selected = block != 0
            else:
                lower = -np.inf if value_lo is None else value_lo
                upper = np.inf if value_hi is None else value_hi
                selected = (block > lower) & (block <= upper)
            fractions[index] = float(selected.mean())
    hits = fractions > 0 if min_fraction <= 0 else fractions >= min_fraction
    return hits, fractions


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a generalized pixel-center Hansen reference.")
    parser.add_argument("grid_npz", type=Path, help="NPZ containing cell_bounds and crs")
    parser.add_argument("gfc")
    parser.add_argument("--band", default="lossyear")
    parser.add_argument("--lo", type=int)
    parser.add_argument("--hi", type=int)
    parser.add_argument("--min-fraction", type=float, default=0.0)
    args = parser.parse_args()
    data = np.load(args.grid_npz, allow_pickle=True)
    hits, fractions = build_reference(
        data["cell_bounds"], str(data["crs"]), args.gfc,
        args.band, args.lo, args.hi, args.min_fraction,
    )
    print(f"Reference positives: {int(hits.sum())}/{len(hits)}; mean fraction={fractions.mean():.6f}")


if __name__ == "__main__":
    main()

