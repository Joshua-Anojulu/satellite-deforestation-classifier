"""Tests for the duplicate-group preflight and origin-level dedup (§4).

The central test is `test_a_moved_node_is_caught_by_coordinates_alone`.  It is
the case round-4 #2 identified and the one the measurement in §4.3 could not
have detected: a node moved between two regional build cutoffs leaves the
containing way's version, timestamp, tags and node-reference list untouched, so
a preflight checking references alone sees two identical ways and silently
chooses between differing geometries.  The test asserts the conflict is raised
*and* that node references are simultaneously equal, because a test that merely
found "some conflict" would not distinguish the two checks.

`test_publication_is_blocked_but_parsing_is_not` and
`test_regional_copies_collapse_to_one_record` assert the positive outcomes.  A
suite checking only that dirty input raises would pass over a `deduplicate` that
published nothing at all.
"""

from __future__ import annotations

import pytest

from forecast.osm_closure import RecordKey, SiteRecord
from forecast.osm_dedupe import (
    COORDINATE_GRID_DEG,
    OSM_TYPE_WAY,
    DirtyPreflight,
    GroupKey,
    MembershipKey,
    RegionWay,
    build_membership_table,
    canonical_tags,
    deduplicate,
    group_by_identity,
    preflight,
)
from forecast.osm_stream import RetainedWay

ORIGIN = 2020
HEADER_A = "2020-01-01T00:00:00Z"
HEADER_B = "2020-01-08T00:00:00Z"

REFS = (10, 11, 12)
COORDS = ((-63.30, 0.10), (-63.29, 0.11), (-63.28, 0.12))
TAGS = {"highway": "track", "surface": "dirt"}


def way(
    osm_id: int = 1,
    *,
    version: int = 3,
    timestamp: str = "2019-06-01T12:00:00Z",
    tags=None,
    refs=REFS,
    coords=COORDS,
) -> RetainedWay:
    return RetainedWay(
        osm_id=osm_id,
        version=version,
        timestamp=timestamp,
        tags=dict(TAGS if tags is None else tags),
        node_refs=refs,
        coordinates=coords,
        is_closed=False,
    )


def region(source_region: str, header: str = HEADER_A, **kwargs) -> RegionWay:
    return RegionWay(
        origin=ORIGIN,
        source_region=source_region,
        region_header_timestamp=header,
        way=way(**kwargs),
    )


class TestGrouping:
    def test_key_is_origin_type_and_id(self) -> None:
        groups = group_by_identity(
            [region("norte"), region("nordeste"), region("norte", osm_id=2)]
        )
        assert set(groups) == {
            GroupKey(ORIGIN, OSM_TYPE_WAY, 1),
            GroupKey(ORIGIN, OSM_TYPE_WAY, 2),
        }
        assert len(groups[GroupKey(ORIGIN, OSM_TYPE_WAY, 1)]) == 2

    def test_the_same_id_in_two_origins_is_two_groups(self) -> None:
        a = region("norte")
        b = RegionWay(
            origin=2021,
            source_region="norte",
            region_header_timestamp=HEADER_A,
            way=way(),
        )
        assert len(group_by_identity([a, b])) == 2


