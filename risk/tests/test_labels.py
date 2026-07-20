import numpy as np
import pytest

from risk.labels import build_labels


def test_l5_numerator_subset_and_ratio_bounds():
    labels = build_labels({
        "valid_land": np.array([100, 100, 0]),
        "eligible_forest_2020": np.array([50, 20, 0]),
        "future_loss": np.array([25, 20, 0]),
    })
    assert labels.future_loss_ratio[:2].tolist() == [0.5, 1.0]
    assert np.isnan(labels.future_loss_ratio[2])
    assert np.all((labels.future_loss_ratio[:2] >= 0) & (labels.future_loss_ratio[:2] <= 1))
    assert labels.at_risk.tolist() == [True, False, False]

    with pytest.raises(AssertionError, match="subset"):
        build_labels({
            "valid_land": np.array([100]),
            "eligible_forest_2020": np.array([20]),
            "future_loss": np.array([21]),
        })

