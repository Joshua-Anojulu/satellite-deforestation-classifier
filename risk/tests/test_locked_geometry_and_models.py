import numpy as np
import pytest

import risk.evaluation as evaluation
from risk.config import assert_feature_years
from risk.models import equal_site_class_weights
from risk.seasons import driest_four_month_window, feature_period


def test_no_upper_clamp_at_eight(monkeypatch):
    monkeypatch.setattr(evaluation, "correlation_range", lambda *args: 15)
    dummy = np.ones(3)
    block, status = evaluation.conservative_block_size({
        "normalized_base": (np.ones((3, 2)), dummy, dummy),
        "normalized_history": (np.ones((3, 2)), dummy, dummy),
        "unnormalized_base": (np.ones((3, 2)), dummy, dummy),
        "unnormalized_history": (np.ones((3, 2)), dummy, dummy),
    })
    assert block == 15
    assert status == "UNRELIABLE"


def test_each_training_site_has_equal_total_weight_and_class_balance():
    sites = np.array(["a", "a", "a", "b", "b"])
    y = np.array([0, 0, 1, 0, 1])
    weights, one_class = equal_site_class_weights(sites, y)
    assert one_class == []
    assert weights[sites == "a"].sum() == pytest.approx(0.5)
    assert weights[sites == "b"].sum() == pytest.approx(0.5)
    assert weights[(sites == "a") & (y == 0)].sum() == pytest.approx(0.25)
    assert weights[(sites == "a") & (y == 1)].sum() == pytest.approx(0.25)


def test_feature_year_assertion_and_circular_window():
    with pytest.raises(AssertionError):
        assert_feature_years((2016, 2021))
    assert driest_four_month_window(np.ones(12)) == 1
    assert feature_period(2020, 11) == ("2019-11-01", "2020-02-29")

