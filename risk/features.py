"""Exact S/B/C/D feature blocks with a single five-year condition support.

Condition extraction accepts one support mask (or verifies that a supplied
year mapping is bit-identical) and applies it unchanged to every annual array.
This API makes the anti-circularity invariant hard to violate accidentally.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import skew

from .config import (
    CELL_SIZE_M,
    DISTANCE_CAP_M,
    FEATURE_YEARS,
    MIN_SUPPORT_PIXELS,
    NEIGHBORHOOD_RADIUS_M,
    REFERENCE_YEAR,
    assert_feature_years,
)

INDEX_NAMES = ("ndvi", "ndmi", "nbr")
SUMMARY_NAMES = ("mean", "std", "skew", "p10", "p25", "p50", "p75", "p90", "tailmass")


def spectral_indices(reflectance: np.ndarray, band_names: Sequence[str]) -> dict[str, np.ndarray]:
    lookup = {name: np.asarray(reflectance[index], dtype=np.float32)
              for index, name in enumerate(band_names)}
    missing = {"B02", "B03", "B04", "B08", "B11", "B12"} - set(lookup)
    if missing:
        raise ValueError(f"Missing condition bands: {sorted(missing)}")
    return {
        "ndvi": (lookup["B08"] - lookup["B04"]) / (lookup["B08"] + lookup["B04"] + 1e-6),
        "ndmi": (lookup["B08"] - lookup["B11"]) / (lookup["B08"] + lookup["B11"] + 1e-6),
        "nbr": (lookup["B08"] - lookup["B12"]) / (lookup["B08"] + lookup["B12"] + 1e-6),
    }


def fixed_support_mask(support: np.ndarray | Mapping[int, np.ndarray]) -> np.ndarray:
    if isinstance(support, Mapping):
        years = assert_feature_years(support)
        first = np.asarray(support[years[0]], dtype=bool)
        for year in years[1:]:
            if not np.array_equal(first, np.asarray(support[year], dtype=bool)):
                raise AssertionError("Condition support changed across feature years.")
        return first
    return np.asarray(support, dtype=bool)


def _distribution(values: np.ndarray, pif_median: float) -> tuple[dict[str, float], bool]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < MIN_SUPPORT_PIXELS:
        raise ValueError("support_lt_20")
    standard_deviation = float(np.std(values, ddof=0))
    degenerate = standard_deviation == 0.0
    result = {
        "mean": float(np.mean(values)), "std": standard_deviation,
        "skew": 0.0 if degenerate else float(skew(values, bias=False)),
    }
    for percentile in (10, 25, 50, 75, 90):
        result[f"p{percentile}"] = float(np.percentile(values, percentile))
    result["tailmass"] = float(np.mean(values < pif_median - 0.20))
    return result, degenerate


def _slope(values: Sequence[float]) -> float:
    return float(np.polyfit(np.asarray(FEATURE_YEARS, dtype=float), np.asarray(values, dtype=float), 1)[0])


def condition_features(reflectance_by_year: Mapping[int, np.ndarray], band_names: Sequence[str],
                       support: np.ndarray | Mapping[int, np.ndarray],
                       pixel_windows: np.ndarray,
                       pif_index_medians: Mapping[int, Mapping[str, float]]) -> pd.DataFrame:
    years = assert_feature_years(reflectance_by_year)
    if set(years) != set(FEATURE_YEARS):
        raise ValueError("Condition history requires all five locked years.")
    fixed = fixed_support_mask(support)
    indices = {year: spectral_indices(reflectance_by_year[year], band_names) for year in FEATURE_YEARS}
    band_lookup = {name: index for index, name in enumerate(band_names)}
    rows = []
    for row0, col0, height, width in np.asarray(pixel_windows, dtype=int):
        cell_support = fixed[row0:row0 + height, col0:col0 + width]
        if int(cell_support.sum()) < MIN_SUPPORT_PIXELS:
            rows.append({"excluded_support_lt20": True})
            continue
        record: dict[str, float | bool] = {"excluded_support_lt20": False, "zero_variance_skew": False}
        annual: dict[int, dict[str, dict[str, float]]] = {}
        for year in FEATURE_YEARS:
            annual[year] = {}
            for name in INDEX_NAMES:
                values = indices[year][name][row0:row0 + height, col0:col0 + width][cell_support]
                summary, degenerate = _distribution(values, pif_index_medians[year][name])
                annual[year][name] = summary
                record["zero_variance_skew"] = bool(record["zero_variance_skew"] or degenerate)

        # C is only the normalized 2020 level.
        for name in INDEX_NAMES:
            for statistic in SUMMARY_NAMES:
                record[f"c_{name}_{statistic}"] = annual[REFERENCE_YEAR][name][statistic]
        rgb = np.mean(
            np.asarray(reflectance_by_year[REFERENCE_YEAR])[
                [band_lookup["B02"], band_lookup["B03"], band_lookup["B04"]],
                row0:row0 + height, col0:col0 + width,
            ], axis=0,
        )
        record["c_brightness"] = float(np.nanmean(rgb[cell_support]))

        # D contains change only; snapshot levels stay exclusively in C.
        for name in INDEX_NAMES:
            means = [annual[year][name]["mean"] for year in FEATURE_YEARS]
            stds = [annual[year][name]["std"] for year in FEATURE_YEARS]
            p10s = [annual[year][name]["p10"] for year in FEATURE_YEARS]
            record[f"d_{name}_slope_mean"] = _slope(means)
            record[f"d_{name}_slope_std"] = _slope(stds)
            record[f"d_{name}_slope_p10"] = _slope(p10s)
            record[f"d_{name}_tstd_mean"] = float(np.std(means, ddof=1))
            record[f"d_{name}_delta"] = float(means[-1] - means[0])
        rows.append(record)
    return pd.DataFrame(rows)


def stock_features(counts: Mapping[str, np.ndarray], clearobs_2020: np.ndarray) -> pd.DataFrame:
    valid = np.asarray(counts["valid_land"], dtype=float)
    eligible = np.asarray(counts["eligible_forest_2020"], dtype=float)
    tree_sum = np.asarray(counts["treecover_eligible_sum"], dtype=float)
    forest_fraction = np.divide(eligible, valid, out=np.zeros_like(eligible), where=valid > 0)
    tree_mean = np.divide(tree_sum, eligible, out=np.full_like(tree_sum, np.nan), where=eligible > 0)
    return pd.DataFrame({
        "s_forest_frac": forest_fraction,
        "s_treecover_mean": tree_mean,
        "s_clearobs": np.asarray(clearobs_2020, dtype=float),
    })


def prior_loss_cell_summaries(lossyear_by_cell: Sequence[np.ndarray],
                              u_treecover_counts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute L20 and max prior code while making future years impossible to select."""
    fractions = np.zeros(len(lossyear_by_cell), dtype=np.float64)
    maximum_prior = np.zeros(len(lossyear_by_cell), dtype=np.int16)
    for index, values in enumerate(lossyear_by_cell):
        values = np.asarray(values)
        prior = values[(values >= 1) & (values <= 20)]
        denominator = int(u_treecover_counts[index])
        fractions[index] = prior.size / denominator if denominator else 0.0
        maximum_prior[index] = int(prior.max()) if prior.size else 0
    if np.any((maximum_prior < 0) | (maximum_prior > 20)):
        raise AssertionError("Label-window year reached a prior-loss summary.")
    return fractions, maximum_prior


