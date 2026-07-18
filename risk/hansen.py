"""Exact Hansen reads and pixel-center overlays for the risk study.

The detector paper's reference builder uses rectangular array slices.  This
module intentionally does not call it: L6 requires explicit pixel-center
membership, and L13 requires a separate read path that cannot expose post-2020
loss years to site selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
from typing import Callable, Iterable, Mapping

import threading

import numpy as np
import rasterio
from affine import Affine
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds, intersection

GFC_VERSION = "GFC-2024-v1.12"
GFC_HTTP_BASE = (
    "https://storage.googleapis.com/earthenginepartners-hansen/"
    f"{GFC_VERSION}/Hansen_{GFC_VERSION}_{{band}}_{{tile}}.tif"
)
VALID_BANDS = frozenset({"lossyear", "treecover2000", "datamask"})


def hansen_url(band: str, tile: str, vsi: bool = True) -> str:
    if band not in VALID_BANDS:
        raise ValueError(f"Unsupported Hansen band {band!r}; expected {sorted(VALID_BANDS)}")
    url = GFC_HTTP_BASE.format(band=band, tile=tile)
    return f"/vsicurl/{url}" if vsi else url


def tile_for_point(lon: float, lat: float) -> str:
    """Return the Hansen 10-degree tile named by its northwest corner."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError((lon, lat))
    west = int(floor(lon / 10.0) * 10)
    north = int(ceil(lat / 10.0) * 10)
    lat_tag = f"{abs(north):02d}{'N' if north >= 0 else 'S'}"
    lon_tag = f"{abs(west):03d}{'E' if west >= 0 else 'W'}"
    return f"{lat_tag}_{lon_tag}"


def tiles_for_bounds(bounds: tuple[float, float, float, float]) -> tuple[str, ...]:
    west, south, east, north = bounds
    epsilon = 1e-10
    lons = np.arange(floor(west / 10) * 10, east, 10, dtype=float)
    north_edges = np.arange(ceil(north / 10) * 10, south, -10, dtype=float)
    tiles = [tile_for_point(float(lon + epsilon), float(edge - epsilon))
             for edge in north_edges for lon in lons]
    return tuple(dict.fromkeys(tiles))


@dataclass(frozen=True)
class HansenWindow:
    arrays: Mapping[str, np.ndarray]
    transform: Affine
    crs: str

    @property
    def shape(self) -> tuple[int, int]:
        return next(iter(self.arrays.values())).shape


@dataclass(frozen=True)
class FrameHansenWindow:
    """The only lossyear-derived objects visible to frame selection are boolean."""

    datamask: np.ndarray
    treecover2000: np.ndarray
    prior_loss_2001_2020: np.ndarray
    recent_loss_2016_2020: np.ndarray
    transform: Affine
    crs: str

    def __post_init__(self) -> None:
        if self.prior_loss_2001_2020.dtype != np.bool_:
            raise TypeError("Temporal firewall requires a boolean prior-loss mask.")
        if self.recent_loss_2016_2020.dtype != np.bool_:
            raise TypeError("Temporal firewall requires a boolean recent-loss mask.")


def _clipped_window(dataset: rasterio.io.DatasetReader,
                    bounds: tuple[float, float, float, float]) -> Window:
    floating = from_bounds(*bounds, transform=dataset.transform)
    col0 = floor(floating.col_off)
    row0 = floor(floating.row_off)
    col1 = ceil(floating.col_off + floating.width)
    row1 = ceil(floating.row_off + floating.height)
    requested = Window(col0, row0, col1 - col0, row1 - row0)
    full = Window(0, 0, dataset.width, dataset.height)
    return intersection(requested, full)


_LOCAL = threading.local()
_MAX_CACHED_DATASETS = 24


def _cached_dataset(band: str, tile: str):
    """Reuse an open /vsicurl dataset instead of re-fetching its header per read.

    A Hansen tile is 40,000 x 40,000 px, so OPENING it over HTTP costs far more than the
    ~900 x 800 px window we actually want. The original code opened and closed each band
    per candidate box; screening 16,244 boxes therefore paid ~29 s/box in header fetches
    and would have taken 8+ hours. Caching the handles turns that into one open per tile.

    THREAD-LOCAL BY CONSTRUCTION: GDAL datasets are NOT thread-safe for concurrent reads,
    and screen_universe is threaded. A shared handle could silently return corrupt pixels
    -- far worse than being slow -- so each worker keeps its own handles.
    """
    cache = getattr(_LOCAL, "datasets", None)
    if cache is None:
        cache = _LOCAL.datasets = {}
    key = (band, tile)
    dataset = cache.get(key)
    if dataset is None:
        if len(cache) >= _MAX_CACHED_DATASETS:  # crude bound on open handles per thread
            for handle in cache.values():
                handle.close()
            cache.clear()
        dataset = cache[key] = rasterio.open(hansen_url(band, tile))
    return dataset


