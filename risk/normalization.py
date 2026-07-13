"""Locked PIF/Theil--Sen mapping of every feature year onto 2020."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.ndimage import distance_transform_edt
from sklearn.linear_model import TheilSenRegressor

from .config import (
    FEATURE_YEARS,
    MIN_PIF_PIXELS,
    NORMALIZATION_GAIN_BOUNDS,
    NORMALIZATION_OFFSET_BOUNDS,
    PIF_CLEAR_OBS_MIN,
    PIF_MAX_SAMPLE,
    PIF_TREECOVER_THRESHOLD,
    REFERENCE_YEAR,
    SEED,
    assert_feature_years,
)


@dataclass(frozen=True)
class BandTransform:
    gain: float
    offset: float
    pif_count: int
    post_out_of_range_fraction: float | None = None


def build_pif_mask(datamask: np.ndarray, treecover2000: np.ndarray,
                   prior_loss_2001_2020: np.ndarray,
                   clearobs_by_year: Mapping[int, np.ndarray],
                   pixel_size_m: tuple[float, float]) -> np.ndarray:
    years = assert_feature_years(clearobs_by_year)
    if set(years) != set(FEATURE_YEARS):
        raise ValueError("PIF clear criterion requires all five locked feature years.")
    shapes = {np.asarray(value).shape for value in clearobs_by_year.values()}
    shapes.update({datamask.shape, treecover2000.shape, prior_loss_2001_2020.shape})
    if len(shapes) != 1:
        raise ValueError("PIF inputs must be sampled on the native Hansen grid.")
    distance = distance_transform_edt(~np.asarray(prior_loss_2001_2020, dtype=bool), sampling=pixel_size_m)
    clear_all = np.logical_and.reduce([
        np.asarray(clearobs_by_year[year]) >= PIF_CLEAR_OBS_MIN for year in FEATURE_YEARS
    ])
    return (
        (datamask == 1) & (treecover2000 >= PIF_TREECOVER_THRESHOLD)
        & ~np.asarray(prior_loss_2001_2020, dtype=bool)
        & (distance >= 1_920.0) & clear_all
    )


def fit_transforms(reflectance_by_year: Mapping[int, np.ndarray], pif_mask: np.ndarray,
                   band_names: tuple[str, ...]) -> dict[int, dict[str, BandTransform]]:
    years = assert_feature_years(reflectance_by_year)
    if set(years) != set(FEATURE_YEARS):
        raise ValueError("Normalization requires exactly 2016--2020.")
    pif_indices = np.flatnonzero(np.asarray(pif_mask, dtype=bool).ravel())
    if pif_indices.size < MIN_PIF_PIXELS:
        raise ValueError(f"PIF count {pif_indices.size} is below locked minimum {MIN_PIF_PIXELS}.")
    if pif_indices.size > PIF_MAX_SAMPLE:
        pif_indices = np.random.default_rng(SEED).choice(
            pif_indices, size=PIF_MAX_SAMPLE, replace=False
        )
    reference = np.asarray(reflectance_by_year[REFERENCE_YEAR])
    if reference.shape[0] != len(band_names):
        raise ValueError("Band names do not match reflectance arrays.")
    transforms: dict[int, dict[str, BandTransform]] = {}
    for year in FEATURE_YEARS:
        if year == REFERENCE_YEAR:
            transforms[year] = {name: BandTransform(1.0, 0.0, len(pif_indices)) for name in band_names}
            continue
        source = np.asarray(reflectance_by_year[year])
        transforms[year] = {}
        for band_index, name in enumerate(band_names):
            x = source[band_index].ravel()[pif_indices]
            y = reference[band_index].ravel()[pif_indices]
            finite = np.isfinite(x) & np.isfinite(y)
            if int(finite.sum()) < MIN_PIF_PIXELS:
                raise ValueError(
                    f"{year} {name} has only {int(finite.sum())} finite PIF pixels; "
                    f"minimum is {MIN_PIF_PIXELS}."
                )
            model = TheilSenRegressor(
                fit_intercept=True, random_state=SEED, max_subpopulation=10_000
            ).fit(x[finite, None], y[finite])
            gain = float(model.coef_[0])
            offset = float(model.intercept_)
            if not (NORMALIZATION_GAIN_BOUNDS[0] <= gain <= NORMALIZATION_GAIN_BOUNDS[1]):
                raise ValueError(f"{year} {name} gain {gain} fails L2.")
            if not (NORMALIZATION_OFFSET_BOUNDS[0] <= offset <= NORMALIZATION_OFFSET_BOUNDS[1]):
                raise ValueError(f"{year} {name} offset {offset} fails L2.")
            transforms[year][name] = BandTransform(gain, offset, int(finite.sum()))
    return transforms


def apply_transforms(reflectance_by_year: Mapping[int, np.ndarray], band_names: tuple[str, ...],
                     transforms: Mapping[int, Mapping[str, BandTransform]], support: np.ndarray
                     ) -> tuple[dict[int, np.ndarray], dict[int, dict[str, BandTransform]]]:
    output: dict[int, np.ndarray] = {}
    audited: dict[int, dict[str, BandTransform]] = {}
    support = np.asarray(support, dtype=bool)
    for year in assert_feature_years(reflectance_by_year):
        values = np.asarray(reflectance_by_year[year], dtype=np.float32).copy()
        audited[year] = {}
        for index, name in enumerate(band_names):
            record = transforms[year][name]
            transformed = values[index] * record.gain + record.offset
            selected = support & np.isfinite(transformed)
            fraction = float(((transformed < 0) | (transformed > 1))[selected].mean())
            values[index] = np.clip(transformed, 0.0, 1.0)
            audited[year][name] = BandTransform(
                record.gain, record.offset, record.pif_count, fraction
            )
        output[year] = values
    return output, audited
