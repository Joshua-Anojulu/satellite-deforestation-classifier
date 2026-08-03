"""§6 identity edges and presence table, over artifacts §4 published.

The case that matters most here is the one a window-only pipeline deletes: a way
that left its site window between origins.  §6.1 promises it is still linked, and
pass 2 retained it specifically so the edge could exist.
"""

from __future__ import annotations

import json

import pytest

from forecast.content_store import ContentStore
from forecast.manifests import validate_dag
from forecast.osm_edges import (
    LineageInputMissing,
    build_endpoints,
    load_geometry,
    run_lineage,
)
from forecast.osm_lineage import GLOBAL_COUNTERPART_STATUS
from forecast.osm_preflight import run_preflight
from forecast.osm_pipeline import load_sites, run
from forecast.osm_windows import build_site_windows
from forecast.tests.test_osm_pipeline import MANIFEST, REPO_ROOT, inside, write_pbf
from forecast.tests.test_osm_preflight import provenance_for

ORIGINS = (2020, 2022)


@pytest.fixture(scope="module")
def site():
    return load_sites(MANIFEST)[0]


@pytest.fixture
def local_root(tmp_path):
    assert "onedrive" not in str(tmp_path).lower()
    return tmp_path


def lineage_for(local_root, site, ways_by_origin):
    """Run the whole path -- passes 1 and 2, §4, then §6 -- as production does."""

    extracts = [
        write_pbf(
            local_root / "in" / f"testland-{origin[2:]}0101.osm.pbf", ways,
            origin_year=origin,
        )
        for origin, ways in sorted(ways_by_origin.items())
    ]
    run(
        extracts,
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
        two_pass=True,
    )
    store = ContentStore(local_root / "store" / "objects")
    checkpoints = ContentStore(local_root / "store" / "checkpoints", verify_ancestry=False)
    preflight = run_preflight(store, checkpoints, provenance_for())
    assert preflight.report.is_clean

    windows = {w.site_id: w for w in build_site_windows([site])}
    outcome = run_lineage(
        store, checkpoints, preflight.origin_manifests, windows, origins=ORIGINS
    )
    return store, outcome


def edge_rows(store, outcome):
    return json.loads(store.read_validated(outcome.edges_digest))["rows"]


def presence_rows(store, outcome):
    return json.loads(store.read_validated(outcome.presence_digest))["rows"]


