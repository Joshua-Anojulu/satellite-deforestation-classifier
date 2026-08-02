"""The production path, end to end on a real PBF this test writes itself.

§3's measurements came from a harness that stopped after the parser, so the
gate could never be satisfied by them (round-4 #3).  These tests exercise the
path that *does* build geometry, intersect masks, dispatch, serialise, hash and
publish -- on a genuine `.osm.pbf` produced by `osmium`, not a stand-in, because
the parser is half of what is being measured.
"""

from __future__ import annotations

import json
from pathlib import Path

import osmium
import pytest

from forecast.entry_gate import Outcome
from forecast.generations import DatasetIdentity, GenerationStore
from forecast.manifests import validate_dag
from forecast.osm_pipeline import (
    SCHEMA_DIGEST,
    ProductionPathError,
    build_evidence,
    dependency_versions,
    load_sites,
    origin_and_region,
    run,
    run_pass_one_file,
    run_pass_two_file,
)
from forecast.osm_windows import build_site_windows
from forecast.content_store import ContentStore

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "forecast" / "artifacts" / "specification_w_manifest.json"


@pytest.fixture(scope="module")
def sites():
    return load_sites(MANIFEST)


@pytest.fixture(scope="module")
def site(sites):
    """One real Specification W site, so the windows under test are the real ones."""

    return sites[0]


