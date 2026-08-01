"""Tests for identity edges, the presence table and §6.5's operators.

The central test is `test_a_way_that_moved_eight_kilometres_still_gets_an_edge`.
That case is the entire reason §2.2 runs a second pass: a radius -- or a window
-- deletes exactly the counterpart the edge exists to catch, and v4's 2000 m
cutoff would have dropped it while a saturation statistic still looked healthy.

`test_a_missing_counterpart_produces_no_edge_but_a_presence_row` is the other
half of that promise.  Round-8 #1 bounded the guarantee to the acquired corpus,
and a half-populated edge row would erase the difference between "no
counterpart" and "counterpart not acquired".

The degenerate tests assert which metrics survive, not merely that nothing
raised.  A suite checking only "no ZeroDivisionError" would pass over a row that
silently reported `0.0` coverage for a way that is a single point.
"""

from __future__ import annotations

import math

import pytest
import shapely
from shapely.geometry import LineString

from forecast.osm_lineage import (
    BUFFER_CAP_STYLE,
    BUFFER_QUAD_SEGS,
    EDGE_COLUMNS,
    GLOBAL_COUNTERPART_STATUS,
    PRESENCE_COLUMNS,
    TAUS,
    Endpoint,
    UnbuildableGeometry,
    build_geometry,
    build_identity_edges,
    build_presence_table,
    buffer,
    edge_metrics,
)
from forecast.osm_windows import build_site_window

SITE = "t-1"
ORIGINS = (2020, 2021, 2022)

BOX = {"candidate_id": SITE, "west": -63.00, "south": 0.00, "east": -62.98, "north": 0.02}

#: Inside the site box.
NEAR = ((-62.995, 0.010), (-62.985, 0.010))
#: ~10 km east -- far outside the 5 km window, which is the point.
FAR = ((-62.895, 0.010), (-62.885, 0.010))


@pytest.fixture(scope="module")
def window():
    return build_site_window(BOX)


@pytest.fixture(scope="module")
def windows(window):
    return {SITE: window}


def endpoint(
    origin: int,
    coords=NEAR,
    *,
    osm_id: int = 1,
    intersects: bool = True,
    selected: bool = True,
    site_id: str = SITE,
) -> Endpoint:
    return Endpoint(
        site_id=site_id,
        origin=origin,
        osm_id=osm_id,
        coordinates=coords,
        intersects_window=intersects,
        selected_by_predicate=selected,
    )


class TestFrozenSchema:
    def test_taus_and_buffer_parameters_are_frozen(self) -> None:
        assert TAUS == (5, 10, 25, 50)
        assert (BUFFER_CAP_STYLE, BUFFER_QUAD_SEGS) == ("flat", 8)

    def test_edge_row_matches_the_frozen_column_list_exactly(self, windows) -> None:
        edges = build_identity_edges([endpoint(2020), endpoint(2021)], windows)
        assert tuple(edges[0].as_row()) == EDGE_COLUMNS
        assert len(EDGE_COLUMNS) == 25

    def test_presence_row_matches_its_column_list(self) -> None:
        rows = build_presence_table([endpoint(2020)], origins=ORIGINS)
        assert tuple(rows[0].as_row()) == PRESENCE_COLUMNS