def test_a_way_present_in_both_origins_gets_one_edge(local_root, site):
    lon, lat = inside(site)
    way = [(400, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]
    store, outcome = lineage_for(local_root, site, {"2020": way, "2022": way})

    assert outcome.edges == 1
    row = edge_rows(store, outcome)[0]

    assert (row["origin_a"], row["origin_b"]) == (2020, 2022)
    assert row["osm_id"] == 400
    assert row["a_intersects_window"] and row["b_intersects_window"]
    assert row["a_closure_only"] is False and row["b_closure_only"] is False
    assert row["min_distance_m"] == pytest.approx(0.0, abs=1e-6)
    assert row["degenerate_flag"] is False


def test_a_way_that_left_the_window_is_still_linked(local_root, site):
    """§6.1's promise, and the reason pass 2 exists.

    A radius -- or a window -- would have deleted exactly this edge.  The far
    endpoint must be marked closure-only so a consumer can tell it apart from a
    road the site actually contains.
    """

    lon, lat = inside(site)
    far_lon = float(site["east"]) + 0.10
    store, outcome = lineage_for(
        local_root,
        site,
        {
            "2020": [(401, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(401, [(far_lon, lat), (far_lon + 0.001, lat)], {"highway": "residential"})],
        },
    )

    assert outcome.edges == 1, "the counterpart moved but the edge must survive"
    assert outcome.closure_only_endpoints == 1
    row = edge_rows(store, outcome)[0]

    assert row["a_intersects_window"] is True
    assert row["a_closure_only"] is False
    assert row["b_intersects_window"] is False
    assert row["b_closure_only"] is True
    assert row["min_distance_m"] > 8_000, (
        "the endpoints really are kilometres apart, and the edge exists anyway"
    )


def test_a_tag_changed_counterpart_is_linked_and_flagged(local_root, site):
    """In the window, no longer a road: all three facts must survive."""

    lon, lat = inside(site)
    store, outcome = lineage_for(
        local_root,
        site,
        {
            "2020": [(402, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(402, [(lon, lat), (lon + 0.001, lat)], {"waterway": "ditch"})],
        },
    )

    assert outcome.edges == 1
    row = edge_rows(store, outcome)[0]

    assert row["b_intersects_window"] is True
    assert row["b_selected_by_predicate"] is False
    assert row["b_closure_only"] is True, (
        "a record in the window that is no longer a road is not a road the site contains"
    )


def test_the_presence_table_emits_absence_over_every_origin(local_root, site):
    """§6.3, round-9 #5: absence needs somewhere to live.

    Way 403 exists only in 2020.  Without a row saying so for 2022, an origin
    where it is absent is indistinguishable from one never acquired.
    """

    lon, lat = inside(site)
    store, outcome = lineage_for(
        local_root,
        site,
        {
            "2020": [(403, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(404, [(lon, lat + 0.002), (lon + 0.001, lat + 0.002)], {"highway": "service"})],
        },
    )

    rows = presence_rows(store, outcome)
    by_key = {(r["osm_id"], r["origin"]): r for r in rows}

    assert len(rows) == 4, "two ways over two origins, present or not"
    assert by_key[(403, 2020)]["presence_in_acquired_corpus"] is True
    assert by_key[(403, 2022)]["presence_in_acquired_corpus"] is False
    assert by_key[(404, 2022)]["presence_in_acquired_corpus"] is True
    assert by_key[(404, 2020)]["presence_in_acquired_corpus"] is False

    assert outcome.edges == 0, "edges are built only between present endpoints"


def test_global_counterpart_status_is_always_unknown(local_root, site):
    """Absence from the acquired corpus is not absence from OSM (§6.1)."""

    lon, lat = inside(site)
    way = [(405, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]
    store, outcome = lineage_for(local_root, site, {"2020": way, "2022": way})

    statuses = {r["global_counterpart_status"] for r in presence_rows(store, outcome)}
    assert statuses == {GLOBAL_COUNTERPART_STATUS} == {"UNKNOWN"}


def test_the_published_artifacts_validate_from_the_store(local_root, site):
    lon, lat = inside(site)
    way = [(406, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]
    store, outcome = lineage_for(local_root, site, {"2020": way, "2022": way})

    assert validate_dag(store, outcome.edges_manifest).manifests == 1
    assert validate_dag(store, outcome.presence_manifest).manifests == 1


def test_presence_requires_the_corpus_origins(local_root, site):
    lon, lat = inside(site)
    way = [(407, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]
    extracts = [
        write_pbf(local_root / "in" / "testland-200101.osm.pbf", way, origin_year="2020")
    ]
    run(
        extracts, sites=[site], store_root=local_root / "store", repo_root=REPO_ROOT,
        command=("x",), two_pass=True,
    )
    store = ContentStore(local_root / "store" / "objects")
    checkpoints = ContentStore(local_root / "store" / "checkpoints", verify_ancestry=False)
    preflight = run_preflight(store, checkpoints, provenance_for(origins=("2020",)))
    windows = {w.site_id: w for w in build_site_windows([site])}

    with pytest.raises(ValueError, match="absence cannot be inferred"):
        run_lineage(store, checkpoints, preflight.origin_manifests, windows, origins=())


def test_a_membership_row_without_geometry_is_reported_not_dropped():
    """"Present but unlocatable" and "absent" are different facts."""

    from forecast.osm_dedupe import MembershipKey, MembershipRow

    rows = (
        MembershipRow(MembershipKey("s", 2020, "way", 1), True, True),
        MembershipRow(MembershipKey("s", 2022, "way", 1), True, True),
    )
    endpoints, orphaned = build_endpoints(
        rows, {(2020, 1): ((0.0, 0.0), (0.001, 0.0))}
    )

    assert len(endpoints) == 1
    assert len(orphaned) == 1
    assert orphaned[0].key[1] == 2022


def test_lineage_refuses_before_section_four_has_published(local_root):
    store = ContentStore(local_root / "objects")
    checkpoints = ContentStore(local_root / "checkpoints", verify_ancestry=False)

    with pytest.raises(LineageInputMissing):
        load_geometry(store, checkpoints, {})
