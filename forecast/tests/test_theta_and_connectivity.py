"""The frozen theta grid and both frozen connectivities must actually run.

Both were previously impossible: the worker hardcoded theta=30 and the
component helper hardcoded 8-connectivity while returning only a count.
"""

from __future__ import annotations

import numpy as np
import pytest

from forecast.gfc_censor import FROZEN_TREECOVER_THRESHOLDS
from forecast.gfc_censor_worker import (
    FROZEN_TREECOVER_THRESHOLDS as WORKER_THRESHOLDS,
    _derive_masks,
    formulas,
)
from forecast.precheck_evaluability import (
    FROZEN_CONNECTIVITIES,
    count_components,
    label_components,
)


def _arrays(treecover: np.ndarray, lossyear: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "treecover2000": treecover,
        "datamask": np.ones_like(treecover, dtype=np.uint8),
        "lossyear": lossyear,
    }


# --- theta -----------------------------------------------------------------

def test_supervisor_and_worker_agree_on_the_frozen_grid():
    assert FROZEN_TREECOVER_THRESHOLDS == WORKER_THRESHOLDS
    assert 30 in FROZEN_TREECOVER_THRESHOLDS, "30 % remains the primary population"


@pytest.mark.parametrize("threshold", FROZEN_TREECOVER_THRESHOLDS)
def test_every_frozen_threshold_produces_masks(threshold):
    treecover = np.array([[5, 20], [40, 80]], dtype=np.uint8)
    lossyear = np.array([[0, 21], [0, 21]], dtype=np.uint8)
    masks = _derive_masks("pre_lift", _arrays(treecover, lossyear), threshold)
    assert set(masks) == {
        "eligible_2020", "eligible_2021", "eligible_2022",
        "positive_2021", "positive_2022",
    }


def test_theta_actually_changes_the_population():
    """A permissive theta must admit pixels a strict one excludes."""

    treecover = np.array([[5, 20], [40, 80]], dtype=np.uint8)
    lossyear = np.zeros((2, 2), dtype=np.uint8)
    arrays = _arrays(treecover, lossyear)

    admitted = {
        theta: int(_derive_masks("pre_lift", arrays, theta)["eligible_2020"].sum())
        for theta in FROZEN_TREECOVER_THRESHOLDS
    }
    assert admitted[10] == 3   # 20, 40, 80
    assert admitted[30] == 2   # 40, 80
    assert admitted[75] == 1   # 80
    # Nested by construction, which is why theta isolation is by artifact.
    assert admitted[10] >= admitted[25] >= admitted[30] >= admitted[50] >= admitted[75]


def test_threshold_outside_the_frozen_grid_is_refused():
    arrays = _arrays(
        np.array([[40]], dtype=np.uint8), np.array([[0]], dtype=np.uint8)
    )
    with pytest.raises(ValueError, match="outside the frozen grid"):
        _derive_masks("pre_lift", arrays, 31)


def test_formulas_render_at_the_run_threshold():
    assert "treecover2000 >= 75" in formulas(75)["eligible_2020"]
    # lossyear stays a RAW Hansen code, never a year.
    assert "lossyear > 20" in formulas(75)["eligible_2020"]
    assert "lossyear == 21" in formulas(75)["positive_2021"]


# --- connectivity ----------------------------------------------------------

def test_both_frozen_connectivities_are_available():
    assert FROZEN_CONNECTIVITIES == (8, 4)


def test_diagonal_touching_pixels_separate_under_four_connectivity():
    """The case that makes the sensitivity meaningful.

    Two diagonally adjacent pairs are ONE component under 8-connectivity and
    TWO under 4-connectivity.
    """

    mask = np.array([
        [1, 1, 0, 0],
        [0, 0, 1, 1],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ], dtype=bool)

    assert count_components(mask, connectivity=8) == 1
    assert count_components(mask, connectivity=4) == 2


def test_two_pixel_floor_applies_to_both_connectivities():
    mask = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 1],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ], dtype=bool)
    # The lone pixel is below the floor under either rule.
    assert count_components(mask, connectivity=8) == 1
    assert count_components(mask, connectivity=4) == 1


def test_label_components_returns_labels_and_sizes():
    mask = np.array([
        [1, 1, 0],
        [0, 0, 0],
        [0, 1, 1],
    ], dtype=bool)
    labels, sizes = label_components(mask, connectivity=4)
    assert sizes.tolist() == [2, 2]
    assert labels.max() == 2


def test_label_components_handles_an_empty_mask():
    labels, sizes = label_components(np.zeros((3, 3), dtype=bool))
    assert sizes.size == 0
    assert labels.max() == 0
    assert count_components(np.zeros((3, 3), dtype=bool)) == 0


def test_unknown_connectivity_is_refused():
    with pytest.raises(ValueError, match="outside the frozen set"):
        label_components(np.zeros((2, 2), dtype=bool), connectivity=6)


def test_default_connectivity_remains_eight():
    """8-connectivity is primary; the default must not silently change."""

    mask = np.array([[1, 0], [0, 1]], dtype=bool)
    assert count_components(mask) == count_components(mask, connectivity=8)