class TestIdentityEdges:
    def test_a_way_that_moved_eight_kilometres_still_gets_an_edge(self, windows) -> None:
        """§6.1: linked regardless of separation, because pass 2 retained it.

        The far endpoint is outside the site window entirely -- it is
        `closure_only` -- which is exactly the record a radius would delete.
        """

        far = endpoint(2021, FAR, intersects=False, selected=True)
        edges = build_identity_edges([endpoint(2020), far], windows)

        assert len(edges) == 1
        edge = edges[0]
        assert (edge.a.origin, edge.b.origin) == (2020, 2021)
        assert edge.b.closure_only is True and edge.a.closure_only is False
        assert edge.metrics.min_distance_m == pytest.approx(10_000, rel=0.05)
        assert edge.metrics.degenerate_flag is False

    def test_origins_are_canonically_ordered(self, windows) -> None:
        edges = build_identity_edges([endpoint(2022), endpoint(2020)], windows)
        assert (edges[0].a.origin, edges[0].b.origin) == (2020, 2022)

    def test_three_origins_give_three_pairs(self, windows) -> None:
        edges = build_identity_edges(
            [endpoint(2020), endpoint(2021), endpoint(2022)], windows
        )
        assert [(e.a.origin, e.b.origin) for e in edges] == [
            (2020, 2021),
            (2020, 2022),
            (2021, 2022),
        ]

    def test_a_missing_counterpart_produces_no_edge_but_a_presence_row(
        self, windows
    ) -> None:
        """A half-populated edge row would erase §6.1's UNKNOWN (round-9 #5)."""

        endpoints = [endpoint(2020)]
        assert build_identity_edges(endpoints, windows) == ()

        rows = {row.origin: row for row in build_presence_table(endpoints, origins=ORIGINS)}
        assert rows[2020].presence_in_acquired_corpus is True
        assert rows[2021].presence_in_acquired_corpus is False
        assert rows[2022].presence_in_acquired_corpus is False

    def test_the_six_endpoint_flags_are_carried_per_endpoint(self, windows) -> None:
        """Round-6 #1: without them a consumer cannot tell an edge between two
        in-window ways from one whose far endpoint exists only as closure."""

        tag_changed = endpoint(2021, intersects=True, selected=False)
        row = build_identity_edges([endpoint(2020), tag_changed], windows)[0].as_row()

        assert row["a_intersects_window"] is True
        assert row["a_selected_by_predicate"] is True
        assert row["a_closure_only"] is False
        assert row["b_intersects_window"] is True
        assert row["b_selected_by_predicate"] is False
        assert row["b_closure_only"] is True

    def test_different_ways_and_sites_never_join(self, windows) -> None:
        edges = build_identity_edges(
            [endpoint(2020, osm_id=1), endpoint(2021, osm_id=2)], windows
        )
        assert edges == ()

    def test_duplicate_origins_are_refused(self, windows) -> None:
        """Dedup (§4) collapses regional copies; lineage runs after it."""

        with pytest.raises(ValueError, match="more than one endpoint per origin"):
            build_identity_edges([endpoint(2020), endpoint(2020)], windows)

    def test_both_endpoints_share_the_sites_frozen_projection(self, windows) -> None:
        """§6.5: one CRS per site window, never per way, so A->B and B->A agree."""

        a, b = endpoint(2020), endpoint(2021, FAR)
        forward = build_identity_edges([a, b], windows)[0].metrics
        backward = build_identity_edges([b, a], windows)[0].metrics
        assert forward.min_distance_m == backward.min_distance_m
        assert forward.hausdorff_m == backward.hausdorff_m


class TestPresenceTable:
    def test_status_is_always_unknown(self) -> None:
        """Absence from the acquired corpus is not absence from OSM (§6.1)."""

        rows = build_presence_table([endpoint(2020)], origins=ORIGINS)
        assert {row.global_counterpart_status for row in rows} == {
            GLOBAL_COUNTERPART_STATUS
        }
        assert GLOBAL_COUNTERPART_STATUS == "UNKNOWN"

    def test_every_pair_gets_a_row_for_every_corpus_origin(self) -> None:
        rows = build_presence_table(
            [endpoint(2020, osm_id=1), endpoint(2021, osm_id=2)], origins=ORIGINS
        )
        assert len(rows) == 2 * len(ORIGINS)
        assert [(r.osm_id, r.origin) for r in rows] == [
            (1, 2020), (1, 2021), (1, 2022),
            (2, 2020), (2, 2021), (2, 2022),
        ]

    def test_origins_are_required_and_never_inferred(self) -> None:
        """An origin with no rows is otherwise indistinguishable from one that
        was never acquired -- and absence is what this table carries."""

        with pytest.raises(ValueError, match="absence cannot be inferred"):
            build_presence_table([endpoint(2020)], origins=())

        rows = build_presence_table([endpoint(2020)], origins=(2020, 2021, 2022, 2023))
        assert len(rows) == 4
        assert [r.presence_in_acquired_corpus for r in rows] == [True, False, False, False]