def contagion_grid_features(l20: np.ndarray, u_counts: np.ndarray, max_prior_year: np.ndarray,
                            grid_rc: np.ndarray, interior: np.ndarray,
                            neighborhood: Mapping[str, np.ndarray] | None = None) -> pd.DataFrame:
    l20 = np.asarray(l20, dtype=float)
    u_counts = np.asarray(u_counts)
    max_prior_year = np.asarray(max_prior_year)
    if not (l20.shape == u_counts.shape == max_prior_year.shape):
        raise ValueError("Contagion grids must align.")
    loss_cells = np.argwhere(l20 >= 0.25)
    records = []
    for flat_index, ((row, col), keep) in enumerate(zip(np.asarray(grid_rc, dtype=int), interior)):
        if not keep:
            continue
        record: dict[str, float | int] = {"cell_index": flat_index, "b_own_prior_loss": float(l20[row, col])}
        for radius in (1, 2, 3, 5):
            rr, cc = np.indices(l20.shape)
            ring = np.maximum(np.abs(rr - row), np.abs(cc - col)) == radius
            valid = ring & (u_counts > 0)
            record[f"b_ring{radius}"] = float(np.mean(l20[valid])) if valid.any() else np.nan
        if loss_cells.size:
            distances_cells = np.sqrt(np.sum((loss_cells - np.array([row, col])) ** 2, axis=1))
            nearest_index = int(np.argmin(distances_cells))
            distance = float(distances_cells[nearest_index] * CELL_SIZE_M)
        else:
            distance = float("inf")
            nearest_index = -1
        if distance <= DISTANCE_CAP_M:
            nearest_row, nearest_col = loss_cells[nearest_index]
            prior_code = int(max_prior_year[nearest_row, nearest_col])
            if not 1 <= prior_code <= 20:
                raise AssertionError("Nearest prior-loss cell has no prior year in [1,20].")
            time_since = 20 - prior_code
            if not 0 <= time_since <= 19:
                raise AssertionError("Uncensored b_time_since_loss escaped [0,19].")
            record.update({
                "b_dist_nearest_loss": distance, "b_dist_censored": 0,
                "b_time_since_loss": time_since,
            })
        else:
            record.update({
                "b_dist_nearest_loss": float(DISTANCE_CAP_M), "b_dist_censored": 1,
                "b_time_since_loss": 25,
            })
        if neighborhood is not None:
            for name in ("b_density_1", "b_density_3", "b_density_5", "b_trend"):
                record[name] = float(np.asarray(neighborhood[name])[flat_index])
        records.append(record)
    return pd.DataFrame(records)


