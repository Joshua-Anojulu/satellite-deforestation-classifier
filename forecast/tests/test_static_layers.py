"""The static schema must be frozen across origins and exclude on stated rules."""

from __future__ import annotations

import json
from datetime import date

import pytest

from forecast.static_layers import (
    GLOBAL,
    ORIGINS,
    REGION_LIMITED,
    REGISTRY,
    StaticLayer,
    build_manifest,
    coverage_features,
    evaluate_layer,
    issue_date,
    primary_schema,
    write_manifest_once,
)


def _layer(**kw) -> StaticLayer:
    base = {"name": "probe", "kind": "static", "coverage": GLOBAL, "vintage": date(2015, 1, 1)}
    base.update(kw)
    return StaticLayer(**base)


# --- the frozen issue-date rule --------------------------------------------

def test_issue_date_is_year_end():
    assert issue_date(2020) == date(2020, 12, 31)
    assert issue_date(2022) == date(2022, 12, 31)


def test_vintage_on_the_issue_date_is_admissible():
    """The rule is <=, so the boundary date itself passes."""

    assert _layer(vintage=date(2020, 12, 31)).is_issue_date_valid(2020)
    assert not _layer(vintage=date(2021, 1, 1)).is_issue_date_valid(2020)


def test_per_origin_snapshots_are_january_first_of_T():
    """Geofabrik keeps no year-end snapshot.

    1 January of T+1 is only a day past the issue date but is still after it,
    so the compliant choice is 1 January of T -- up to twelve months stale.
    """

    roads = _layer(name="roads", kind="per_origin", vintage=None)
    assert roads.snapshot_for(2020) == date(2020, 1, 1)
    assert roads.is_issue_date_valid(2020)
    assert roads.snapshot_for(2022) == date(2022, 1, 1)


# --- exclusion rules --------------------------------------------------------

def test_region_limited_layer_is_excluded():
    """Absence must not conflate 'none here' with 'not surveyed here'."""

    decision = evaluate_layer(_layer(name="peat", coverage=REGION_LIMITED))
    assert not decision.included
    assert "region-limited" in decision.reason


def test_layer_valid_at_only_some_origins_is_excluded():
    """The exact GLO-30 situation: fine for 2021/2022, invalid for 2020.

    Admitting it would make the layer present in training and absent - or
    differently defined - elsewhere, encoding time through missingness.
    """

    glo30 = _layer(name="terrain_glo30", vintage=date(2021, 1, 1))
    decision = evaluate_layer(glo30)
    assert not decision.included
    assert decision.valid_origins == (2021, 2022)
    assert "2020" in decision.reason


def test_layer_with_no_retrievable_snapshot_is_excluded():
    protected = next(l for l in REGISTRY if l.name == "protected_areas")
    decision = evaluate_layer(protected)
    assert not decision.included
    assert "no retrievable" in decision.reason


def test_globally_valid_layer_is_included():
    decision = evaluate_layer(_layer(vintage=date(2010, 1, 1)))
    assert decision.included
    assert decision.valid_origins == ORIGINS


# --- the frozen intersection ------------------------------------------------

def test_primary_schema_is_the_expected_intersection():
    included, _ = primary_schema()
    assert set(included) == {"roads", "terrain", "rivers", "ecoregion", "climate"}
    assert "protected_areas" not in included, "WDPA has no <=issue snapshot"
    assert "peat" not in included, "PEATMAP is Asia-only"


def test_schema_does_not_vary_by_origin():
    """The whole point of the intersection rule.

    Whatever subset of origins is considered, a layer is either in for all of
    them or out - so missingness can never signal which year is in view.
    """

    full, _ = primary_schema(ORIGINS)
    for origin in ORIGINS:
        single, _ = primary_schema([origin])
        assert set(full) <= set(single), (
            "a layer admitted for all origins must be admitted for each"
        )


def test_dropping_the_training_origin_would_admit_more():
    """Non-vacuity control for the intersection rule.

    GLO-30-style layers are excluded ONLY because of the 2020 training origin;
    if the intersection silently skipped it, more layers would slip in.
    """

    registry = (*REGISTRY, _layer(name="terrain_glo30", vintage=date(2021, 1, 1)))
    with_2020, _ = primary_schema(ORIGINS, registry)
    without_2020, _ = primary_schema([2021, 2022], registry)
    assert "terrain_glo30" not in with_2020
    assert "terrain_glo30" in without_2020


def test_terrain_is_srtm_not_copernicus():
    """Copernicus is inadmissible at ANY resolution.

    Both GLO-30 and GLO-90 on AWS are the 2021 release, so the release - not
    the resolution - is what post-dates the 2020 issue date. Switching
    resolutions does not fix it; switching products does.
    """

    terrain = next(l for l in REGISTRY if l.name == "terrain")
    assert terrain.vintage == date(2008, 1, 1)
    assert terrain.is_issue_date_valid(2020), "must clear the training origin"
    assert "SRTM" in terrain.source
    assert "Copernicus" not in terrain.source


def test_a_2021_release_terrain_would_be_excluded_at_any_resolution():
    """Guards the reasoning above, so re-adding Copernicus cannot pass quietly."""

    for name in ("terrain_glo30", "terrain_glo90"):
        decision = evaluate_layer(_layer(name=name, vintage=date(2021, 1, 1)))
        assert not decision.included
        assert decision.valid_origins == (2021, 2022)


def test_empty_schema_is_refused():
    with pytest.raises(ValueError, match="schema is empty"):
        primary_schema(ORIGINS, [_layer(coverage=REGION_LIMITED)])


# --- coverage and manifest --------------------------------------------------

def test_coverage_features_are_explicit_not_nan():
    included, _ = primary_schema()
    flags = coverage_features(included)
    assert len(flags) == len(included)
    assert all(flag.endswith("_covered") for flag in flags)


def test_manifest_records_every_exclusion_reason():
    manifest = build_manifest()
    layers = manifest["layers"]
    assert set(layers) == {l.name for l in REGISTRY}
    for name in ("protected_areas", "peat"):
        assert layers[name]["included_in_primary"] is False
        assert layers[name]["reason"], f"{name} must record WHY it is excluded"
    assert manifest["primary_schema"] == list(
        n for n in manifest["primary_schema"]
    )
    assert manifest["issue_dates"]["2020"] == "2020-12-31"


def test_manifest_records_per_origin_snapshots():
    manifest = build_manifest()
    roads = manifest["layers"]["roads"]["snapshots"]
    assert roads["2020"] == "2020-01-01"
    assert roads["2022"] == "2022-01-01"


def test_manifest_is_write_once(tmp_path):
    manifest = build_manifest()
    path = write_manifest_once(tmp_path / "schema.json", manifest)
    assert json.loads(path.read_text())["schema_version"] == 1
    with pytest.raises(FileExistsError):
        write_manifest_once(path, manifest)
