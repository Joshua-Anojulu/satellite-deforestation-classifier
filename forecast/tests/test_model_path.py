import pandas as pd

from forecast.model_path import run_specification_w_loso
from forecast.specification_w import RESULT_NAMESPACE
from risk.config import FRAME_REQUIRED, FRAME_SITES_PER_GROUP, FEATURE_YEARS
from risk.models import run_loso


def _table(site_count: int) -> pd.DataFrame:
    records = []
    for site_index in range(site_count):
        for label in (0, 1):
            records.append({
                "site": f"site-{site_index:02d}",
                "label": label,
                "cohort": "frame",
                "group": "group",
                "grid_row": label,
                "grid_col": site_index,
                "future_loss_pixels": label,
            })
    return pd.DataFrame(records)


def test_primary_frame_constants_and_default_loso_counts_remain_unchanged():
    assert FRAME_SITES_PER_GROUP == 3
    assert FRAME_REQUIRED == 12
    assert FEATURE_YEARS == (2018, 2019, 2020)
    predictions, audit = run_loso(
        _table(12), "frame_only", "normalized", arms=("A",), model_kinds=("lr",)
    )
    assert len(predictions) == 24
    assert {record["n_training_sites"] for record in audit} == {11}
    assert "result_namespace" not in predictions


def test_w_model_wrapper_uses_36_outer_and_35_training_sites_in_own_namespace():
    predictions, audit = run_specification_w_loso(
        _table(36), "normalized", arms=("A",), model_kinds=("lr",)
    )
    assert len(predictions) == 72
    assert set(predictions["specification"]) == {"Specification W"}
    assert set(predictions["result_namespace"]) == {RESULT_NAMESPACE}
    assert {record["n_training_sites"] for record in audit} == {35}
    assert {record["result_namespace"] for record in audit} == {RESULT_NAMESPACE}

