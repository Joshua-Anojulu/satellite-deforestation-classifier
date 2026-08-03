"""§4 preflight and origin publication, driven from committed checkpoints.

§4.6 puts preflight at step 4, after parsing, precisely because it "reads
Parquet, never a PBF" -- and that is only true if it runs from committed
region checkpoints.  These tests drive it the way production does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forecast.content_store import ContentStore
from forecast.manifests import validate_dag
from forecast.osm_dedupe import DirtyPreflight, deduplicate
from forecast.osm_preflight import (
    CheckpointsMissing,
    load_region_ways,
    load_site_records,
    run_preflight,
)
from forecast.osm_pipeline import run
from forecast.osm_provenance import ABSENT, ProvenanceSurvey, RegionProvenance
from forecast.tests.test_osm_pipeline import (
    MANIFEST,
    REPO_ROOT,
    inside,
    write_pbf,
)
from forecast.osm_pipeline import load_sites


@pytest.fixture(scope="module")
def site():
    return load_sites(MANIFEST)[0]


@pytest.fixture
def local_root(tmp_path):
    assert "onedrive" not in str(tmp_path).lower()
    return tmp_path


def provenance_for(origins=("2020", "2022"), region="testland") -> ProvenanceSurvey:
    """2020 carries ABSENT, matching the real corpus (owner ruling)."""

    stamps = {"2020": ABSENT, "2021": "2021-01-01T21:42:03Z", "2022": "2022-01-01T21:21:26Z"}
    return ProvenanceSurvey(
        tuple(
            RegionProvenance(
                name=f"{region}-{o[2:]}0101",
                origin=o,
                region=region,
                header_timestamp=stamps[o],
                replication_base_url="",
                generator="osmium/1.14.0",
            )
            for o in origins
        )
    )


def build_corpus(local_root, site, ways_by_origin):
    """Run the real pass-1/pass-2 path so §4 reads genuine committed parts."""

    extracts = [
        write_pbf(
            local_root / "in" / f"testland-{origin[2:]}0101.osm.pbf",
            ways,
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
    return (
        ContentStore(local_root / "store" / "objects"),
        ContentStore(local_root / "store" / "checkpoints", verify_ancestry=False),
    )


def test_preflight_runs_from_committed_parts_and_publishes(local_root, site):
    lon, lat = inside(site)
    store, checkpoints = build_corpus(
        local_root,
        site,
        {
            "2020": [(300, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(300, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        },
    )

    outcome = run_preflight(store, checkpoints, provenance_for())

    assert outcome.report.is_clean
    assert outcome.region_records == 2
    assert outcome.published
    assert set(outcome.origin_manifests) == {2020, 2022}
    assert outcome.origin_ways == {2020: 1, 2022: 1}

    for manifest in outcome.origin_manifests.values():
        assert validate_dag(store, manifest).manifests == 1


def test_the_2020_origin_carries_ABSENT_into_its_records(local_root, site):
    """The owner ruling, threaded all the way to §4.3's conflict input.

    Substituting a filename date here would make two undatable 2020 regions look
    like they corroborated each other.
    """

    lon, lat = inside(site)
    store, checkpoints = build_corpus(
        local_root,
        site,
        {
            "2020": [(301, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(301, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        },
    )

    records = load_region_ways(store, checkpoints, provenance_for())
    by_origin = {r.origin: r.region_header_timestamp for r in records}

    assert by_origin[2020] == ABSENT
    assert by_origin[2022] == "2022-01-01T21:21:26Z"


def test_the_published_origin_dataset_records_its_header_timestamp(local_root, site):
    lon, lat = inside(site)
    store, checkpoints = build_corpus(
        local_root,
        site,
        {"2020": [(302, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]},
    )

    outcome = run_preflight(store, checkpoints, provenance_for(origins=("2020",)))
    manifest = json.loads(store.read_validated(outcome.origin_manifests[2020]))

    assert manifest["bindings"]["header_timestamp"] == ABSENT, (
        "an undatable origin must say so in its own published manifest"
    )


def test_site_records_include_pass_two_closure_rows(local_root, site):
    """§4.1's membership input must see what pass 1 could not.

    A closure-only record carries different flags, and dropping it here would
    make the membership table describe a road supply the dataset does not have.
    """

    lon, lat = inside(site)
    far_lon = float(site["east"]) + 0.10
    store, checkpoints = build_corpus(
        local_root,
        site,
        {
            "2020": [(303, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            "2022": [(303, [(far_lon, lat), (far_lon + 0.001, lat)], {"highway": "residential"})],
        },
    )

    records = load_site_records(store, checkpoints)
    closure_only = [r for r in records if r.closure_only]

    assert len(closure_only) == 1, "pass 2 recovered the way that left the window"
    assert closure_only[0].key.origin == 2022
    assert closure_only[0].intersects_window is False
    assert closure_only[0].in_road_supply is False


def test_a_dirty_preflight_blocks_publication(local_root, site):
    """§4.6's actual gate, not a statement about one.

    Two regions of one origin disagreeing on a way's geometry must stop the
    origin dataset being published at all.
    """

    from forecast.osm_dedupe import RegionWay
    from forecast.osm_stream import RetainedWay

    lon, lat = inside(site)
    store, checkpoints = build_corpus(
        local_root,
        site,
        {"2020": [(304, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]},
    )

    def way(coords):
        return RetainedWay(
            osm_id=304, version=1, timestamp="2020-01-01T00:00:00Z",
            tags={"highway": "residential"}, node_refs=(1, 2),
            coordinates=coords, is_closed=False,
        )

    conflicting = (
        RegionWay(2020, "norte", ABSENT, way(((0.0, 0.0), (0.001, 0.0)))),
        RegionWay(2020, "nordeste", ABSENT, way(((9.9, 9.9), (9.901, 9.9)))),
    )

    from forecast.osm_dedupe import preflight as run_report

    report = run_report(conflicting)
    assert not report.is_clean
    assert report.geometry_conflicts

    with pytest.raises(DirtyPreflight):
        deduplicate(conflicting, report)


def test_preflight_refuses_to_run_before_pass_one_has_committed(local_root):
    store = ContentStore(local_root / "objects")
    empty = ContentStore(local_root / "checkpoints", verify_ancestry=False)

    with pytest.raises(CheckpointsMissing):
        load_region_ways(store, empty, provenance_for())


def test_origin_publication_is_byte_deterministic(local_root, site):
    """Two runs must produce one object, or the store fills with near-duplicates."""

    lon, lat = inside(site)
    store, checkpoints = build_corpus(
        local_root,
        site,
        {"2020": [(305, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})]},
    )
    prov = provenance_for(origins=("2020",))

    first = run_preflight(store, checkpoints, prov)
    second = run_preflight(store, checkpoints, prov)

    assert first.origin_manifests == second.origin_manifests
