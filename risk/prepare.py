"""End-to-end site preparation after the four annual artifacts are downloaded.

This stage builds the 2020 master grid, reads native Hansen pixels, constructs
L5 labels and the fixed support, fits L3 normalization, applies L2, and writes
normalized and unnormalized S/B/C/D cell tables ready for the LOSO runners.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import rasterio
from pyproj import Geod, Transformer
from rasterio.transform import array_bounds
from rasterio.windows import Window, from_bounds, intersection
from rasterio.warp import Resampling, reproject, transform_bounds

from .config import FEATURE_YEARS, PROCESSED_DIR, REFLECTANCE_BANDS
from .grid import _to_rho
from .features import (
    condition_features,
    contagion_grid_features,
    neighborhood_hansen_features,
    prior_loss_cell_summaries,
    spectral_indices,
    stock_features,
)
from .grid import cell_grid, load_trajectory
from .grid import warp_reflectance
from .hansen import (
    aggregate_hansen_cells,
    eligible_mask_to_master,
    pixel_center_indices,
    pixel_center_mask,
    read_hansen_window,
)
from .labels import build_labels
from .normalization import apply_transforms, build_pif_mask, fit_transforms
from .provenance import base_provenance, write_json
from .qc import evaluate_site, evaluate_site_year


def _reproject_single(path: Path, shape: tuple[int, int], transform, crs,
                      resampling: Resampling, dtype=np.float32) -> np.ndarray:
    with rasterio.open(path) as source:
        destination = np.full(shape, np.nan, dtype=dtype)
        reproject(
            source=rasterio.band(source, 1), destination=destination,
            src_transform=source.transform, src_crs=source.crs,
            dst_transform=transform, dst_crs=crs,
            src_nodata=source.nodata, dst_nodata=np.nan,
            resampling=resampling,
        )
    return destination


def _reflectance_to_hansen(path: Path, hansen_shape: tuple[int, int], hansen_transform,
                           hansen_crs: str, convention: str) -> tuple[np.ndarray, tuple[str, ...]]:
    with rasterio.open(path) as source:
        destination = np.full((source.count, *hansen_shape), np.nan, dtype=np.float32)
        for index in range(source.count):
            values = source.read(index + 1).astype(np.float32)
            if source.nodata is not None:
                values[values == source.nodata] = np.nan
            values = _to_rho(values, convention)
            reproject(
                source=values, destination=destination[index],
                src_transform=source.transform, src_crs=source.crs,
                dst_transform=hansen_transform, dst_crs=hansen_crs,
                src_nodata=np.nan, dst_nodata=np.nan,
                resampling=Resampling.average,
            )
        names = tuple(name or f"band_{i}" for i, name in enumerate(source.descriptions, 1))
    return destination, names


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    finite = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not finite.any():
        return float("nan")
    values = values[finite]
    weights = weights[finite]
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    return float(values[order[np.searchsorted(cumulative, cumulative[-1] / 2, side="left")]])


def _area_weighted_values(array: np.ndarray, support: np.ndarray, transform,
                          bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Return native pixels and exact rectangle-overlap areas for one target box."""
    west, south, east, north = bounds
    floating = from_bounds(west, south, east, north, transform)
    col0_float, row0_float = floating.col_off, floating.row_off
    col1_float = floating.col_off + floating.width
    row1_float = floating.row_off + floating.height
    requested = Window(
        np.floor(col0_float), np.floor(row0_float),
        np.ceil(col1_float) - np.floor(col0_float),
        np.ceil(row1_float) - np.floor(row0_float),
    )
    try:
        window = intersection(requested, Window(0, 0, array.shape[1], array.shape[0]))
    except Exception:
        return np.array([], dtype=array.dtype), np.array([], dtype=float)
    row0 = int(window.row_off)
    col0 = int(window.col_off)
    height = int(window.height)
    width = int(window.width)
    rows, cols = np.indices((height, width))
    rows = rows + row0
    cols = cols + col0
    x0 = transform.c + cols * transform.a
    x1 = x0 + transform.a
    y1 = transform.f + rows * transform.e
    y0 = y1 + transform.e
    pixel_west, pixel_east = np.minimum(x0, x1), np.maximum(x0, x1)
    pixel_south, pixel_north = np.minimum(y0, y1), np.maximum(y0, y1)
    overlap_x = np.maximum(0.0, np.minimum(pixel_east, east) - np.maximum(pixel_west, west))
    overlap_y = np.maximum(0.0, np.minimum(pixel_north, north) - np.maximum(pixel_south, south))
    weights = overlap_x * overlap_y
    array_part = array[row0:row0 + height, col0:col0 + width]
    support_part = support[row0:row0 + height, col0:col0 + width]
    selected = support_part & (weights > 0)
    return array_part[selected], weights[selected]


