"""AMENDMENT-3 regression: the imagery axis and the Hansen axis must stay separate.

AMENDMENT-3 shortened FEATURE_YEARS to 2018--2020 because the 2016/2017 Sentinel-2
archive cannot reach the L2 clear-observation gate. Hansen is unaffected: it covers
2016--2020 regardless of the optical archive, and b_trend (block B, the CONTAGION
BASELINE the study measures incremental information against) is fit on that full
five-point series.

_slope() originally took its x-axis implicitly from FEATURE_YEARS and was shared by
both callers. Shrinking FEATURE_YEARS would then have fit 3 x-values against block B's
5 y-values, silently corrupting the control the whole result rests on.
"""

import numpy as np
import pytest

from risk.config import FEATURE_YEARS, HANSEN_TREND_YEARS
from risk.features import _slope, neighborhood_hansen_features


def test_hansen_trend_axis_is_five_points_and_independent_of_feature_years():
    assert HANSEN_TREND_YEARS == (2016, 2017, 2018, 2019, 2020)
    assert len(HANSEN_TREND_YEARS) == 5
    # The whole point of the amendment: the imagery window shrank, Hansen's did not.
    assert len(FEATURE_YEARS) < len(HANSEN_TREND_YEARS)


def test_slope_requires_one_year_per_value():
    with pytest.raises(ValueError, match="one year per value"):
        _slope([1.0, 2.0, 3.0, 4.0, 5.0], FEATURE_YEARS)  # 5 values, 3 years


def test_slope_is_correct_on_each_axis():
    # +2 loss pixels per year across the five Hansen years.
    assert _slope([0, 2, 4, 6, 8], HANSEN_TREND_YEARS) == pytest.approx(2.0)
    # +0.5 per year across the three feature years.
    assert _slope([1.0, 1.5, 2.0], FEATURE_YEARS) == pytest.approx(0.5)


def test_b_trend_still_reads_all_five_hansen_loss_years():
    """A cell whose loss is concentrated in 2016--2017 must yield a NEGATIVE trend.

    If b_trend had been narrowed to the 2018--2020 imagery window, that early loss
    would be invisible and the trend would come back ~0 instead.
    """
    # 3x3 native grid, all valid land, all inside the 1,920 m neighborhood.
    lossyear = np.array([
        [16, 16, 16],
        [17, 17, 0],
        [0, 0, 0],
    ], dtype=np.int16)
    datamask = np.ones((3, 3), dtype=np.uint8)
    xs = np.array([0.0, 30.0, 60.0])
    ys = np.array([0.0, 30.0, 60.0])
    centres = np.array([[30.0, 30.0]])

    out = neighborhood_hansen_features(lossyear, datamask, xs, ys, centres)

    # Loss is 3 pixels in 2016, 2 in 2017, 0 in 2018-2020 -> a declining series.
    assert out["b_trend"][0] < 0, "early (2016-17) loss vanished from b_trend"
    # And it is still visible to the cumulative 5-year density.
    assert out["b_density_5"][0] > 0