def write_pbf(path: Path, ways, *, origin_year: str = "2022") -> Path:
    """Write a real PBF.  `ways` is a list of (osm_id, [(lon, lat), ...], tags)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = osmium.SimpleWriter(str(path))
    node_id = 1
    pending = []
    for osm_id, coordinates, tags in ways:
        refs = []
        for lon, lat in coordinates:
            writer.add_node(
                osmium.osm.mutable.Node(id=node_id, location=(lon, lat), version=1)
            )
            refs.append(node_id)
            node_id += 1
        pending.append((osm_id, refs, tags))
    for osm_id, refs, tags in pending:
        writer.add_way(
            osmium.osm.mutable.Way(
                id=osm_id,
                nodes=refs,
                tags=tags,
                version=1,
                timestamp=f"{origin_year}-01-01T00:00:00Z",
            )
        )
    writer.close()
    return path


def inside(site, dx: float = 0.0, dy: float = 0.0) -> tuple[float, float]:
    lon = (float(site["west"]) + float(site["east"])) / 2.0 + dx
    lat = (float(site["south"]) + float(site["north"])) / 2.0 + dy
    return lon, lat


@pytest.fixture
def local_root(tmp_path):
    assert "onedrive" not in str(tmp_path).lower()
    return tmp_path


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------


def test_origin_and_region_are_read_from_the_extract_name():
    assert origin_and_region(Path("norte-220101.osm.pbf")) == ("2022", "norte")
    assert origin_and_region(Path("haiti-and-domrep-200101.osm.pbf")) == (
        "2020",
        "haiti-and-domrep",
    )


def test_an_unparseable_extract_name_is_refused():
    """Guessing an origin would mislabel which archive a way came from."""

    with pytest.raises(ProductionPathError):
        origin_and_region(Path("indonesia.osm.pbf"))


# --------------------------------------------------------------------------
# One file through the real path
# --------------------------------------------------------------------------


def test_a_way_inside_a_window_is_dispatched_serialised_and_published(local_root, site):
    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(10, [(lon, lat), (lon + 0.001, lat + 0.001)], {"highway": "residential"})],
    )
    store = ContentStore(local_root / "objects")
    windows = build_site_windows([site])

    outcome = run_pass_one_file(pbf, windows, store)

    assert outcome.origin == "2022"
    assert outcome.region == "testland"
    assert outcome.counters.retained_ways == 1
    assert outcome.counters.ways_with_complete_geometry == 1
    assert outcome.counters.geometry_availability == 1.0
    assert outcome.counters.invalid_node_locations == 0
    assert outcome.counters.node_cardinality == 2
    assert outcome.counters.max_node_id == 2
    assert outcome.counters.wall_clock_s > 0
    assert outcome.counters.peak_commit_bytes > 0

    assert len(outcome.parts) == 1
    assert outcome.parts[0].ways == 1
    assert outcome.parts[0].site_ids == (site["candidate_id"],)

    # The region manifest names a DAG that fully validates from the store.
    report = validate_dag(store, outcome.region_manifest)
    assert report.manifests == 2
    assert report.leaves == 1

    payload = json.loads(store.read_validated(outcome.parts[0].digest))
    assert payload["origin"] == "2022"
    assert payload["rows"][0]["osm_id"] == 10
    assert payload["rows"][0]["site_id"] == site["candidate_id"]


def test_a_way_outside_every_window_is_counted_but_dispatched_nowhere(local_root, site):
    """Retained is not the same as in-window, and the counters must not conflate them."""

    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(11, [(0.0, 0.0), (0.001, 0.001)], {"highway": "track"})],
    )
    store = ContentStore(local_root / "objects")

    outcome = run_pass_one_file(pbf, build_site_windows([site]), store)

    assert outcome.counters.retained_ways == 1
    assert outcome.counters.ways_with_complete_geometry == 1
    assert outcome.parts == (), "a way touching no window must produce no part rows"


def test_a_non_highway_way_is_never_retained(local_root, site):
    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(12, [(lon, lat), (lon + 0.001, lat)], {"waterway": "river"})],
    )
    store = ContentStore(local_root / "objects")

    outcome = run_pass_one_file(pbf, build_site_windows([site]), store)
    assert outcome.counters.retained_ways == 0


def test_a_single_node_way_is_counted_as_unbuildable_not_as_geometry(local_root, site):
    """A resolved location and a buildable line are different things.

    Counting a one-node way as having complete geometry would inflate
    `geometry_availability` -- the row the gate scores at exactly 1.0.
    """

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(13, [(lon, lat)], {"highway": "path"})],
    )
    store = ContentStore(local_root / "objects")

    outcome = run_pass_one_file(pbf, build_site_windows([site]), store)

    assert outcome.counters.retained_ways == 1
    assert outcome.counters.ways_with_complete_geometry == 0
    assert outcome.counters.geometry_availability == 0.0
    assert outcome.parts == ()


def test_part_serialisation_is_byte_deterministic(local_root, site):
    """The part's digest is its identity, so two identical runs must agree.

    If serialisation were nondeterministic the store would fill with duplicate
    objects that never dedupe, and §8.3's rehash-before-reuse would be pointless.
    """

    lon, lat = inside(site)
    ways = [
        (20, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"}),
        (21, [(lon, lat + 0.002), (lon + 0.001, lat + 0.002)], {"highway": "service"}),
    ]
    first = run_pass_one_file(
        write_pbf(local_root / "a" / "testland-220101.osm.pbf", ways),
        build_site_windows([site]),
        ContentStore(local_root / "store-a"),
    )
    second = run_pass_one_file(
        write_pbf(local_root / "b" / "testland-220101.osm.pbf", ways),
        build_site_windows([site]),
        ContentStore(local_root / "store-b"),
    )

    assert [p.digest for p in first.parts] == [p.digest for p in second.parts]
    assert first.region_manifest == second.region_manifest


def test_parts_are_split_at_the_configured_size(local_root, site):
    lon, lat = inside(site)
    ways = [
        (30 + i, [(lon + i * 1e-5, lat), (lon + i * 1e-5, lat + 1e-4)], {"highway": "service"})
        for i in range(5)
    ]
    pbf = write_pbf(local_root / "in" / "testland-220101.osm.pbf", ways)
    store = ContentStore(local_root / "objects")

    outcome = run_pass_one_file(pbf, build_site_windows([site]), store, ways_per_part=2)

    assert len(outcome.parts) == 3, "5 rows at 2 per part is 3 parts (§5.5)"
    assert sum(p.ways for p in outcome.parts) == 5
    assert validate_dag(store, outcome.region_manifest).manifests == 4


# --------------------------------------------------------------------------
# The gate and its evidence
# --------------------------------------------------------------------------


def test_a_full_run_publishes_a_generation_and_produces_evidence(local_root, site):
    lon, lat = inside(site)
    extracts = [
        write_pbf(
            local_root / "in" / f"testland-{yy}0101.osm.pbf",
            [(40, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            origin_year=f"20{yy}",
        )
        for yy in ("20", "21", "22")
    ]

    result = run(
        extracts,
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline", "--test"),
    )

    assert result["generation"] == 1
    evidence = result["evidence"]
    assert evidence.missing() == (), "the artifact must be complete or it authorises nothing"
    assert evidence.covers_full_production_path
    assert len(evidence.input_digests) == 3
    assert evidence.dependency_versions["osmium"] != "absent"
    assert "stage" in evidence.output_digests

    generations = GenerationStore(local_root / "store")
    identity = DatasetIdentity(
        dataset="osm-normalisation-pass-1",
        schema_digest=SCHEMA_DIGEST,
        cache_key="pass-1",
    )
    selection = generations.select(identity)
    assert selection.number == 1
    assert selection.root_digest == result["stage"]
    # 1 stage + 3 origin datasets + 3 regions + 3 shards = 10 manifests, over
    # 3 part files, which are leaves rather than manifests.
    dag = validate_dag(generations.store, selection.root_digest)
    assert (dag.manifests, dag.leaves) == (10, 3)


def test_pass_one_alone_does_not_authorise_a_corpus_run(local_root, site):
    """The point of the gate: a complete pass-1 run is still not authorisation.

    Two rows stay `NOT_ASSESSED` -- the corpus projection and pass-2 commit with
    `S` resident -- and `NOT_ASSESSED` is not `PASS` (round-4 #3).  A gate that
    authorised here would be authorising a 12-hour corpus run on evidence that
    pass 2 has never been measured at all.
    """

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(50, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
    )
    result = run(
        [pbf],
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
    )
    report = result["report"]

    assert report.failed == (), "a clean pass-1 run must not FAIL any row"
    assert report.evidence is not None and report.evidence.missing() == ()
    assert not report.authorises_corpus_run

    unmeasured = {c.name for c in report.not_assessed}
    assert unmeasured == {
        "projected corpus wall-clock, both passes",
        "peak commit charge with S resident, pass 2",
    }
    assert "NOT AUTHORISED" in report.describe()


def test_the_gate_authorises_once_the_two_unmeasured_rows_are_supplied(local_root, site):
    """And it does authorise when the evidence is genuinely complete.

    The negative test above is only meaningful if the positive one passes;
    otherwise `authorises_corpus_run` could be hard-wired to False.
    """

    from forecast.entry_gate import evaluate_gate

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(51, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
    )
    result = run(
        [pbf],
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
    )

    authorised = evaluate_gate(
        [o.counters for o in result["outcomes"]],
        evidence=result["evidence"],
        projected_corpus_wall_clock_s=8 * 3600,
        pass_two_peak_commit_bytes=9 * 1024**3,
    )
    assert authorised.not_assessed == ()
    assert authorised.failed == ()
    assert authorised.authorises_corpus_run


def test_an_over_ceiling_pass_two_measurement_fails_the_gate(local_root, site):
    from forecast.entry_gate import evaluate_gate

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [(52, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
    )
    result = run(
        [pbf],
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
    )

    refused = evaluate_gate(
        [o.counters for o in result["outcomes"]],
        evidence=result["evidence"],
        projected_corpus_wall_clock_s=8 * 3600,
        pass_two_peak_commit_bytes=20 * 1024**3,
    )
    assert not refused.authorises_corpus_run
    assert [c.name for c in refused.failed] == [
        "peak commit charge with S resident, pass 2"
    ]


def test_the_parser_source_digest_changes_when_the_parser_changes(local_root):
    """Evidence must not survive an edit to the code that produced it (§8.2)."""

    from forecast.osm_pipeline import parser_source_digest, PARSER_SOURCE_MODULES

    baseline = parser_source_digest(REPO_ROOT)

    fake_root = local_root / "fake-repo"
    for relative in PARSER_SOURCE_MODULES:
        target = fake_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    assert parser_source_digest(fake_root) == baseline

    edited = fake_root / PARSER_SOURCE_MODULES[0]
    edited.write_bytes(edited.read_bytes() + b"\n# an edit that changes behaviour\n")
    assert parser_source_digest(fake_root) != baseline


# --------------------------------------------------------------------------
# Pass 2: the closure (§2.2)
# --------------------------------------------------------------------------


def test_pass_two_recovers_a_counterpart_that_left_the_window(local_root, site):
    """The case the whole second pass exists for (§6.1).

    Way 100 is inside the window in 2020 and 8 km away in 2022.  Pass 1 sees it
    only in 2020; a window-only pipeline would leave 2022 with no record and the
    identity edge would simply be absent, with nothing raised anywhere.
    """

    from forecast.osm_closure import ClosureTable, RecordKey

    lon, lat = inside(site)
    near = write_pbf(
        local_root / "in" / "testland-200101.osm.pbf",
        [(100, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        origin_year="2020",
    )
    # Clear of the box AND of §2.1's 5 km extraction guard -- measuring from the
    # centre would not have escaped either, the box being 0.25 degrees wide.
    far_lon = float(site["east"]) + 0.10
    far = write_pbf(
        local_root / "far" / "testland-220101.osm.pbf",
        [(100, [(far_lon, lat), (far_lon + 0.001, lat)], {"highway": "residential"})],
        origin_year="2022",
    )

    store = ContentStore(local_root / "objects")
    windows = build_site_windows([site])
    from shapely.geometry import LineString

    assert not windows[0].intersects_window(
        LineString([(far_lon, lat), (far_lon + 0.001, lat)])
    ), "the fixture must actually place the 2022 way outside the window"
    closure = ClosureTable()
    emitted: set[RecordKey] = set()

    first = run_pass_one_file(near, windows, store, closure=closure, emitted=emitted)
    second = run_pass_one_file(far, windows, store, closure=closure, emitted=emitted)

    assert first.parts != (), "the 2020 way is inside the window"
    assert second.parts == (), "the 2022 way has moved outside it"
    assert len(closure) == 1

    recovered = run_pass_two_file(far, windows, closure, emitted, store)

    assert recovered.ways_claimed == 1
    assert recovered.records == 1, "pass 2 must recover the other-origin counterpart"
    assert recovered.closure_only_records == 1
    payload = json.loads(store.read_validated(recovered.parts[0].digest))
    row = payload["records"][0]
    assert row["osm_id"] == 100
    assert row["intersects_window"] is False
    assert row["selected_by_predicate"] is True
    assert row["closure_only"] is True
    assert row["in_road_supply"] is False


def test_pass_two_recovers_a_tag_changed_counterpart(local_root, site):
    """Still in the window, no longer tagged a road.

    Pass 1 never sees it because the predicate rejects it, so only pass 2 can
    record that this site's way stopped being a road rather than disappearing.
    """

    from forecast.osm_closure import ClosureTable, RecordKey

    lon, lat = inside(site)
    road = write_pbf(
        local_root / "a" / "testland-200101.osm.pbf",
        [(101, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        origin_year="2020",
    )
    no_longer = write_pbf(
        local_root / "b" / "testland-220101.osm.pbf",
        [(101, [(lon, lat), (lon + 0.001, lat)], {"waterway": "ditch"})],
        origin_year="2022",
    )

    store = ContentStore(local_root / "objects")
    windows = build_site_windows([site])
    closure = ClosureTable()
    emitted: set[RecordKey] = set()

    run_pass_one_file(road, windows, store, closure=closure, emitted=emitted)
    later = run_pass_one_file(no_longer, windows, store, closure=closure, emitted=emitted)
    assert later.counters.retained_ways == 0, "the predicate rejects it in 2022"

    recovered = run_pass_two_file(no_longer, windows, closure, emitted, store)

    assert recovered.records == 1
    row = json.loads(store.read_validated(recovered.parts[0].digest))["records"][0]
    assert row["intersects_window"] is True
    assert row["selected_by_predicate"] is False
    assert row["closure_only"] is True
    assert row["in_road_supply"] is False, (
        "a way inside the window that is no longer a road is not road supply"
    )


def test_pass_two_does_not_duplicate_the_exact_pass_one_record(local_root, site):
    """Suppression is on the record, not the pair (§2.2).

    Suppressing on `(site_id, osm_id)` would make pass 2 inert, because every
    pair in S is there precisely because pass 1 emitted it somewhere.
    """

    from forecast.osm_closure import ClosureTable, RecordKey

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-200101.osm.pbf",
        [(102, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        origin_year="2020",
    )
    store = ContentStore(local_root / "objects")
    windows = build_site_windows([site])
    closure = ClosureTable()
    emitted: set[RecordKey] = set()

    run_pass_one_file(pbf, windows, store, closure=closure, emitted=emitted)
    again = run_pass_two_file(pbf, windows, closure, emitted, store)

    assert again.ways_claimed == 1, "the way is in S and is examined"
    assert again.records == 0, "but its exact pass-1 record is already written"


def test_pass_two_skips_ways_no_site_claims(local_root, site):
    """The dict lookup that makes the pass affordable at corpus scale."""

    from forecast.osm_closure import ClosureTable, RecordKey

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-200101.osm.pbf",
        [
            (103, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"}),
            (104, [(0.0, 0.0), (0.001, 0.0)], {"highway": "track"}),
        ],
        origin_year="2020",
    )
    store = ContentStore(local_root / "objects")
    windows = build_site_windows([site])
    closure = ClosureTable()
    emitted: set[RecordKey] = set()

    run_pass_one_file(pbf, windows, store, closure=closure, emitted=emitted)
    result = run_pass_two_file(pbf, windows, closure, emitted, store)

    assert result.ways_considered == 2, "every way is examined"
    assert result.ways_claimed == 1, "only the claimed one pays for geometry"


def test_the_closure_table_round_trips_through_its_artifact(local_root, site):
    """§2.2: S is published, so pass 2's input is versioned, not process state."""

    from forecast.osm_closure import ClosureTable, RecordKey
    from forecast.osm_pipeline import closure_payload, load_closure

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-200101.osm.pbf",
        [(105, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
        origin_year="2020",
    )
    store = ContentStore(local_root / "objects")
    closure = ClosureTable()
    run_pass_one_file(
        pbf, build_site_windows([site]), store, closure=closure, emitted=set()
    )

    payload = closure_payload(closure)
    assert closure_payload(load_closure(payload)) == payload, "digest-stable round trip"
    assert list(load_closure(payload)) == list(closure)


def test_a_two_pass_run_measures_the_pass_two_gate_row(local_root, site):
    """The row that has been NOT_ASSESSED since §3 was written.

    Pass 1 cannot produce it: commit charge "with S resident" is undefined while
    pass 1 is still building S.
    """

    lon, lat = inside(site)
    extracts = [
        write_pbf(
            local_root / "in" / f"testland-{yy}0101.osm.pbf",
            [(106, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            origin_year=f"20{yy}",
        )
        for yy in ("20", "22")
    ]

    result = run(
        extracts,
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline", "--two-pass"),
        two_pass=True,
    )
    report = result["report"]

    unmeasured = {c.name for c in report.not_assessed}
    assert "peak commit charge with S resident, pass 2" not in unmeasured, (
        "the two-pass run must actually measure the row it exists to measure"
    )
    assert unmeasured == {"projected corpus wall-clock, both passes"}
    assert result["closure_digest"] is not None
    assert result["closure_pairs"] == 1

    # The closure artifact and every pass-2 manifest are reachable from the stage.
    generations = GenerationStore(local_root / "store")
    identity = DatasetIdentity(
        dataset="osm-normalisation-pass-1",
        schema_digest=SCHEMA_DIGEST,
        cache_key="pass-1",
    )
    selection = generations.select(identity)
    reachable = generations.reachable_objects()
    assert result["closure_digest"] in reachable
    for closure_outcome in result["closures"]:
        assert closure_outcome.manifest in reachable


# --------------------------------------------------------------------------
# §4.6 region checkpoints and resume
# --------------------------------------------------------------------------


def _corpus(local_root, site):
    lon, lat = inside(site)
    return [
        write_pbf(
            local_root / "in" / f"testland-{yy}0101.osm.pbf",
            [(200, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"})],
            origin_year=f"20{yy}",
        )
        for yy in ("20", "22")
    ]


def test_a_resumed_run_skips_committed_files_and_matches_the_first(local_root, site):
    """§10.1: the whole input file is the restart boundary.

    A file whose region is already committed is not re-parsed -- and the run
    must reach the same published state either way, or resume is a different
    pipeline wearing the same name.
    """

    extracts = _corpus(local_root, site)
    common = dict(
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
        two_pass=True,
    )

    first = run(extracts, **common)
    assert first["resumed"] == (), "nothing to resume on a fresh store"

    second = run(extracts, **common)
    assert len(second["resumed"]) == len(extracts), "every file must resume"
    assert second["stage"] == first["stage"], (
        "a resumed run must publish the identical stage, not merely a valid one"
    )
    assert second["closure_pairs"] == first["closure_pairs"]
    assert second["closure_digest"] == first["closure_digest"]


def test_resume_rebuilds_the_closure_from_committed_parts(local_root, site):
    """The failure this would otherwise hide.

    If a resumed file's closure contribution were skipped along with its parse,
    `S` would be silently short and pass 2 would stop recovering exactly the
    counterparts it exists for -- with nothing raised anywhere.
    """

    from forecast.osm_closure import ClosureTable, RecordKey
    from forecast.osm_pipeline import restore_closure_from_parts

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-200101.osm.pbf",
        [
            (201, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"}),
            (202, [(lon, lat + 0.002), (lon + 0.001, lat + 0.002)], {"highway": "service"}),
        ],
        origin_year="2020",
    )
    store = ContentStore(local_root / "objects")
    parsed_closure, parsed_emitted = ClosureTable(), set()
    outcome = run_pass_one_file(
        pbf, build_site_windows([site]), store,
        closure=parsed_closure, emitted=parsed_emitted,
    )

    restored_closure, restored_emitted = ClosureTable(), set()
    restore_closure_from_parts(store, outcome, restored_closure, restored_emitted)

    assert len(restored_closure) == 2
    assert list(restored_closure) == list(parsed_closure)
    assert restored_emitted == parsed_emitted


def test_a_checkpoint_from_different_site_windows_is_not_reused(local_root, sites):
    """§8.1: an artifact built for different site windows must not validate.

    Resume keys on a digest of the windows, so a checkpoint written under one
    site set cannot be silently reused under another.
    """

    from forecast.osm_pipeline import checkpoint_name, windows_digest

    one = windows_digest(build_site_windows([sites[0]]))
    two = windows_digest(build_site_windows([sites[0], sites[1]]))

    assert one != two
    assert checkpoint_name(one, "norte", "2020") != checkpoint_name(two, "norte", "2020")
    assert windows_digest(build_site_windows([sites[0]])) == one, "and it is stable"


def test_pass_two_checkpoints_are_keyed_on_the_complete_closure(local_root, site):
    """A checkpoint from a different `S` is not reusable.

    Pass 2's output is exactly the set of counterparts `S` happened to claim, so
    reusing one built under a partial closure would silently under-recover.
    """

    from forecast.osm_pipeline import pass_two_checkpoint_name

    a = pass_two_checkpoint_name("a" * 64, "norte", "2020")
    b = pass_two_checkpoint_name("b" * 64, "norte", "2020")
    assert a != b
    assert a != pass_two_checkpoint_name("a" * 64, "norte", "2021")


def test_a_resumed_two_pass_run_reuses_pass_two_and_still_scores_the_gate(
    local_root, site
):
    """Resume must not cost the pass-2 gate row its measurement."""

    extracts = _corpus(local_root, site)
    common = dict(
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
        two_pass=True,
    )
    first = run(extracts, **common)
    second = run(extracts, **common)

    assert [c.manifest for c in second["closures"]] == [
        c.manifest for c in first["closures"]
    ]
    unmeasured = {c.name for c in second["report"].not_assessed}
    assert "peak commit charge with S resident, pass 2" not in unmeasured
    assert second["stage"] == first["stage"]


def test_no_resume_reparses_everything(local_root, site):
    extracts = _corpus(local_root, site)
    common = dict(
        sites=[site],
        store_root=local_root / "store",
        repo_root=REPO_ROOT,
        command=("python", "-m", "forecast.osm_pipeline"),
    )
    run(extracts, **common)
    again = run(extracts, resume=False, **common)
    assert again["resumed"] == ()


# --------------------------------------------------------------------------
# The parser-only baseline
# --------------------------------------------------------------------------


def test_the_baseline_counts_total_ways_and_retained_ways_separately(local_root, site):
    """Both counts matter, and conflating them is how the old figures got lost.

    Comparing two runs' timings is meaningless unless they parsed the same
    amount of file, so the baseline reports how many ways it saw as well as how
    many it kept.
    """

    from forecast.osm_parser_baseline import measure

    lon, lat = inside(site)
    pbf = write_pbf(
        local_root / "in" / "testland-220101.osm.pbf",
        [
            (60, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"}),
            (61, [(lon, lat + 0.002), (lon + 0.001, lat + 0.002)], {"waterway": "river"}),
            (62, [(lon, lat + 0.004), (lon + 0.001, lat + 0.004)], {"highway": "track"}),
        ],
        origin_year="2022",
    )

    result = measure(pbf, progress=False)

    assert result.total_ways == 3
    assert result.retained_ways == 2, "the waterway is parsed but not retained"
    assert result.node_cardinality == 4, "only retained ways contribute node refs"
    assert result.wall_clock_s > 0
    assert result.peak_commit_bytes > 0


def test_the_baseline_and_the_production_path_retain_identical_ways(local_root, site):
    """The precondition for comparing their costs at all.

    If these two ever disagreed, the difference in their wall clocks would be a
    difference in workload rather than the cost of the six extra stages.
    """

    from forecast.osm_parser_baseline import measure

    lon, lat = inside(site)
    ways = [
        (70, [(lon, lat), (lon + 0.001, lat)], {"highway": "residential"}),
        (71, [(lon, lat + 0.002), (lon + 0.001, lat + 0.002)], {"waterway": "river"}),
        (72, [(lon, lat + 0.004), (lon + 0.001, lat + 0.004)], {"highway": "service"}),
        (73, [(0.0, 0.0), (0.001, 0.0)], {"highway": "track"}),
    ]
    pbf = write_pbf(local_root / "in" / "testland-220101.osm.pbf", ways)

    baseline = measure(pbf, progress=False)
    produced = run_pass_one_file(
        pbf, build_site_windows([site]), ContentStore(local_root / "objects")
    )

    assert baseline.retained_ways == produced.counters.retained_ways
    assert baseline.node_cardinality == produced.counters.node_cardinality
    assert baseline.max_node_id == produced.counters.max_node_id


def test_dependency_versions_record_what_actually_resolved():
    versions = dependency_versions()
    assert versions["python"].startswith("3.")
    assert versions["osmium"] != "absent"
    assert versions["shapely"] != "absent"
