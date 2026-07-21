"""Locked feature arms, equal-site weights, nested tuning, and two full LOSO runs."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import GBM_GRID, LR_C_GRID, MIN_VALID_INNER_FOLDS, SEED
from .config import COMBINED_MINIMUM

ARMS = {
    "A": (),
    "S+B": ("S", "B"),
    "S+C": ("S", "C"),
    "S+B+C": ("S", "B", "C"),
    "S+B+C+D": ("S", "B", "C", "D"),
}
PRIMARY_CONTRAST = ("S+B+C", "S+B+C+D")
SECONDARY_CONTRAST = ("S+B", "S+B+C")


@dataclass(frozen=True)
class TuningResult:
    model_kind: str
    candidate_index: int
    parameters: Mapping[str, Any]
    mean_held_site_ap: float | None
    valid_folds: int
    fallback: bool


class InterceptOnly:
    def fit(self, y: np.ndarray, sample_weight: np.ndarray) -> "InterceptOnly":
        self.score_ = float(np.average(y, weights=sample_weight))
        return self

    def predict_proba(self, n: int) -> np.ndarray:
        return np.column_stack((np.full(n, 1 - self.score_), np.full(n, self.score_)))


def columns_for_arm(columns: Iterable[str], arm: str) -> list[str]:
    if arm not in ARMS:
        raise ValueError(arm)
    prefixes = tuple(f"{block.lower()}_" for block in ARMS[arm])
    return sorted(column for column in columns if column.startswith(prefixes)) if prefixes else []


def equal_site_class_weights(site_ids: Sequence[object], y: Sequence[int]) -> tuple[np.ndarray, list[str]]:
    """Each site has equal total weight; classes split that site's weight equally."""
    sites = np.asarray(site_ids)
    labels = np.asarray(y, dtype=int)
    unique_sites = np.unique(sites)
    weights = np.zeros(len(labels), dtype=np.float64)
    one_class = []
    for site in unique_sites:
        site_mask = sites == site
        classes = np.unique(labels[site_mask])
        if len(classes) == 1:
            weights[site_mask] = 1.0 / site_mask.sum()
            one_class.append(str(site))
        else:
            for class_id in classes:
                class_mask = site_mask & (labels == class_id)
                weights[class_mask] = (1.0 / len(classes)) / class_mask.sum()
    weights /= len(unique_sites)
    if not np.allclose([weights[sites == site].sum() for site in unique_sites], 1 / len(unique_sites)):
        raise AssertionError("Training sites do not have equal total weight.")
    return weights, one_class


def _candidate_parameters(model_kind: str) -> list[dict[str, Any]]:
    if model_kind == "lr":
        return [{"C": value} for value in LR_C_GRID]
    if model_kind == "gbm":
        return [dict(value) for value in GBM_GRID]
    raise ValueError(model_kind)


def _model(model_kind: str, parameters: Mapping[str, Any]) -> Any:
    if model_kind == "lr":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(
                penalty="l2", solver="lbfgs", C=float(parameters["C"]),
                max_iter=5_000, random_state=SEED,
            )),
        ])
    if model_kind == "gbm":
        return HistGradientBoostingClassifier(
            **parameters, random_state=SEED, early_stopping=False
        )
    raise ValueError(model_kind)


def _fit(model: Any, model_kind: str, x: np.ndarray, y: np.ndarray,
         weights: np.ndarray) -> Any:
    if len(np.unique(y)) < 2:
        raise ValueError("Model training data contain only one outcome class.")
    if model_kind == "lr":
        return model.fit(x, y, classifier__sample_weight=weights)
    return model.fit(x, y, sample_weight=weights)


