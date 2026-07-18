import numpy as np
import pytest

from risk.config import FEATURE_YEARS
from risk.features import condition_features, fixed_support_mask


BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")


def _trajectory():
    data = {}
    for offset, year in enumerate(FEATURE_YEARS):
        array = np.zeros((6, 5, 5), dtype=np.float32)
        array[0] = 0.05
        array[1] = 0.06
        array[2] = 0.10
        array[3] = 0.50 + offset * 0.01
        array[4] = 0.20
        array[5] = 0.15
        array[:, 4, :] = 0.99  # outside the locked 20-pixel support
        data[year] = array
    return data


def test_fixed_support_must_be_bit_identical_in_every_feature_year():
    base = np.ones((5, 5), dtype=bool)
    base[4, :] = False
    supports = {year: base.copy() for year in FEATURE_YEARS}
    assert np.array_equal(fixed_support_mask(supports), base)
    supports[FEATURE_YEARS[-1]][0, 0] = False
    with pytest.raises(AssertionError, match="support changed"):
        fixed_support_mask(supports)


def test_condition_extraction_uses_one_support_for_every_year():
    support = np.ones((5, 5), dtype=bool)
    support[4, :] = False
    medians = {year: {name: 0.5 for name in ("ndvi", "ndmi", "nbr")}
               for year in FEATURE_YEARS}
    result = condition_features(
        _trajectory(), BANDS, support,
        pixel_windows=np.array([[0, 0, 5, 5]]), pif_index_medians=medians,
    )
    assert not result.loc[0, "excluded_support_lt20"]
    # NIR rises by exactly .01 each year on the fixed set; outside 0.99 values
    # never enter any annual summary.
    assert result.loc[0, "d_ndvi_slope_mean"] > 0
    assert result.loc[0, "c_ndvi_mean"] < 0.75
