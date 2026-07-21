import pytest

from forecast.audit_allocation import (
    allocate_detector_audit,
    finite_population_correction,
    largest_remainder_with_caps,
    stratified_ratio_variance,
)


def test_n_zero_is_not_a_stratum_and_receives_no_sample():
    result = allocate_detector_audit({"empty": 0, "active": 100}, budget=20)
    assert result.allocations == {"active": 20, "empty": 0}
    assert result.zero_population_sites == ("empty",)
    assert "empty" not in result.census_sites


def test_populations_at_or_below_five_are_censuses_before_allocation():
    result = allocate_detector_audit({"a": 1, "b": 5, "c": 100}, budget=20)
    assert result.allocations == {"a": 1, "b": 5, "c": 14}
    assert result.census_sites == ("a", "b")


def test_every_site_is_censused_when_remaining_population_fits_budget():
    result = allocate_detector_audit({"a": 4, "b": 6, "c": 7}, budget=180)
    assert result.allocations == {"a": 4, "b": 6, "c": 7}
    assert result.realised_total == 17
    assert result.census_sites == ("a", "b", "c")


def test_floor_overage_is_raised_and_disclosed():
    result = allocate_detector_audit({"a": 10, "b": 10, "c": 10}, budget=5)
    assert result.allocations == {"a": 2, "b": 2, "c": 2}
    assert result.effective_budget == 6
    assert result.floor_overage == 1


def test_caps_and_iterative_largest_remainder_redistribution():
    assert largest_remainder_with_caps({"a": 1, "b": 2, "c": 100}, 102) == {
        "a": 1, "b": 2, "c": 99,
    }
    # The frozen example that exposed proportional-to-N overflow: the six-pixel
    # site is capped at census, and the excess stays with the large site.
    result = allocate_detector_audit({"a": 6, "b": 175}, budget=180)
    assert result.allocations == {"a": 6, "b": 174}
    assert result.realised_total == 180


def test_largest_remainder_ties_break_by_ascending_site_id():
    assert largest_remainder_with_caps({"c": 1, "a": 1, "b": 1}, 2) == {
        "a": 1, "b": 1, "c": 0,
    }


def test_k9_strata_sum_to_the_unchanged_180_budget():
    result = allocate_detector_audit({f"site-{index}": 100 for index in range(9)})
    assert result.realised_total == result.effective_budget == 180
    assert set(result.allocations.values()) == {20}
    assert min(result.allocations.values()) >= 2


def test_fpc_is_zero_for_censuses_and_enters_ratio_variance():
    assert finite_population_correction(5, 5) == 0
    assert finite_population_correction(10, 2) == pytest.approx(0.8)
    assert finite_population_correction(0, 0) == 0
    variance = stratified_ratio_variance(
        populations={"census": 5, "sample": 10},
        allocations={"census": 5, "sample": 2},
        residual_variances={"census": 999.0, "sample": 0.25},
        denominator=10.0,
    )
    assert variance == pytest.approx((0.8 * (100 / 2) * 0.25) / 100)