class TestAttributeAgreement:
    def test_a_clean_duplicate_pair_reports_nothing(self) -> None:
        report = preflight([region("norte"), region("nordeste", HEADER_B)])
        assert report.is_clean
        assert report.duplicate_groups == 1
        assert report.groups_checked == 1

    @pytest.mark.parametrize(
        "field,kwargs",
        [
            ("version", {"version": 4}),
            ("timestamp", {"timestamp": "2019-07-01T12:00:00Z"}),
            ("tags", {"tags": {"highway": "residential"}}),
        ],
    )
    def test_disagreement_fails_closed_and_is_reported(self, field, kwargs) -> None:
        report = preflight([region("norte"), region("nordeste", HEADER_B, **kwargs)])
        assert not report.is_clean
        conflict = report.attribute_conflicts[0]
        assert conflict.field == field
        assert {value[0] for value in conflict.values} == {"norte", "nordeste"}
        assert {value[1] for value in conflict.values} == {HEADER_A, HEADER_B}

    def test_attributes_are_checked_before_any_geometry_comparison(self) -> None:
        """§4.2.  Two records that disagree about *what way this is* have nothing
        to say about where it runs, so the geometry is never compared."""

        report = preflight(
            [
                region("norte"),
                region(
                    "nordeste",
                    HEADER_B,
                    version=4,
                    coords=((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
                ),
            ]
        )
        assert len(report.attribute_conflicts) == 1
        assert report.geometry_conflicts == ()

    def test_tag_order_does_not_manufacture_a_conflict(self) -> None:
        reordered = {"surface": "dirt", "highway": "track"}
        assert canonical_tags(reordered) == canonical_tags(TAGS)
        assert preflight([region("norte"), region("nordeste", tags=reordered)]).is_clean


class TestGeometryEquality:
    def test_a_moved_node_is_caught_by_coordinates_alone(self) -> None:
        """Round-4 #2, the whole reason both checks exist.

        Only the node moved, so the way object is genuinely unchanged: same
        version, same timestamp, same tags, same ordered references.  A
        reference-only preflight sees two identical ways here.
        """

        moved = (COORDS[0], (-63.29, 0.1100001), COORDS[2])
        report = preflight([region("norte"), region("nordeste", HEADER_B, coords=moved)])

        assert not report.is_clean
        assert report.attribute_conflicts == ()
        assert [c.kind for c in report.geometry_conflicts] == ["coordinates"]

        conflict = report.geometry_conflicts[0]
        assert conflict.a_node_refs == conflict.b_node_refs, (
            "the references agree; only the resolved coordinates differ"
        )
        assert conflict.positions == (1,)
        assert conflict.conflicting_node_ids == ((11, 11),)
        assert conflict.conflicting_coordinates == (((-63.29, 0.11), (-63.29, 0.1100001)),)
        assert (conflict.a_region, conflict.b_region) == ("norte", "nordeste")
        assert (conflict.a_header_timestamp, conflict.b_header_timestamp) == (
            HEADER_A,
            HEADER_B,
        )
        assert conflict.a_coordinates == COORDS and conflict.b_coordinates == moved

    def test_one_grid_unit_is_the_smallest_detectable_move(self) -> None:
        """The stated limit of "exact coordinate equality".

        OSM stores coordinates on a 1e-7 degree grid -- about 1.1 cm at the
        equator -- so this check detects moves of a grid unit and larger, which
        is not the same as detecting any move at all.
        """

        lon, lat = COORDS[1]
        one_unit = (COORDS[0], (lon, lat + COORDINATE_GRID_DEG), COORDS[2])
        assert not preflight(
            [region("norte"), region("nordeste", coords=one_unit)]
        ).is_clean

    def test_osm_coordinates_are_exactly_reproducible(self) -> None:
        """Why exact equality is the right predicate and no tolerance is used.

        `Location` quantises to the int32 grid, so float noise never reaches the
        comparison: the same input file yields bitwise-identical coordinates.
        """

        import osmium

        assert osmium.osm.Location(0.1 + 0.2, 0.0).lon == 0.3
        assert osmium.osm.Location(-63.3750001, 0.0).x == -633750001

    def test_reordered_nodes_conflict(self) -> None:
        report = preflight(
            [region("norte"), region("nordeste", refs=(10, 12, 11), coords=COORDS)]
        )
        assert [c.kind for c in report.geometry_conflicts] == ["node_refs"]
        assert report.geometry_conflicts[0].positions == (1, 2)

    def test_a_fragment_reports_the_missing_tail(self) -> None:
        """v3 would have reconciled this into a way present in no source."""

        report = preflight(
            [
                region("norte"),
                region("nordeste", refs=REFS[:2], coords=COORDS[:2]),
            ]
        )
        kinds = [c.kind for c in report.geometry_conflicts]
        assert kinds == ["node_refs", "coordinates"]
        assert all(c.positions == (2,) for c in report.geometry_conflicts)
        assert report.geometry_conflicts[0].conflicting_node_ids == ((12, None),)

    def test_three_regions_all_compared_against_the_anchor(self) -> None:
        report = preflight(
            [
                region("norte"),
                region("nordeste", coords=(COORDS[0], (0.0, 0.0), COORDS[2])),
                region("centro-oeste", coords=(COORDS[0], (1.0, 1.0), COORDS[2])),
            ]
        )
        assert {c.b_region for c in report.geometry_conflicts} == {
            "nordeste",
            "centro-oeste",
        }


class TestPublicationGate:
    def test_regional_copies_collapse_to_one_record(self) -> None:
        """The positive outcome: one record, both regions named (§4.1)."""

        records = [region("nordeste", HEADER_B), region("norte")]
        published = deduplicate(records, preflight(records))

        assert len(published) == 1
        row = published[0]
        assert (row.origin, row.osm_type, row.osm_id) == (ORIGIN, OSM_TYPE_WAY, 1)
        assert row.source_regions == ("nordeste", "norte")
        assert row.node_refs == REFS and row.coordinates == COORDS
        assert row.tags == TAGS

    def test_a_single_copy_is_published_and_is_not_a_duplicate_group(self) -> None:
        records = [region("norte"), region("norte", osm_id=2)]
        report = preflight(records)
        assert report.duplicate_groups == 0 and report.groups_checked == 2
        assert len(deduplicate(records, report)) == 2

    def test_publication_is_blocked_but_parsing_is_not(self) -> None:
        """§4.6: the gate is on publication.  A dirty preflight still returns a
        full report, so every conflict is visible in one run."""

        records = [region("norte"), region("nordeste", HEADER_B, version=9)]
        report = preflight(records)

        with pytest.raises(DirtyPreflight) as raised:
            deduplicate(records, report)
        assert raised.value.report is report
        assert "attribute" in str(raised.value)
        assert report.describe()

    def test_a_generator_cannot_silently_publish_nothing(self) -> None:
        """Both entry points materialise their input.

        Passing one generator to `preflight` and then to `deduplicate` would
        otherwise yield a clean report over a consumed iterator and publish an
        empty dataset with nothing raised.
        """

        records = (r for r in [region("norte"), region("nordeste")])
        report = preflight(records)
        assert deduplicate([region("norte"), region("nordeste")], report)


class TestMembershipTable:
    def test_membership_survives_the_dedup_key(self) -> None:
        """Round-8 #3: the published origin dataset names only source_regions,
        so per-site facts need their own key and their own table."""

        rows, conflicts = build_membership_table(
            [
                SiteRecord(RecordKey("site-a", ORIGIN, "norte", 1), True, True),
                SiteRecord(RecordKey("site-a", ORIGIN, "nordeste", 1), True, True),
                SiteRecord(RecordKey("site-b", ORIGIN, "norte", 1), False, True),
            ]
        )
        assert conflicts == ()
        assert [row.key for row in rows] == [
            MembershipKey("site-a", ORIGIN, OSM_TYPE_WAY, 1),
            MembershipKey("site-b", ORIGIN, OSM_TYPE_WAY, 1),
        ]
        assert rows[0].in_road_supply is True and rows[0].closure_only is False
        assert rows[1].closure_only is True and rows[1].in_road_supply is False

    def test_two_regional_copies_collapse_to_one_row(self) -> None:
        rows, conflicts = build_membership_table(
            [
                SiteRecord(RecordKey("site-a", ORIGIN, "norte", 1), True, False),
                SiteRecord(RecordKey("site-a", ORIGIN, "nordeste", 1), True, False),
            ]
        )
        assert conflicts == ()
        assert len(rows) == 1
        assert rows[0].intersects_window is True
        assert rows[0].selected_by_predicate is False
        assert rows[0].closure_only is True

    def test_disagreeing_copies_are_reported_never_merged(self) -> None:
        """An OR would paper over a dispatch that is not a function of the
        record -- which, given identical coordinates, is the only way this can
        happen."""

        rows, conflicts = build_membership_table(
            [
                SiteRecord(RecordKey("site-a", ORIGIN, "norte", 1), True, True),
                SiteRecord(RecordKey("site-a", ORIGIN, "nordeste", 1), False, True),
            ]
        )
        assert rows == ()
        assert len(conflicts) == 1
        assert conflicts[0].field == "intersects_window"
        assert set(conflicts[0].values) == {("norte", True), ("nordeste", False)}

    def test_membership_conflicts_make_the_report_dirty(self) -> None:
        records = [region("norte")]
        report = preflight(
            records,
            site_records=[
                SiteRecord(RecordKey("site-a", ORIGIN, "norte", 1), True, True),
                SiteRecord(RecordKey("site-a", ORIGIN, "nordeste", 1), True, False),
            ],
        )
        assert not report.is_clean
        with pytest.raises(DirtyPreflight):
            deduplicate(records, report)
