"""Master-grid creation and alignment checks for five-year trajectories."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from affine import Affine
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, bounds as window_bounds

from .config import (
    BOA_ADD_OFFSET_BASELINE_04,
    BOA_QUANTIFICATION_VALUE,
    PATCH_PIXELS,
    REFERENCE_YEAR,
    STRIDE_PIXELS,
    assert_feature_years,
)


@dataclass(frozen=True)
class MasterGrid:
    crs: str
    transform: Affine
    height: int
    width: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width


def master_grid(path_2020: str | Path) -> MasterGrid:
    with rasterio.open(path_2020) as dataset:
        transform = dataset.transform
        if not (np.isclose(abs(transform.a), 10.0) and np.isclose(abs(transform.e), 10.0)
                and np.isclose(transform.b, 0.0) and np.isclose(transform.d, 0.0)):
            raise AssertionError(f"Master raster is not an unrotated 10 m grid: {transform}")
        return MasterGrid(str(dataset.crs), transform, dataset.height, dataset.width)


def assert_aligned(grids: Iterable[MasterGrid]) -> None:
    grids = list(grids)
    if not grids:
        raise ValueError("No grids supplied.")
    first = grids[0]
    for grid in grids[1:]:
        if grid != first:
            raise AssertionError(f"Trajectory grid mismatch: {first} != {grid}")


def _to_rho(values: np.ndarray, convention: str) -> np.ndarray:
    if convention == "already_reflectance":
        return values
    if convention == "already_offset_integer_scaled":
        return values / BOA_QUANTIFICATION_VALUE
    if convention == "raw_baseline04_dn":
        return (values + BOA_ADD_OFFSET_BASELINE_04) / BOA_QUANTIFICATION_VALUE
    raise ValueError(convention)


def warp_reflectance(path: str | Path, master: MasterGrid,
                     convention: str = "already_offset_integer_scaled") -> tuple[np.ndarray, tuple[str, ...]]:
    """Convert to rho first, then apply only the locked bilinear reprojection."""
    with rasterio.open(path) as source:
        destination = np.full((source.count, *master.shape), np.nan, dtype=np.float32)
        for band in range(source.count):
            values = source.read(band + 1).astype(np.float32)
            if source.nodata is not None:
                values[values == source.nodata] = np.nan
            values = _to_rho(values, convention)
            reproject(
                source=values, destination=destination[band],
                src_transform=source.transform, src_crs=source.crs,
                dst_transform=master.transform, dst_crs=master.crs,
                src_nodata=np.nan, dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
        names = tuple(name or f"band_{i}" for i, name in enumerate(source.descriptions, 1))
    return destination, names


def warp_categorical(path: str | Path, master: MasterGrid) -> np.ndarray:
    """Nearest-neighbour is reserved for categorical/boolean layers such as SCL."""
    with rasterio.open(path) as source:
        destination = np.zeros(master.shape, dtype=source.dtypes[0])
        reproject(
            source=rasterio.band(source, 1), destination=destination,
            src_transform=source.transform, src_crs=source.crs,
            dst_transform=master.transform, dst_crs=master.crs,
            src_nodata=source.nodata, dst_nodata=0,
            resampling=Resampling.nearest,
        )
    return destination


def cell_grid(master: MasterGrid, analysis_bounds_wgs84: tuple[float, float, float, float]
              ) -> dict[str, np.ndarray]:
    """Build non-overlapping 64x64 cells and flag the unbuffered interior."""
    rows = list(range(0, master.height - PATCH_PIXELS + 1, STRIDE_PIXELS))
    cols = list(range(0, master.width - PATCH_PIXELS + 1, STRIDE_PIXELS))
    analysis = transform_bounds("EPSG:4326", master.crs, *analysis_bounds_wgs84, densify_pts=21)
    rc, pixel_windows, bounds, interior = [], [], [], []
    for grid_row, row in enumerate(rows):
        for grid_col, col in enumerate(cols):
            window = Window(col, row, PATCH_PIXELS, PATCH_PIXELS)
            left, bottom, right, top = window_bounds(window, master.transform)
            rc.append((grid_row, grid_col))
            pixel_windows.append((row, col, PATCH_PIXELS, PATCH_PIXELS))
            bounds.append((left, bottom, right, top))
            interior.append(
                left >= analysis[0] and bottom >= analysis[1]
                and right <= analysis[2] and top <= analysis[3]
            )
    return {
        "grid_rc": np.asarray(rc, dtype=np.int32),
        "pixel_windows": np.asarray(pixel_windows, dtype=np.int32),
        "cell_bounds": np.asarray(bounds, dtype=np.float64),
        "interior": np.asarray(interior, dtype=bool),
        "grid_shape": np.asarray((len(rows), len(cols)), dtype=np.int32),
    }


def load_trajectory(paths: dict[int, str | Path],
                    convention: str = "already_offset_integer_scaled") -> tuple[MasterGrid, dict[int, np.ndarray], tuple[str, ...]]:
    years = assert_feature_years(paths.keys())
    if set(years) != set(range(2016, 2021)):
        raise ValueError("The locked trajectory requires all five years 2016--2020.")
    master = master_grid(paths[REFERENCE_YEAR])
    arrays: dict[int, np.ndarray] = {}
    names: tuple[str, ...] | None = None
    for year in sorted(paths):
        array, current_names = warp_reflectance(paths[year], master, convention)
        names = names or current_names
        if current_names != names:
            raise AssertionError("Band order differs across feature years.")
        arrays[year] = array
    return master, arrays, names or ()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify/warp five composites to the 2020 master grid.")
    for year in range(2016, 2021):
        parser.add_argument(f"--y{year}", type=Path, required=True)
    args = parser.parse_args()
    paths = {year: getattr(args, f"y{year}") for year in range(2016, 2021)}
    grid, arrays, bands = load_trajectory(paths)
    print(f"Master: {grid.crs} {grid.shape} {grid.transform}")
    print(f"Bands: {bands}; years: {tuple(arrays)}")


if __name__ == "__main__":
    main()