def _read_tile_band(band: str, tile: str,
                    bounds: tuple[float, float, float, float],
                    opener: Callable[..., object] = rasterio.open
                    ) -> tuple[np.ndarray, Affine, str]:
    # Tests inject fake openers; only the real rasterio path is cached.
    if opener is not rasterio.open:
        with opener(hansen_url(band, tile)) as dataset:
            window = _clipped_window(dataset, bounds)
            array = dataset.read(1, window=window)
            return array, dataset.window_transform(window), str(dataset.crs)
    dataset = _cached_dataset(band, tile)
    window = _clipped_window(dataset, bounds)
    array = dataset.read(1, window=window)
    return array, dataset.window_transform(window), str(dataset.crs)


def _place_parts(parts: Iterable[tuple[np.ndarray, Affine]], fill: int | bool = 0
                 ) -> tuple[np.ndarray, Affine]:
    parts = list(parts)
    if not parts:
        raise ValueError("No raster parts overlap the requested bounds.")
    xres = abs(parts[0][1].a)
    yres = abs(parts[0][1].e)
    extents = []
    for array, transform in parts:
        bottom, left = 0.0, 0.0  # names assigned below for readability
        left, bottom, right, top = array_bounds(*array.shape, transform)
        extents.append((left, bottom, right, top))
    left = min(e[0] for e in extents)
    bottom = min(e[1] for e in extents)
    right = max(e[2] for e in extents)
    top = max(e[3] for e in extents)
    width = int(round((right - left) / xres))
    height = int(round((top - bottom) / yres))
    dtype = np.result_type(*[part[0].dtype for part in parts])
    out = np.full((height, width), fill, dtype=dtype)
    for (array, transform), extent in zip(parts, extents):
        col = int(round((extent[0] - left) / xres))
        row = int(round((top - extent[3]) / yres))
        out[row:row + array.shape[0], col:col + array.shape[1]] = array
    return out, Affine(xres, 0.0, left, 0.0, -yres, top)


def read_hansen_window(bounds: tuple[float, float, float, float],
                       bands: Iterable[str] = ("lossyear", "treecover2000", "datamask"),
                       opener: Callable[..., object] = rasterio.open) -> HansenWindow:
    """Read full Hansen values for labels/features, outside the frame firewall."""
    requested = tuple(bands)
    arrays: dict[str, np.ndarray] = {}
    common_transform: Affine | None = None
    crs: str | None = None
    for band in requested:
        pieces: list[tuple[np.ndarray, Affine]] = []
        for tile in tiles_for_bounds(bounds):
            try:
                array, transform, tile_crs = _read_tile_band(band, tile, bounds, opener)
            except Exception as exc:
                if exc.__class__.__name__ == "WindowError":
                    continue
                raise
            pieces.append((array, transform))
            crs = tile_crs
        arrays[band], band_transform = _place_parts(pieces)
        common_transform = common_transform or band_transform
        if arrays[band].shape != next(iter(arrays.values())).shape or band_transform != common_transform:
            raise AssertionError("Hansen bands are not on one common native grid.")
    return HansenWindow(arrays=arrays, transform=common_transform, crs=crs or "EPSG:4326")


def _read_frame_tile(tile: str, bounds: tuple[float, float, float, float],
                     opener: Callable[..., object] = rasterio.open
                     ) -> tuple[dict[str, np.ndarray], Affine, str]:
    """Read one tile and destroy raw lossyear immediately after making <=2020 masks.

    L13.3 needs both cumulative and 2016--2020 activity.  The two boolean masks
    are derived in this single expression; no caller can access a year value.
    """
    loss, transform, crs = _read_tile_band("lossyear", tile, bounds, opener)
    prior = np.logical_and(loss >= 1, loss <= 20)
    recent = np.logical_and(loss >= 16, loss <= 20)
    del loss
    treecover, tree_tf, tree_crs = _read_tile_band("treecover2000", tile, bounds, opener)
    datamask, data_tf, data_crs = _read_tile_band("datamask", tile, bounds, opener)
    if tree_tf != transform or data_tf != transform or tree_crs != crs or data_crs != crs:
        raise AssertionError("Hansen frame bands are not aligned.")
    return {
        "datamask": datamask,
        "treecover2000": treecover,
        "prior": prior,
        "recent": recent,
    }, transform, crs