def clearobs_native_statistics(path: Path, eligible_hansen: np.ndarray,
                               hansen_transform, hansen_crs: str,
                               cell_bounds_master: np.ndarray, master_crs: str,
                               analysis_bounds_wgs84: tuple[float, float, float, float]
                               ) -> tuple[float, np.ndarray, np.ndarray]:
    """Area-weight native 20 m counts; never bilinearly interpolate them."""
    with rasterio.open(path) as source:
        counts = source.read(1).astype(np.float32)
        if source.nodata is not None:
            counts[counts == source.nodata] = np.nan
        support20 = eligible_mask_to_master(
            eligible_hansen, hansen_transform, hansen_crs,
            counts.shape, source.transform, str(source.crs),
        )
        analysis_bounds = transform_bounds("EPSG:4326", source.crs, *analysis_bounds_wgs84, densify_pts=21)
        values, weights = _area_weighted_values(counts, support20, analysis_bounds)
        site_median = _weighted_median(values, weights)
        cell_medians = []
        for bounds in cell_bounds_master:
            projected = transform_bounds(master_crs, source.crs, *bounds, densify_pts=5)
            values, weights = _area_weighted_values(counts, support20, projected)
            cell_medians.append(_weighted_median(values, weights))
        # Area-weighted average onto each native Hansen pixel for the PIF clear criterion.
        on_hansen = np.full(eligible_hansen.shape, np.nan, dtype=np.float32)
        reproject(
            source=counts, destination=on_hansen,
            src_transform=source.transform, src_crs=source.crs,
            dst_transform=hansen_transform, dst_crs=hansen_crs,
            src_nodata=np.nan, dst_nodata=np.nan,
            resampling=Resampling.average,
        )
    return site_median, np.asarray(cell_medians), on_hansen


def _cell_lossyear_values(lossyear: np.ndarray, treecover: np.ndarray, datamask: np.ndarray,
                          transform, bounds: np.ndarray) -> list[np.ndarray]:
    output = []
    for cell in bounds:
        row_indices, col_indices = pixel_center_indices(transform, lossyear.shape, tuple(cell))
        if row_indices.size == 0 or col_indices.size == 0:
            output.append(np.array([], dtype=lossyear.dtype))
            continue
        index = np.ix_(row_indices, col_indices)
        cell_loss = lossyear[index]
        universe = (datamask[index] == 1) & (treecover[index] >= 30)
        output.append(cell_loss[universe])
    return output


def _pif_medians(reflectance_30m: Mapping[int, np.ndarray], band_names: Sequence[str],
                 pif_mask: np.ndarray) -> dict[int, dict[str, float]]:
    output = {}
    for year in FEATURE_YEARS:
        output[year] = {}
        for name, values in spectral_indices(reflectance_30m[year], band_names).items():
            output[year][name] = float(np.nanmedian(values[pif_mask]))
    return output