def tune(train: pd.DataFrame, features: Sequence[str], model_kind: str,
         site_column: str = "site", label_column: str = "label") -> TuningResult:
    candidates = _candidate_parameters(model_kind)
    sites = list(dict.fromkeys(train[site_column].tolist()))
    candidate_scores: list[list[float]] = [[] for _ in candidates]
    for held_site in sites:
        inner_train = train[train[site_column] != held_site]
        validation = train[train[site_column] == held_site]
        y_validation = validation[label_column].to_numpy(dtype=int)
        if y_validation.sum() == 0:
            continue
        y_train = inner_train[label_column].to_numpy(dtype=int)
        if len(np.unique(y_train)) < 2:
            continue
        weights, _ = equal_site_class_weights(inner_train[site_column], y_train)
        for index, parameters in enumerate(candidates):
            model = _fit(
                _model(model_kind, parameters), model_kind,
                inner_train[list(features)].to_numpy(dtype=float), y_train, weights,
            )
            scores = model.predict_proba(validation[list(features)].to_numpy(dtype=float))[:, 1]
            candidate_scores[index].append(float(average_precision_score(y_validation, scores)))
    valid_folds = max((len(scores) for scores in candidate_scores), default=0)
    if valid_folds < MIN_VALID_INNER_FOLDS:
        return TuningResult(model_kind, 0, candidates[0], None, valid_folds, True)
    means = [float(np.mean(scores)) if scores else -np.inf for scores in candidate_scores]
    # np.argmax returns the earliest candidate, which is the locked simplicity tie-break.
    best = int(np.argmax(means))
    return TuningResult(model_kind, best, candidates[best], means[best], len(candidate_scores[best]), False)


def fit_predict_outer(train: pd.DataFrame, test: pd.DataFrame, arm: str, model_kind: str,
                      site_column: str = "site", label_column: str = "label",
                      extra_features: Sequence[str] = ()
                      ) -> tuple[np.ndarray, TuningResult | None, list[str]]:
    features = columns_for_arm(train.columns, arm) + sorted(extra_features)
    y_train = train[label_column].to_numpy(dtype=int)
    weights, one_class_sites = equal_site_class_weights(train[site_column], y_train)
    if arm == "A":
        model = InterceptOnly().fit(y_train, weights)
        return model.predict_proba(len(test))[:, 1], None, one_class_sites
    tuning = tune(train, features, model_kind, site_column, label_column)
    model = _fit(
        _model(model_kind, tuning.parameters), model_kind,
        train[features].to_numpy(dtype=float), y_train, weights,
    )
    scores = model.predict_proba(test[features].to_numpy(dtype=float))[:, 1]
    return scores, tuning, one_class_sites


