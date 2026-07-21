"""Specification W entry points into shared model code.

The 12-site v11 defaults in :mod:`risk.models` remain unchanged.  This wrapper
supplies W's 36/35 counts and stamps the separate result namespace so fitted
state and outputs cannot be confused with the primary analysis.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from risk.models import ARMS, run_loso

from .specification_w import RESULT_NAMESPACE, SITES


def run_specification_w_loso(
    table: pd.DataFrame,
    pipeline: str,
    *,
    arms: Sequence[str] = tuple(ARMS),
    model_kinds: Sequence[str] = ("lr", "gbm"),
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    predictions, audit = run_loso(
        table,
        "frame_only",
        pipeline,
        arms=arms,
        model_kinds=model_kinds,
        expected_frame_sites=SITES,
    )
    predictions["specification"] = "Specification W"
    predictions["result_namespace"] = RESULT_NAMESPACE
    for record in audit:
        record["specification"] = "Specification W"
        record["result_namespace"] = RESULT_NAMESPACE
    return predictions, audit

