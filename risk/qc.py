"""Sensor-only L2 quality gate, applied before any risk model is fit."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .config import (
    BOA_ADD_OFFSET_BASELINE_04,
    BOA_QUANTIFICATION_VALUE,
    MAX_NODATA_FRACTION,
    MAX_OUT_OF_RANGE_FRACTION,
    MIN_CELL_MEDIAN_CLEAR_OBS,
    MIN_GOOD_CELL_FRACTION,
    MIN_MEDIAN_CLEAR_OBS,
    MIN_PIF_PIXELS,
    NORMALIZATION_GAIN_BOUNDS,
    NORMALIZATION_OFFSET_BOUNDS,
)


@dataclass(frozen=True)
class ReflectanceConversion:
    reflectance: np.ndarray
    out_of_range_fraction: float


@dataclass(frozen=True)
class SiteYearQC:
    year: int
    median_clear_observations: float
    nodata_fraction: float
    out_of_range_fraction: float
    pif_pixels: int
    coefficient_bounds_ok: bool
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class SiteQC:
    site_years: tuple[SiteYearQC, ...]
    every_year_cell_fraction: float
    passed: bool
    failures: tuple[str, ...]


def convert_reflectance(values: np.ndarray, support: np.ndarray,
                        convention: str = "already_offset_integer_scaled") -> ReflectanceConversion:
    data = np.asarray(values, dtype=np.float32)
    if convention == "already_reflectance":
        rho = data.copy()
    elif convention == "already_offset_integer_scaled":
        rho = data / BOA_QUANTIFICATION_VALUE
    elif convention == "raw_baseline04_dn":
        rho = (data + BOA_ADD_OFFSET_BASELINE_04) / BOA_QUANTIFICATION_VALUE
    else:
        raise ValueError(f"Unknown L0 convention: {convention}")
    selected = np.broadcast_to(np.asarray(support, dtype=bool), rho.shape[-2:])
    if rho.ndim == 3:
        selected = np.broadcast_to(selected, rho.shape)
    finite_support = selected & np.isfinite(rho)
    if not finite_support.any():
        raise ValueError("No finite reflectance on fixed condition support.")
    fraction = float(((rho < 0) | (rho > 1))[finite_support].mean())
    clipped = np.clip(rho, 0.0, 1.0)
    return ReflectanceConversion(clipped, fraction)


def coefficient_bounds_ok(coefficients: Mapping[str, tuple[float, float]] | None) -> bool:
    if coefficients is None:
        return True
    return all(
        NORMALIZATION_GAIN_BOUNDS[0] <= gain <= NORMALIZATION_GAIN_BOUNDS[1]
        and NORMALIZATION_OFFSET_BOUNDS[0] <= offset <= NORMALIZATION_OFFSET_BOUNDS[1]
        for gain, offset in coefficients.values()
    )


def evaluate_site_year(year: int, reflectance: np.ndarray, clearobs: np.ndarray,
                       support: np.ndarray, pif_pixels: int,
                       coefficients: Mapping[str, tuple[float, float]] | None = None,
                       convention: str = "already_offset_integer_scaled",
                       median_clear_override: float | None = None) -> tuple[SiteYearQC, np.ndarray]:
    conversion = convert_reflectance(reflectance, support, convention)
    support = np.asarray(support, dtype=bool)
    clear_values = np.asarray(clearobs, dtype=float)[support]
    median_clear = (float(median_clear_override) if median_clear_override is not None
                    else float(np.nanmedian(clear_values)) if clear_values.size else float("nan"))
    if reflectance.ndim == 3:
        missing = ~np.isfinite(conversion.reflectance).all(axis=0)
    else:
        missing = ~np.isfinite(conversion.reflectance)
    nodata_fraction = float(missing[support].mean()) if support.any() else 1.0
    coeff_ok = coefficient_bounds_ok(coefficients)
    failures = []
    if not np.isfinite(median_clear) or median_clear < MIN_MEDIAN_CLEAR_OBS:
        failures.append("median_clear_observations")
    if nodata_fraction >= MAX_NODATA_FRACTION:
        failures.append("post_mask_nodata")
    if pif_pixels < MIN_PIF_PIXELS:
        failures.append("pif_pixels")
    if conversion.out_of_range_fraction > MAX_OUT_OF_RANGE_FRACTION:
        failures.append("out_of_range_reflectance")
    if not coeff_ok:
        failures.append("normalization_coefficients")
    record = SiteYearQC(
        year=year, median_clear_observations=median_clear,
        nodata_fraction=nodata_fraction,
        out_of_range_fraction=conversion.out_of_range_fraction,
        pif_pixels=int(pif_pixels), coefficient_bounds_ok=coeff_ok,
        passed=not failures, failures=tuple(failures),
    )
    return record, conversion.reflectance


def evaluate_site(records: Mapping[int, SiteYearQC], cell_year_median_clear: np.ndarray) -> SiteQC:
    """Drop the whole site if any year or the locked every-year cell check fails."""
    values = np.asarray(cell_year_median_clear, dtype=float)
    if values.ndim != 2 or values.shape[1] != 5:
        raise ValueError("Expected at-risk cell x five-year clear-observation medians.")
    if values.shape[0] == 0:
        fraction = 0.0
    else:
        fraction = float(np.all(values >= MIN_CELL_MEDIAN_CLEAR_OBS, axis=1).mean())
    failures = []
    failed_years = [year for year, record in records.items() if not record.passed]
    if failed_years:
        failures.append(f"failed_site_years:{failed_years}")
    if fraction < MIN_GOOD_CELL_FRACTION:
        failures.append("every_year_cell_clear_fraction")
    return SiteQC(tuple(records[year] for year in sorted(records)), fraction, not failures, tuple(failures))


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a saved risk-study QC JSON artifact.")
    parser.add_argument("json", type=Path)
    args = parser.parse_args()
    print(json.dumps(json.loads(args.json.read_text()), indent=2))


if __name__ == "__main__":
    main()
