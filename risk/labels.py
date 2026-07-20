"""L5 eligible-forest universe, at-risk mask, and Hansen-detected outcome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .config import AT_RISK_LAND_FRACTION, PRIMARY_LABEL_THRESHOLD


@dataclass(frozen=True)
class Labels:
    eligible_forest_2020: np.ndarray
    future_loss: np.ndarray
    valid_land: np.ndarray
    at_risk: np.ndarray
    future_loss_ratio: np.ndarray
    positive: np.ndarray


def build_labels(counts: Mapping[str, np.ndarray],
                 threshold: float = PRIMARY_LABEL_THRESHOLD) -> Labels:
    valid = np.asarray(counts["valid_land"], dtype=np.int64)
    eligible = np.asarray(counts["eligible_forest_2020"], dtype=np.int64)
    future = np.asarray(counts["future_loss"], dtype=np.int64)
    if not (valid.shape == eligible.shape == future.shape):
        raise ValueError("L5 count arrays must share a shape.")
    if np.any(future > eligible):
        raise AssertionError("L5 future-loss numerator must be a subset of the denominator.")
    ratio = np.full(valid.shape, np.nan, dtype=np.float64)
    np.divide(future, eligible, out=ratio, where=eligible > 0)
    finite = np.isfinite(ratio)
    if np.any((ratio[finite] < 0) | (ratio[finite] > 1)):
        raise AssertionError("L5 future-loss ratio escaped [0,1].")
    at_risk = (valid > 0) & (eligible >= AT_RISK_LAND_FRACTION * valid)
    positive = at_risk & (ratio >= threshold)
    return Labels(eligible, future, valid, at_risk, ratio, positive)

