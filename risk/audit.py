"""Seeded L9 manual label-audit draw with retained inclusion probabilities."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from .config import SEED

AUDIT_CODES = (
    "land-use conversion",
    "fire",
    "harvest-plantation cycle",
    "natural disturbance",
    "apparent GFC false positive",
)


def _loss_bin(values: pd.Series) -> pd.Categorical:
    array = values.to_numpy(dtype=float)
    labels = np.select(
        [np.isclose(array, 0.0), (array > 0) & (array < 0.25), array >= 0.25],
        ["0", "(0,25%)", ">=25%"], default="missing",
    )
    return pd.Categorical(labels, categories=["0", "(0,25%)", ">=25%"])


def draw_manual_audit(cells: pd.DataFrame, per_stratum: int = 2,
                      seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"site", "cohort", "future_loss_ratio", "grid_row", "grid_col"}
    if not required.issubset(cells):
        raise ValueError(f"Audit table lacks {sorted(required - set(cells.columns))}")
    frame = cells.copy()
    frame["loss_bin"] = _loss_bin(frame["future_loss_ratio"])
    rng = np.random.default_rng(seed)
    draws = []
    for (cohort, site, loss_bin), stratum in frame.groupby(
        ["cohort", "site", "loss_bin"], observed=False, sort=True
    ):
        n = len(stratum)
        if n == 0:
            continue
        take = min(per_stratum, n)
        chosen = rng.choice(stratum.index.to_numpy(), size=take, replace=False)
        sample = frame.loc[chosen, ["cohort", "site", "grid_row", "grid_col",
                                    "future_loss_ratio", "loss_bin"]].copy()
        sample["stratum_size"] = n
        sample["inclusion_probability"] = take / n
        sample["before_source"] = ""
        sample["before_date"] = ""
        sample["after_source"] = ""
        sample["after_date"] = ""
        sample["audit_code"] = ""
        sample["notes"] = ""
        draws.append(sample)
    audit = pd.concat(draws, ignore_index=True) if draws else pd.DataFrame()
    duplicate_count = int(math.ceil(0.10 * len(audit))) if len(audit) else 0
    duplicate_indices = rng.choice(len(audit), size=duplicate_count, replace=False) if duplicate_count else []
    duplicates = audit.iloc[duplicate_indices].copy()
    duplicates["minimum_recode_gap_days"] = 14
    # No score column is ever copied into either interpreter sheet.
    if any("score" in column.lower() for column in audit.columns):
        raise AssertionError("Interpreter audit draw is not blinded to model scores.")
    return audit, duplicates


def weighted_label_validity(coded: pd.DataFrame) -> pd.DataFrame:
    """Inverse-probability estimates kept separate for legacy/frame cohorts."""
    required = {"cohort", "audit_code", "inclusion_probability"}
    if not required.issubset(coded):
        raise ValueError(f"Coded audit lacks {sorted(required - set(coded.columns))}")
    if not set(coded["audit_code"].dropna()).issubset(AUDIT_CODES):
        raise ValueError("Coded audit contains an unrecognized L9 category.")
    records = []
    for cohort, group in coded.groupby("cohort", sort=True):
        weights = 1.0 / group["inclusion_probability"].to_numpy(dtype=float)
        valid = group["audit_code"].to_numpy() != "apparent GFC false positive"
        records.append({
            "cohort": cohort, "weighted_label_validity": float(np.average(valid, weights=weights)),
            "weighted_cells": float(weights.sum()), "audited_cells": len(group),
        })
        for code in AUDIT_CODES:
            records[-1][f"share_{code.replace(' ', '_').replace('-', '_')}"] = float(
                np.average(group["audit_code"].to_numpy() == code, weights=weights)
            )
    return pd.DataFrame(records)


def intra_rater_agreement(first_codes: pd.Series, delayed_codes: pd.Series) -> dict[str, float | int]:
    if len(first_codes) != len(delayed_codes) or len(first_codes) == 0:
        raise ValueError("Matched non-empty first/delayed code vectors are required.")
    return {
        "duplicates": len(first_codes),
        "raw_agreement": float(np.mean(first_codes.to_numpy() == delayed_codes.to_numpy())),
        "cohen_kappa": float(cohen_kappa_score(first_codes, delayed_codes, labels=list(AUDIT_CODES))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw the blinded L9 label audit.")
    parser.add_argument("cells", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit, duplicates = draw_manual_audit(pd.read_csv(args.cells))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output, index=False)
    duplicates.to_csv(args.output.with_name(args.output.stem + "_duplicates.csv"), index=False)
    print(f"Audit cells: {len(audit)}; delayed duplicates: {len(duplicates)}")


if __name__ == "__main__":
    main()