class TestOperators:
    """§6.5, exercised on planar geometry so the expected values are exact."""

    def test_identical_geometry_scores_one_everywhere(self) -> None:
        line = LineString([(0, 0), (100, 0)])
        metrics = edge_metrics(line, LineString([(0, 0), (100, 0)]))

        assert metrics.min_distance_m == 0.0
        assert metrics.hausdorff_m == 0.0
        assert metrics.degenerate_flag is False
        for tau in TAUS:
            assert metrics.iou[tau] == pytest.approx(1.0)
            assert metrics.cov_a_in_b[tau] == pytest.approx(1.0)
            assert metrics.cov_b_in_a[tau] == pytest.approx(1.0)

    def test_parallel_offset_matches_the_closed_form_iou(self) -> None:
        """Two parallel flat-capped buffers give iou = (2t - d) / (2t + d)."""

        offset = 2.0
        metrics = edge_metrics(
            LineString([(0, 0), (100, 0)]), LineString([(0, offset), (100, offset)])
        )
        assert metrics.min_distance_m == pytest.approx(offset)
        assert metrics.hausdorff_m == pytest.approx(offset)
        for tau in TAUS:
            expected = (2 * tau - offset) / (2 * tau + offset)
            assert metrics.iou[tau] == pytest.approx(expected, rel=1e-6)
            assert metrics.cov_a_in_b[tau] == pytest.approx(1.0)

    def test_both_coverage_directions_are_emitted_and_differ(self) -> None:
        """§6.5 emits both explicitly rather than implying one from the other."""

        long_way = LineString([(0, 0), (200, 0)])
        short_way = LineString([(0, 0), (100, 0)])
        metrics = edge_metrics(long_way, short_way)

        for tau in TAUS:
            assert metrics.cov_a_in_b[tau] == pytest.approx(0.5)
            assert metrics.cov_b_in_a[tau] == pytest.approx(1.0)
        assert metrics.min_distance_m == 0.0
        assert metrics.hausdorff_m == pytest.approx(100.0)

    def test_hausdorff_is_the_max_of_both_directions(self) -> None:
        """GEOS already returns a symmetric value, measured on every probe.

        The max is taken explicitly anyway so the emitted number equals §6.5's
        stated definition even if a future GEOS returns a directed distance.
        """

        a = LineString([(0, 0), (100, 0)])
        b = LineString([(0, 0), (50, 40), (100, 0)])
        forward = shapely.hausdorff_distance(a, b)
        backward = shapely.hausdorff_distance(b, a)

        assert forward == backward
        assert edge_metrics(a, b).hausdorff_m == pytest.approx(max(forward, backward))

    def test_iou_and_distances_are_symmetric_but_coverage_is_not(self) -> None:
        a = LineString([(0, 0), (200, 0)])
        b = LineString([(0, 5), (100, 5)])
        forward, backward = edge_metrics(a, b), edge_metrics(b, a)

        assert forward.min_distance_m == pytest.approx(backward.min_distance_m)
        assert forward.hausdorff_m == pytest.approx(backward.hausdorff_m)
        for tau in TAUS:
            assert forward.iou[tau] == pytest.approx(backward.iou[tau])
            assert forward.cov_a_in_b[tau] == pytest.approx(backward.cov_b_in_a[tau])

    def test_a_closed_way_is_its_ring_traversal(self) -> None:
        """§6.5: lengths are perimeters, and no area semantics are applied."""

        ring = LineString([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        assert ring.length == 40.0
        metrics = edge_metrics(ring, ring)
        assert metrics.degenerate_flag is False
        assert metrics.cov_a_in_b[5] == pytest.approx(1.0)


class TestDegenerateGeometry:
    def test_a_flat_cap_makes_a_zero_length_buffer_empty(self) -> None:
        """Why the degenerate branch is required rather than merely cautious.

        A round cap would have returned a disc of ~78 m² at tau=5 and yielded a
        finite iou for a way that is a single point.
        """

        point_way = LineString([(0, 0), (0, 0)])
        assert point_way.length == 0.0
        assert buffer(point_way, 5).is_empty
        assert point_way.buffer(5, cap_style="round", quad_segs=8).area > 75

    def test_a_coincident_node_way_nulls_every_ratio_but_keeps_the_distances(
        self,
    ) -> None:
        """The deviation from a literal reading of "null metrics", asserted.

        §6.5's stated hazard is division by zero.  `min_distance_m` and
        `hausdorff_m` involve none and are well-defined for a zero-length way, so
        they are emitted; every buffer-derived ratio is null, because a coverage
        of `0.0` against an empty buffer is an artefact, not a measurement.
        """

        road = LineString([(0, 0), (100, 0)])
        point_way = LineString([(50, 0), (50, 0)])
        metrics = edge_metrics(road, point_way)

        assert metrics.degenerate_flag is True
        assert metrics.min_distance_m == 0.0
        assert metrics.hausdorff_m == pytest.approx(50.0)
        for tau in TAUS:
            assert metrics.iou[tau] is None
            assert metrics.cov_a_in_b[tau] is None
            assert metrics.cov_b_in_a[tau] is None

    def test_a_one_node_way_cannot_be_built_and_nulls_everything(self) -> None:
        """GEOS raises on a one-point array, and §1.3 permits such a way."""

        with pytest.raises(UnbuildableGeometry):
            build_geometry([(0.0, 0.0)])

        metrics = edge_metrics(None, LineString([(0, 0), (100, 0)]))
        assert metrics.degenerate_flag is True
        assert metrics.min_distance_m is None and metrics.hausdorff_m is None
        assert all(metrics.iou[tau] is None for tau in TAUS)

    def test_an_unbuildable_endpoint_still_produces_a_flagged_row(self, windows) -> None:
        """Never a silently dropped row (§6.5)."""

        edges = build_identity_edges(
            [endpoint(2020), endpoint(2021, ((-62.99, 0.01),))], windows
        )
        assert len(edges) == 1
        row = edges[0].as_row()
        assert row["degenerate_flag"] is True
        assert row["min_distance_m"] is None
        assert row["iou_50"] is None

    def test_no_metric_is_ever_nan(self, windows) -> None:
        """An empty LineString returns nan from distance and hausdorff without
        raising, so a NaN would sit in a metric column looking like a null."""

        edges = build_identity_edges(
            [
                endpoint(2020),
                endpoint(2021, ((-62.99, 0.01), (-62.99, 0.01))),
                endpoint(2022, ((-62.99, 0.01),)),
            ],
            windows,
        )
        assert len(edges) == 3
        for edge in edges:
            for column, value in edge.as_row().items():
                if isinstance(value, float):
                    assert not math.isnan(value), column