def read_frame_hansen(bounds: tuple[float, float, float, float],
                      opener: Callable[..., object] = rasterio.open) -> FrameHansenWindow:
    """Temporal-firewalled frame read: future loss is indistinguishable from no prior loss."""
    grouped: dict[str, list[tuple[np.ndarray, Affine]]] = {
        "datamask": [], "treecover2000": [], "prior": [], "recent": []
    }
    crs = "EPSG:4326"
    for tile in tiles_for_bounds(bounds):
        values, transform, crs = _read_frame_tile(tile, bounds, opener)
        for name, value in values.items():
            grouped[name].append((value, transform))
    mosaics: dict[str, np.ndarray] = {}
    common_tf: Affine | None = None
    for name, parts in grouped.items():
        mosaics[name], transform = _place_parts(parts, fill=False if name in {"prior", "recent"} else 0)
        common_tf = common_tf or transform
        if transform != common_tf:
            raise AssertionError("Hansen frame mosaics are not aligned.")
    return FrameHansenWindow(
        datamask=mosaics["datamask"],
        treecover2000=mosaics["treecover2000"],
        prior_loss_2001_2020=mosaics["prior"].astype(bool, copy=False),
        recent_loss_2016_2020=mosaics["recent"].astype(bool, copy=False),
        transform=common_tf,
        crs=crs,
    )


def pixel_center_mask(transform: Affine, shape: tuple[int, int],
                      bounds: tuple[float, float, float, float]) -> np.ndarray:
    """Select pixels whose centers fall in half-open non-overlapping cell bounds."""
    rows = np.arange(shape[0], dtype=np.float64)
    cols = np.arange(shape[1], dtype=np.float64)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    west, south, east, north = bounds
    x_ok = (xs >= west) & (xs < east)
    y_ok = (ys > south) & (ys <= north)
    return y_ok[:, None] & x_ok[None, :]


def pixel_center_indices(transform: Affine, shape: tuple[int, int],
                         bounds: tuple[float, float, float, float]
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Memory-efficient row/column indices for the same L6 half-open rule."""
    rows = np.arange(shape[0], dtype=np.float64)
    cols = np.arange(shape[1], dtype=np.float64)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    west, south, east, north = bounds
    return np.flatnonzero((ys > south) & (ys <= north)), np.flatnonzero((xs >= west) & (xs < east))


def aggregate_hansen_cells(lossyear: np.ndarray, treecover2000: np.ndarray,
                           datamask: np.ndarray, transform: Affine,
                           cell_bounds: np.ndarray) -> dict[str, np.ndarray]:
    """Apply L5 counts using native pixels and explicit center membership."""
    if not (lossyear.shape == treecover2000.shape == datamask.shape):
        raise ValueError("Hansen arrays must share a shape.")
    n = len(cell_bounds)
    result = {name: np.zeros(n, dtype=np.int64) for name in
              ("valid_land", "u_treecover", "eligible_forest_2020", "future_loss", "prior_loss")}
    result["treecover_eligible_sum"] = np.zeros(n, dtype=np.float64)
    for i, bounds in enumerate(np.asarray(cell_bounds, dtype=float)):
        row_indices, col_indices = pixel_center_indices(transform, lossyear.shape, tuple(bounds))
        if row_indices.size == 0 or col_indices.size == 0:
            continue
        index = np.ix_(row_indices, col_indices)
        cell_loss = lossyear[index]
        cell_tree = treecover2000[index]
        cell_data = datamask[index]
        valid = cell_data == 1
        universe = valid & (cell_tree >= 30)
        eligible = universe & ((cell_loss == 0) | (cell_loss >= 21))
        future = universe & (cell_loss >= 21) & (cell_loss <= 24)
        prior = universe & (cell_loss >= 1) & (cell_loss <= 20)
        result["valid_land"][i] = int(valid.sum())
        result["u_treecover"][i] = int(universe.sum())
        result["eligible_forest_2020"][i] = int(eligible.sum())
        result["future_loss"][i] = int(future.sum())
        result["prior_loss"][i] = int(prior.sum())
        result["treecover_eligible_sum"][i] = float(cell_tree[eligible].sum())
        if result["future_loss"][i] > result["eligible_forest_2020"][i]:
            raise AssertionError("L5 numerator is not a subset of its denominator.")
    return result


def eligible_mask_to_master(eligible_30m: np.ndarray, source_transform: Affine,
                            source_crs: str, master_shape: tuple[int, int],
                            master_transform: Affine, master_crs: str) -> np.ndarray:
    """L6 boolean nearest-neighbour sampling onto Sentinel pixel centers."""
    destination = np.zeros(master_shape, dtype=np.uint8)
    reproject(
        source=eligible_30m.astype(np.uint8), destination=destination,
        src_transform=source_transform, src_crs=source_crs,
        dst_transform=master_transform, dst_crs=master_crs,
        resampling=Resampling.nearest,
    )
    return destination.astype(bool)