def neighborhood_hansen_features(lossyear: np.ndarray, datamask: np.ndarray,
                                 x_coordinates_m: np.ndarray, y_coordinates_m: np.ndarray,
                                 cell_centres_m: np.ndarray) -> dict[str, np.ndarray]:
    """Circular 1,920 m native-pixel densities and five-point loss-count slope."""
    lossyear = np.asarray(lossyear)
    datamask = np.asarray(datamask)
    x_coordinates_m = np.asarray(x_coordinates_m)
    y_coordinates_m = np.asarray(y_coordinates_m)
    if x_coordinates_m.ndim == y_coordinates_m.ndim == 1:
        xx, yy = np.meshgrid(x_coordinates_m, y_coordinates_m)
    elif x_coordinates_m.shape == y_coordinates_m.shape == lossyear.shape:
        xx, yy = x_coordinates_m, y_coordinates_m
    else:
        raise ValueError("Hansen metric coordinates must be matching 1-D axes or 2-D grids.")
    points = np.column_stack((xx.ravel(), yy.ravel()))
    tree = cKDTree(points)
    flat_loss = lossyear.ravel()
    flat_valid = datamask.ravel() == 1
    result = {name: np.full(len(cell_centres_m), np.nan, dtype=float)
              for name in ("b_density_1", "b_density_3", "b_density_5", "b_trend")}
    for index, (centre_x, centre_y) in enumerate(np.asarray(cell_centres_m, dtype=float)):
        neighborhood_indices = np.asarray(
            tree.query_ball_point((centre_x, centre_y), NEIGHBORHOOD_RADIUS_M), dtype=np.int64
        )
        valid_indices = neighborhood_indices[flat_valid[neighborhood_indices]]
        denominator = int(valid_indices.size)
        if denominator == 0:
            continue
        local_loss = flat_loss[valid_indices]
        for window, lower in ((1, 20), (3, 18), (5, 16)):
            numerator = (local_loss >= lower) & (local_loss <= 20)
            result[f"b_density_{window}"][index] = float(numerator.sum() / denominator)
        annual_counts = [int((local_loss == code).sum()) for code in range(16, 21)]
        result["b_trend"][index] = _slope(annual_counts)
    return result


def feature_blocks(frame: pd.DataFrame) -> dict[str, list[str]]:
    return {
        "S": sorted(column for column in frame if column.startswith("s_")),
        "B": sorted(column for column in frame if column.startswith("b_")),
        "C": sorted(column for column in frame if column.startswith("c_")),
        "D": sorted(column for column in frame if column.startswith("d_")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect feature blocks in a prepared parquet table.")
    parser.add_argument("table", type=Path)
    args = parser.parse_args()
    table = pd.read_parquet(args.table)
    print(feature_blocks(table))


if __name__ == "__main__":
    main()