def prepare_site(site: Mapping[str, object], raw_root: str | Path,
                 output_dir: str | Path = PROCESSED_DIR,
                 convention: str = "already_offset_integer_scaled") -> dict[str, object]:
    raw_root = Path(raw_root)
    site_id = str(site["candidate_id"])
    site_dir = raw_root / site_id
    reflectance_paths = {year: site_dir / f"{year}_reflectance.tif" for year in FEATURE_YEARS}
    clear_paths = {year: site_dir / f"{year}_clearobs.tif" for year in FEATURE_YEARS}
    missing = [str(path) for path in (*reflectance_paths.values(), *clear_paths.values()) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing downloaded artifacts for {site_id}: {missing}")

    # L0 conversion is the first radiometric operation.  Arrays remain
    # unclipped here so QC can measure out-of-range support before clipping.
    master, raw_master, band_names = load_trajectory(reflectance_paths, convention)
    if tuple(band_names) != tuple(REFLECTANCE_BANDS):
        raise AssertionError(f"Unexpected reflectance band order: {band_names}")
    analysis_wgs84 = tuple(float(site[name]) for name in ("west", "south", "east", "north"))
    cells = cell_grid(master, analysis_wgs84)
    master_bounds = array_bounds(master.height, master.width, master.transform)
    hansen_bounds = transform_bounds(master.crs, "EPSG:4326", *master_bounds, densify_pts=21)
    hansen = read_hansen_window(hansen_bounds)
    loss = hansen.arrays["lossyear"]
    tree = hansen.arrays["treecover2000"]
    datamask = hansen.arrays["datamask"]
    cell_bounds_hansen = np.asarray([
        transform_bounds(master.crs, hansen.crs, *bounds, densify_pts=5)
        for bounds in cells["cell_bounds"]
    ])
    counts = aggregate_hansen_cells(loss, tree, datamask, hansen.transform, cell_bounds_hansen)
    labels = build_labels(counts)
    eligible30 = (datamask == 1) & (tree >= 30) & ((loss == 0) | (loss >= 21))
    support10 = eligible_mask_to_master(
        eligible30, hansen.transform, hansen.crs,
        master.shape, master.transform, master.crs,
    )
    analysis_bounds_master = transform_bounds("EPSG:4326", master.crs, *analysis_wgs84, densify_pts=21)
    analysis_support = support10 & pixel_center_mask(master.transform, master.shape, analysis_bounds_master)

    cell_clear: dict[int, np.ndarray] = {}
    clear_hansen: dict[int, np.ndarray] = {}
    site_clear: dict[int, float] = {}
    acquisition_covariates: dict[int, dict[str, float]] = {}
    for year in FEATURE_YEARS:
        site_clear[year], cell_clear[year], clear_hansen[year] = clearobs_native_statistics(
            clear_paths[year], eligible30, hansen.transform, hansen.crs,
            cells["cell_bounds"], master.crs, analysis_wgs84,
        )
        solar_path = site_dir / f"{year}_solar_zenith.tif"
        dispersion_path = site_dir / f"{year}_dispersion.tif"
        provenance_path = site_dir / f"{year}_provenance.json"
        if not (solar_path.exists() and dispersion_path.exists() and provenance_path.exists()):
            raise FileNotFoundError(
                f"Acquisition robustness artifacts missing for {site_id} {year}: "
                f"{solar_path}, {dispersion_path}, {provenance_path}"
            )
        solar = _reproject_single(
            solar_path, master.shape, master.transform, master.crs, Resampling.bilinear
        )
        dispersion, dispersion_names = warp_reflectance(
            dispersion_path, master, "already_offset_integer_scaled"
        )
        if dispersion_names != band_names:
            raise AssertionError("Dispersion band order differs from reflectance.")
        download_record = json.loads(provenance_path.read_text(encoding="utf-8"))
        metadata = download_record.get("acquisition_metadata", {})
        median_doy = metadata.get("median_doy")
        acquisition_covariates[year] = {
            "median_doy": float(median_doy) if median_doy is not None else np.nan,
            "clearobs": float(site_clear[year]),
            "solar_zenith": float(np.nanmedian(solar[analysis_support])),
            # One prespecified scalar per site-year: median of the per-band,
            # per-pixel temporal SD raster over fixed support.
            "dispersion": float(np.nanmedian(dispersion[:, analysis_support])),
        }
    # Approximate native Hansen pixel sizes geodesically at the window centre.
    centre_lat = (hansen_bounds[1] + hansen_bounds[3]) / 2
    geod = Geod(ellps="WGS84")
    _, _, x_size = geod.inv(
        hansen.transform.c, centre_lat,
        hansen.transform.c + abs(hansen.transform.a), centre_lat,
    )
    _, _, y_size = geod.inv(
        hansen.transform.c, centre_lat,
        hansen.transform.c, centre_lat + abs(hansen.transform.e),
    )
    pif_mask = build_pif_mask(
        datamask, tree, (loss >= 1) & (loss <= 20), clear_hansen,
        (abs(y_size), abs(x_size)),
    )

    raw_hansen = {}
    converted_hansen = {}
    converted_master = {}
    for year in FEATURE_YEARS:
        raw_hansen[year], names = _reflectance_to_hansen(
            reflectance_paths[year], hansen.shape, hansen.transform, hansen.crs, convention
        )
        if names != band_names:
            raise AssertionError("Hansen-aggregated band order changed.")
        record30, converted_hansen[year] = evaluate_site_year(
            year, raw_hansen[year], np.ones(hansen.shape), pif_mask,
            int(pif_mask.sum()), convention="already_reflectance",
        )
        # This temporary record is used only for L0 conversion; final QC below
        # uses the unbuffered condition support and real clear counts.
        _, converted_master[year] = evaluate_site_year(
            year, raw_master[year], np.ones(master.shape), analysis_support,
            int(pif_mask.sum()), convention="already_reflectance",
            median_clear_override=site_clear[year],
        )

    transforms = fit_transforms(converted_hansen, pif_mask, band_names)
    normalized_master, audited_transforms = apply_transforms(
        converted_master, band_names, transforms, support10
    )
    normalized_hansen, _ = apply_transforms(converted_hansen, band_names, transforms, pif_mask)

    qc_records = {}
    for year in FEATURE_YEARS:
        coefficients = {name: (record.gain, record.offset)
                        for name, record in transforms[year].items()}
        qc_records[year], _ = evaluate_site_year(
            year, raw_master[year], np.ones(master.shape), analysis_support,
            int(pif_mask.sum()), coefficients, "already_reflectance",
            median_clear_override=site_clear[year],
        )
    at_risk_interior = labels.at_risk & cells["interior"]
    clear_matrix = np.column_stack([cell_clear[year][at_risk_interior] for year in FEATURE_YEARS])
    site_qc = evaluate_site(qc_records, clear_matrix)

    loss_values = _cell_lossyear_values(loss, tree, datamask, hansen.transform, cell_bounds_hansen)
    l20_flat, max_prior_flat = prior_loss_cell_summaries(loss_values, counts["u_treecover"])
    grid_shape = tuple(int(value) for value in cells["grid_shape"])
    l20 = l20_flat.reshape(grid_shape)
    max_prior = max_prior_flat.reshape(grid_shape)
    u_grid = counts["u_treecover"].reshape(grid_shape)

    rows = np.arange(loss.shape[0], dtype=float)
    cols = np.arange(loss.shape[1], dtype=float)
    lon = hansen.transform.c + (cols + 0.5) * hansen.transform.a
    lat = hansen.transform.f + (rows + 0.5) * hansen.transform.e
    llon, llat = np.meshgrid(lon, lat)
    to_master = Transformer.from_crs(hansen.crs, master.crs, always_xy=True)
    xx, yy = to_master.transform(llon, llat)
    centres = np.column_stack((
        (cells["cell_bounds"][:, 0] + cells["cell_bounds"][:, 2]) / 2,
        (cells["cell_bounds"][:, 1] + cells["cell_bounds"][:, 3]) / 2,
    ))
    neighborhood = neighborhood_hansen_features(loss, datamask, xx, yy, centres)
    b = contagion_grid_features(
        l20, u_grid, max_prior, cells["grid_rc"], cells["interior"], neighborhood
    ).set_index("cell_index")
    s = stock_features(counts, cell_clear[2020])

    output_dir = Path(output_dir) / site_id
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {}
    for pipeline, reflectance, pif_reflectance in (
        ("normalized", normalized_master, normalized_hansen),
        ("unnormalized", converted_master, converted_hansen),
    ):
        c_d = condition_features(
            reflectance, band_names, support10, cells["pixel_windows"],
            _pif_medians(pif_reflectance, band_names, pif_mask),
        )
        table = pd.concat((s, c_d), axis=1).join(b, how="left")
        table["site"] = site_id
        table["cohort"] = site["cohort"]
        table["group"] = site["group"]
        table["grid_row"] = cells["grid_rc"][:, 0]
        table["grid_col"] = cells["grid_rc"][:, 1]
        table["label"] = labels.positive.astype(int)
        table["future_loss_pixels"] = labels.future_loss
        table["future_loss_ratio"] = labels.future_loss_ratio
        table["at_risk"] = labels.at_risk
        table["interior"] = cells["interior"]
        for year in FEATURE_YEARS:
            for name, value in acquisition_covariates[year].items():
                table[f"m_{year}_{name}"] = value
        keep = table["at_risk"] & table["interior"] & ~table["excluded_support_lt20"]
        table = table.loc[keep].reset_index(drop=True)
        path = output_dir / f"cells_{pipeline}.csv"
        table.to_csv(path, index=False)
        tables[pipeline] = str(path)

    artifact = {
        **base_provenance(), "site": site_id, "qc_passed": site_qc.passed,
        "qc": {"site_years": [record.__dict__ for record in site_qc.site_years],
               "every_year_cell_fraction": site_qc.every_year_cell_fraction,
               "failures": site_qc.failures},
        "pif_pixels": int(pif_mask.sum()), "tables": tables,
        "normalization": {
            str(year): {name: record.__dict__ for name, record in audited_transforms[year].items()}
            for year in FEATURE_YEARS
        },
    }
    write_json(output_dir / "preparation.json", artifact)
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare one downloaded site through QC/features.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("site")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    site = next((item for item in manifest["sites"] if item["candidate_id"] == args.site), None)
    if site is None:
        raise SystemExit(f"Unknown site {args.site!r}")
    result = prepare_site(site, args.raw_root, args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