def run_loso(table: pd.DataFrame, analysis: str, pipeline: str,
             arms: Sequence[str] = tuple(ARMS), model_kinds: Sequence[str] = ("lr", "gbm"),
             site_column: str = "site", label_column: str = "label",
             acquisition_adjusted: bool = False,
             expected_frame_sites: int = 12,
             ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if analysis not in {"combined", "frame_only"}:
        raise ValueError(analysis)
    if pipeline not in {"normalized", "unnormalized"}:
        raise ValueError(pipeline)
    if analysis == "frame_only":
        data = table[table["cohort"] == "frame"].copy()
        if (data["cohort"] != "frame").any():
            raise AssertionError("Legacy site entered frame-only LOSO.")
    else:
        data = table.copy()
    sites = list(dict.fromkeys(data[site_column].tolist()))
    metadata_features = sorted(column for column in data if column.startswith("m_")) if acquisition_adjusted else []
    if analysis == "frame_only" and len(sites) != expected_frame_sites:
        raise RuntimeError(
            f"Frame-only LOSO requires all {expected_frame_sites} frame sites, got {len(sites)}."
        )
    if analysis == "combined" and len(sites) < COMBINED_MINIMUM:
        raise RuntimeError(f"Combined LOSO requires at least {COMBINED_MINIMUM} sites, got {len(sites)}.")
    predictions = []
    audit = []
    for held_site in sites:
        train = data[data[site_column] != held_site]
        test = data[data[site_column] == held_site]
        if (
            analysis == "frame_only"
            and train[site_column].nunique() != expected_frame_sites - 1
        ):
            raise AssertionError(
                "Each frame-only outer fold must train on exactly "
                f"{expected_frame_sites - 1} frame sites."
            )
        for model_kind in model_kinds:
            for arm in arms:
                scores, tuning, one_class_sites = fit_predict_outer(
                    train, test, arm, model_kind, site_column, label_column, metadata_features
                )
                fold = test[[site_column, label_column, "cohort", "group", "grid_row", "grid_col",
                             "future_loss_pixels"]].copy()
                fold["score"] = scores
                fold["analysis"] = analysis
                fold["pipeline"] = pipeline
                fold["model"] = model_kind
                fold["arm"] = arm
                fold["acquisition_adjusted"] = acquisition_adjusted
                predictions.append(fold)
                audit.append({
                    "held_site": held_site, "analysis": analysis, "pipeline": pipeline,
                    "model": model_kind, "arm": arm,
                    "n_training_sites": int(train[site_column].nunique()),
                    "one_class_training_sites": one_class_sites,
                    "tuning": asdict(tuning) if tuning else None,
                })
    return pd.concat(predictions, ignore_index=True), audit


def run_two_analyses(table: pd.DataFrame, pipeline: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    combined, audit_combined = run_loso(table, "combined", pipeline)
    frame, audit_frame = run_loso(table, "frame_only", pipeline)
    return pd.concat((combined, frame), ignore_index=True), audit_combined + audit_frame


def run_acquisition_robustness(table: pd.DataFrame, pipeline: str
                               ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Secondary only: add identical acquisition fields to both primary arms."""
    adjusted = []
    audit = []
    for analysis in ("combined", "frame_only"):
        predictions, current_audit = run_loso(
            table, analysis, pipeline, arms=PRIMARY_CONTRAST,
            acquisition_adjusted=True,
        )
        adjusted.append(predictions)
        audit.extend(current_audit)
    return pd.concat(adjusted, ignore_index=True), audit


def run_zero_prior_sensitivity(table: pd.DataFrame, pipeline: str
                               ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    restricted = table[np.isclose(table["b_own_prior_loss"], 0.0)].copy()
    return run_two_analyses(restricted, pipeline)


def run_leave_one_biome_out(table: pd.DataFrame, pipeline: str,
                            arms: Sequence[str] = PRIMARY_CONTRAST,
                            model_kinds: Sequence[str] = ("lr", "gbm")
                            ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Descriptive secondary; tuning remains leave-one-training-site-out."""
    predictions = []
    audit = []
    for held_group in sorted(table["group"].unique()):
        train = table[table["group"] != held_group]
        test = table[table["group"] == held_group]
        for model_kind in model_kinds:
            for arm in arms:
                scores, tuning, one_class = fit_predict_outer(train, test, arm, model_kind)
                fold = test[["site", "label", "cohort", "group", "grid_row", "grid_col",
                             "future_loss_pixels"]].copy()
                fold["score"] = scores
                fold["analysis"] = "leave_one_biome_out"
                fold["pipeline"] = pipeline
                fold["model"] = model_kind
                fold["arm"] = arm
                predictions.append(fold)
                audit.append({
                    "held_group": held_group, "pipeline": pipeline, "model": model_kind,
                    "arm": arm, "n_training_sites": int(train["site"].nunique()),
                    "one_class_training_sites": one_class,
                    "tuning": asdict(tuning) if tuning else None,
                })
    return pd.concat(predictions, ignore_index=True), audit


def main() -> None:
    from forecast.prelift_sandbox import require_pre_lift_role

    require_pre_lift_role("tuning")
    parser = argparse.ArgumentParser(description="Run combined and clean frame-only full LOSO analyses.")
    parser.add_argument("table", type=Path, help="Prepared cell-level CSV")
    parser.add_argument("--pipeline", choices=("normalized", "unnormalized"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    table = pd.read_csv(args.table)
    predictions, audit = run_two_analyses(table, args.pipeline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output, index=False)
    args.output.with_suffix(".audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Wrote {len(predictions):,} out-of-site scores -> {args.output}")


if __name__ == "__main__":
    main()
