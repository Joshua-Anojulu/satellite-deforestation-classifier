from __future__ import annotations

import inspect

import numpy as np
import pytest

import forecast.precheck_evaluability as precheck
from forecast.gfc_censor import PRE_LIFT_MASKS
from forecast.precheck_evaluability import SiteResult, build_report, score_site_masks
from forecast.specification_w import FRAME_GROUP_ORDER, K


def _masks() -> dict[str, np.ndarray]:
    empty = np.zeros((8, 8), dtype=bool)
    eligible = np.ones((8, 8), dtype=bool)
    positive_2021 = empty.copy()
    positive_2022 = empty.copy()
    # Two distinct two-pixel 8-connected components in each permitted outcome.
    positive_2021[0, 0:2] = True
    positive_2021[5, 5:7] = True
    positive_2022[1:3, 4] = True
    positive_2022[6, 0:2] = True
    return {
        "eligible_2020": eligible.copy(),
        "eligible_2021": eligible.copy(),
        "eligible_2022": eligible.copy(),
        "positive_2021": positive_2021,
        "positive_2022": positive_2022,
    }


def test_score_site_consumes_only_exact_aligned_boolean_handoff():
    site = {
        "candidate_id": "new-site",
        "group": "sea_peat",
        "draw_rank": 10,
        "retained_position": 9,
        "amendment_role": "addition",
    }
    result = score_site_masks(site, _masks())
    assert result.components == {2020: 2, 2021: 2}
    assert result.positives_px == {2020: 4, 2021: 4}
    assert result.eligible_px_test_origin == 64

    wrong = _masks()
    wrong["raw_lossyear"] = np.zeros((8, 8), dtype=bool)
    with pytest.raises(ValueError, match="exact pre-lift mask schema"):
        score_site_masks(site, wrong)
    assert set(_masks()) == set(PRE_LIFT_MASKS)


def _all_evaluable_results() -> list[SiteResult]:
    results = []
    for group in FRAME_GROUP_ORDER:
        for position in range(1, K + 1):
            draw_rank = position
            if group == "sea_peat" and position >= 8:
                draw_rank += 1
            results.append(SiteResult(
                site_id=f"{group}-{position}",
                group=group,
                draw_rank=draw_rank,
                retained_position=position,
                amendment_role="incumbent" if position <= 3 else "addition",
                eligible_px={2020: 100, 2021: 100},
                positives_px={2020: 20, 2021: 20},
                components={2020: 5, 2021: 6},
                eligible_px_test_origin=100,
            ))
    return results


def test_report_scores_retained_positions_four_through_nine_non_binding():
    report = build_report(_all_evaluable_results())
    assert report["precheck_is_strictly_non_binding"] is True
    assert report["only_permitted_failure_action"].startswith("stop and re-plan")
    assert report["prohibited_action"].startswith("resize K")
    additions = [
        site for site in report["site_results"] if site["amendment_role"] == "addition"
    ]
    assert len(additions) == 24
    assert {site["retained_position"] for site in additions} == set(range(4, 10))
    sea = [site for site in additions if site["group"] == "sea_peat"]
    assert [site["draw_rank"] for site in sea] == [4, 5, 6, 7, 9, 10]


def test_zero_quiet_stratum_bound_and_assumed_rate_sensitivity_are_separate():
    report = build_report(_all_evaluable_results())
    for group in FRAME_GROUP_ORDER:
        diagnostic = report["worst_of_two_stability_diagnostic"][group]
        assert diagnostic["quiet_worst_of_2021_2022"] == 0
        assert diagnostic["one_sided_95pct_upper_bound_worst_of_two"] == pytest.approx(
            1 - 0.05 ** (1 / 6)
        )
    assumed_quarter = next(
        row for row in report["assumed_single_year_sensitivity"]
        if row["assumed_iid_single_test_year_quiet_rate"] == 0.25
    )
    assert assumed_quarter["probability_all_strata_have_at_least_one_site_slack"] == pytest.approx(
        0.961, abs=0.001
    )
    assert assumed_quarter["not_estimated_from_historical_diagnostic"] is True


def test_component_totals_are_labeled_as_permitted_origin_projections():
    report = build_report(_all_evaluable_results())
    for outcome in ("2021", "2022"):
        for group in FRAME_GROUP_ORDER:
            projection = report["origin_specific_projection"][outcome][group]
            assert projection["projected_mapped_components"] >= 30
            assert projection["projection_only_not_test_origin_fact"] is True
    assert "does not establish the full regional gate" in report["scope"]


def test_precheck_source_has_no_raw_raster_or_network_reader():
    source = inspect.getsource(precheck)
    assert "rasterio" not in source
    assert "/vsicurl/" not in source
    assert "requests." not in source

