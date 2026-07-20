"""L4/L7 metrics, spatial uncertainty, concordance, and operational budgets."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from scipy.stats import wilcoxon
from sklearn.metrics import average_precision_score

from .config import (
    ALERT_BUDGETS,
    BOOTSTRAP_MAX_DRAW_MULTIPLIER,
    HIERARCHICAL_BOOTSTRAP_REPLICATES,
    MAX_RELIABLE_BLOCK_SIZE,
    MAX_ZERO_POSITIVE_FRACTION,
    MIN_BLOCK_SIZE,
    MORAN_MAX_LAG,
    MORAN_MIN_PAIRS,
    MORAN_THRESHOLD,
    SEED,
    SITE_BOOTSTRAP_REPLICATES,
)


@dataclass(frozen=True)
class ConfidenceInterval:
    lower: float | None
    upper: float | None
    status: str = "ok"


@dataclass(frozen=True)
class SiteBootstrap:
    delta_ap: float | None
    interval: ConfidenceInterval
    block_size: int | None
    zero_positive_fraction: float


def paired_site_metrics(y: np.ndarray, score_base: np.ndarray, score_history: np.ndarray) -> dict[str, float | int | None]:
    y = np.asarray(y, dtype=int)
    positives = int(y.sum())
    if positives == 0:
        return {"positives": 0, "base_rate": 0.0, "ap_base": None,
                "ap_history": None, "delta_ap": None}
    ap_base = float(average_precision_score(y, score_base))
    ap_history = float(average_precision_score(y, score_history))
    return {
        "positives": positives, "base_rate": float(y.mean()),
        "ap_base": ap_base, "ap_history": ap_history, "delta_ap": ap_history - ap_base,
    }


def alert_budget_metrics(y: np.ndarray, scores: np.ndarray, future_loss_pixels: np.ndarray,
                         budgets: Sequence[float] = ALERT_BUDGETS) -> list[dict[str, float]]:
    y = np.asarray(y, dtype=int)
    scores = np.asarray(scores, dtype=float)
    area = np.asarray(future_loss_pixels, dtype=float)
    # Stable ordering makes score ties deterministic without a tunable tie rule.
    order = np.argsort(-scores, kind="stable")
    output = []
    for budget in budgets:
        count = max(1, int(math.ceil(budget * len(y))))
        selected = order[:count]
        tp = int(y[selected].sum())
        precision = tp / count
        recall = tp / y.sum() if y.sum() else np.nan
        capture = area[selected].sum() / area.sum() if area.sum() else np.nan
        output.append({
            "budget": float(budget), "alerted_cells": count,
            "precision": float(precision), "positive_cell_capture": float(recall),
            "future_loss_area_capture": float(capture),
        })
    return output


def pearson_residuals(y: np.ndarray, scores: np.ndarray) -> np.ndarray:
    probability = np.clip(np.asarray(scores, dtype=float), 1e-6, 1 - 1e-6)
    return (np.asarray(y, dtype=float) - probability) / np.sqrt(probability * (1 - probability))


def moran_correlogram(coords_m: np.ndarray, residuals: np.ndarray) -> list[dict[str, float | int]]:
    coords = np.asarray(coords_m, dtype=float)
    z = np.asarray(residuals, dtype=float) - np.mean(residuals)
    denominator = float(np.sum(z * z))
    if denominator == 0 or len(z) < 2:
        return []
    distances_in_cells = pdist(coords) / 640.0
    pairs = np.column_stack(np.triu_indices(len(z), k=1))
    output = []
    for lag in range(1, MORAN_MAX_LAG + 1):
        selected = (distances_in_cells >= lag - 0.5) & (distances_in_cells < lag + 0.5)
        pair_count = int(selected.sum())
        if pair_count < MORAN_MIN_PAIRS:
            continue
        selected_pairs = pairs[selected]
        numerator = 2 * float(np.sum(z[selected_pairs[:, 0]] * z[selected_pairs[:, 1]]))
        weight_sum = 2 * pair_count
        moran_i = len(z) / weight_sum * numerator / denominator
        output.append({"lag": lag, "pairs": pair_count, "moran_i": float(moran_i)})
    return output


def correlation_range(coords_m: np.ndarray, y: np.ndarray, scores: np.ndarray) -> int | None:
    for record in moran_correlogram(coords_m, pearson_residuals(y, scores)):
        if record["moran_i"] < MORAN_THRESHOLD:
            return int(record["lag"])
    return None


def conservative_block_size(correlograms: Mapping[str, tuple[np.ndarray, np.ndarray, np.ndarray]]
                            ) -> tuple[int | None, str]:
    """Use the max range across both arms and both pipelines; never clamp at 8."""
    ranges = []
    for coords, y, scores in correlograms.values():
        measured = correlation_range(coords, y, scores)
        if measured is None:
            return None, "UNRELIABLE"
        ranges.append(measured)
    block_size = max(MIN_BLOCK_SIZE, max(ranges))
    if block_size > MAX_RELIABLE_BLOCK_SIZE:
        return block_size, "UNRELIABLE"
    return block_size, "ok"


def moving_block_indices(grid_rc: np.ndarray, block_size: int,
                         rng: np.random.Generator) -> np.ndarray:
    grid_rc = np.asarray(grid_rc, dtype=int)
    n = len(grid_rc)
    minimum = grid_rc.min(axis=0)
    maximum = grid_rc.max(axis=0)
    chunks = []
    count = 0
    attempts = 0
    while count < n:
        attempts += 1
        if attempts > n * 100:
            raise RuntimeError("Could not draw non-empty moving blocks.")
        origin_row = int(rng.integers(minimum[0], maximum[0] + 1))
        origin_col = int(rng.integers(minimum[1], maximum[1] + 1))
        selected = np.flatnonzero(
            (grid_rc[:, 0] >= origin_row) & (grid_rc[:, 0] < origin_row + block_size)
            & (grid_rc[:, 1] >= origin_col) & (grid_rc[:, 1] < origin_col + block_size)
        )
        if selected.size:
            chunks.append(selected)
            count += selected.size
    # The final full/edge-partial block is deliberately retained, even if N is exceeded.
    return np.concatenate(chunks)


def site_block_bootstrap(y: np.ndarray, score_base: np.ndarray, score_history: np.ndarray,
                         grid_rc: np.ndarray, block_size: int,
                         replicates: int = SITE_BOOTSTRAP_REPLICATES, seed: int = SEED
                         ) -> SiteBootstrap:
    point = paired_site_metrics(y, score_base, score_history)["delta_ap"]
    if block_size > MAX_RELIABLE_BLOCK_SIZE:
        return SiteBootstrap(
            None if point is None else float(point),
            ConfidenceInterval(None, None, "UNRELIABLE"), block_size, 0.0,
        )
    if point is None:
        return SiteBootstrap(None, ConfidenceInterval(None, None, "undefined"), block_size, 1.0)
    rng = np.random.default_rng(seed)
    deltas = []
    zero_positive = 0
    attempts = 0
    maximum_attempts = BOOTSTRAP_MAX_DRAW_MULTIPLIER * replicates
    while len(deltas) < replicates and attempts < maximum_attempts:
        attempts += 1
        indices = moving_block_indices(grid_rc, block_size, rng)
        if np.asarray(y)[indices].sum() == 0:
            zero_positive += 1
            continue
        metrics = paired_site_metrics(
            np.asarray(y)[indices], np.asarray(score_base)[indices], np.asarray(score_history)[indices]
        )
        deltas.append(float(metrics["delta_ap"]))
    zero_fraction = zero_positive / attempts if attempts else 1.0
    if zero_fraction > MAX_ZERO_POSITIVE_FRACTION or len(deltas) < replicates:
        return SiteBootstrap(float(point), ConfidenceInterval(None, None, "undefined"), block_size, zero_fraction)
    lower, upper = np.percentile(deltas, [2.5, 97.5])
    return SiteBootstrap(float(point), ConfidenceInterval(float(lower), float(upper)), block_size, zero_fraction)


def _one_block_delta(site: Mapping[str, Any], rng: np.random.Generator) -> float | None:
    for _ in range(BOOTSTRAP_MAX_DRAW_MULTIPLIER):
        indices = moving_block_indices(site["grid_rc"], int(site["block_size"]), rng)
        y = np.asarray(site["y"])[indices]
        if y.sum() == 0:
            continue
        return float(paired_site_metrics(
            y, np.asarray(site["score_base"])[indices], np.asarray(site["score_history"])[indices]
        )["delta_ap"])
    return None


def hierarchical_interval(sites: Sequence[Mapping[str, Any]], frame_equal_groups: bool = False,
                          replicates: int = HIERARCHICAL_BOOTSTRAP_REPLICATES,
                          seed: int = SEED) -> ConfidenceInterval:
    if any(site.get("status", "ok") != "ok" for site in sites):
        return ConfidenceInterval(None, None, "UNRELIABLE")
    rng = np.random.default_rng(seed)
    deltas = []
    attempts = 0
    maximum = BOOTSTRAP_MAX_DRAW_MULTIPLIER * replicates
    groups = sorted({site["group"] for site in sites})
    if frame_equal_groups and (len(groups) != 4 or any(sum(s["group"] == g for s in sites) != 3 for g in groups)):
        raise ValueError("Frame CI requires exactly three sites in each of four groups.")
    while len(deltas) < replicates and attempts < maximum:
        attempts += 1
        if frame_equal_groups:
            group_means = []
            valid = True
            for group in groups:
                pool = [site for site in sites if site["group"] == group]
                draw = rng.choice(len(pool), size=3, replace=True)
                values = [_one_block_delta(pool[int(index)], rng) for index in draw]
                if any(value is None for value in values):
                    valid = False
                    break
                group_means.append(float(np.mean(values)))
            if valid:
                deltas.append(float(np.mean(group_means)))
        else:
            draw = rng.choice(len(sites), size=len(sites), replace=True)
            values = [_one_block_delta(sites[int(index)], rng) for index in draw]
            if all(value is not None for value in values):
                deltas.append(float(np.mean(values)))
    if len(deltas) < replicates:
        return ConfidenceInterval(None, None, "undefined")
    lower, upper = np.percentile(deltas, [2.5, 97.5])
    return ConfidenceInterval(float(lower), float(upper), "ok")


def _ci_class(interval: ConfidenceInterval) -> str:
    if interval.status != "ok" or interval.lower is None or interval.upper is None:
        return "unreliable"
    if interval.lower > 0:
        return "positive"
    if interval.upper < 0:
        return "negative"
    return "contains_zero"


def concordance_verdict(normalized: ConfidenceInterval,
                        unnormalized: ConfidenceInterval) -> str:
    """The complete L4 decision table, including forced inconclusiveness."""
    normal_class = _ci_class(normalized)
    raw_class = _ci_class(unnormalized)
    if normal_class == raw_class == "positive":
        return "HISTORY ADDS VALUE"
    if normal_class == raw_class == "negative":
        return "HISTORY HARMS"
    if normal_class == raw_class == "contains_zero":
        return "NULL"
    return "INCONCLUSIVE"


def paired_wilcoxon(delta_ap: Sequence[float]) -> dict[str, float | int | None]:
    values = np.asarray(delta_ap, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"n_eval": 0, "statistic": None, "pvalue": None}
    result = wilcoxon(values)
    return {"n_eval": int(values.size), "statistic": float(result.statistic),
            "pvalue": float(result.pvalue)}


def grouped_permutation_importance(predict_scores: Any, features: pd.DataFrame,
                                   y: np.ndarray, feature_groups: Mapping[str, Sequence[str]],
                                   repeats: int = 100, seed: int = SEED) -> pd.DataFrame:
    """Conditional-on-other-fields group permutation, reported as association."""
    y = np.asarray(y, dtype=int)
    if y.sum() == 0:
        raise ValueError("Permutation AP is undefined for a zero-positive site.")
    baseline = float(average_precision_score(y, predict_scores(features)))
    rng = np.random.default_rng(seed)
    records = []
    for group, columns in feature_groups.items():
        drops = []
        for _ in range(repeats):
            order = rng.permutation(len(features))
            permuted = features.copy()
            # Permute the whole correlated family together, preserving its
            # internal joint distribution while all other families stay fixed.
            permuted.loc[:, list(columns)] = features.iloc[order][list(columns)].to_numpy()
            score = float(average_precision_score(y, predict_scores(permuted)))
            drops.append(baseline - score)
        records.append({
            "feature_group": group, "baseline_ap": baseline,
            "mean_ap_drop": float(np.mean(drops)),
            "p025": float(np.percentile(drops, 2.5)),
            "p975": float(np.percentile(drops, 97.5)),
        })
    return pd.DataFrame(records)


def coefficient_stability(coefficients: Mapping[str, Mapping[str, float]]) -> pd.DataFrame:
    """Summarize LR coefficient sign/magnitude across outer folds."""
    feature_names = sorted({name for fold in coefficients.values() for name in fold})
    records = []
    for name in feature_names:
        values = np.array([fold.get(name, np.nan) for fold in coefficients.values()], dtype=float)
        values = values[np.isfinite(values)]
        records.append({
            "feature": name, "folds": len(values), "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "positive_fraction": float(np.mean(values > 0)),
            "negative_fraction": float(np.mean(values < 0)),
        })
    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize out-of-site risk scores.")
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    table = pd.read_csv(args.predictions)
    print(table.groupby(["analysis", "pipeline", "model", "arm"])["site"].nunique())


if __name__ == "__main__":
    main()
