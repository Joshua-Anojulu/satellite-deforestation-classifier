"""Tests for the frozen way stream (§1.1, §1.3, §1.4, §1.5).

These build real `.osm.pbf` fixtures with `osmium.SimpleWriter` and run the
production pipeline over them, rather than mocking the parser.  The point of the
module is what the parser actually does, so a mock would test the wrong thing --
particularly for §1.5, whose whole premise is that pyosmium stays *silent* about
unresolved locations.
"""

from __future__ import annotations

import datetime as dt

import osmium
import osmium.osm.mutable as om
import pytest

from forecast.osm_normalise import UnknownHighwayNamespace
from forecast.osm_stream import (
    InvalidWayGeometry,
    RetainedWay,
    build_retained_way,
    is_closed_ring,
    stream_retained_ways,
    way_processor,
)

TS = dt.datetime(2021, 6, 1, 12, 0, 0, tzinfo=dt.timezone.utc)


def write_pbf(path, nodes, ways):
    """Write a tiny extract.  `nodes` is {id: (lon, lat)}, `ways` is a list of dicts."""

    writer = osmium.SimpleWriter(str(path))
    try:
        for node_id, (lon, lat) in sorted(nodes.items()):
            writer.add_node(
                om.Node(id=node_id, location=(lon, lat), tags={}, version=1, timestamp=TS)
            )
        for way in ways:
            writer.add_way(
                om.Way(
                    id=way["id"],
                    nodes=way["nodes"],
                    tags=way["tags"],
                    version=way.get("version", 1),
                    timestamp=TS,
                )
            )
    finally:
        writer.close()
    return path


@pytest.fixture
def simple_extract(tmp_path):
    """One open road, one closed ring, one area, one lifecycle-only, one non-road."""

    nodes = {
        1: (10.0, 50.0),
        2: (10.001, 50.0),
        3: (10.001, 50.001),
        4: (10.0, 50.001),
        5: (11.0, 51.0),
        6: (11.001, 51.0),
    }
    ways = [
        {"id": 100, "nodes": [1, 2, 3], "tags": {"highway": "residential"}},
        {"id": 101, "nodes": [1, 2, 3, 4, 1], "tags": {"highway": "service"}},
        {"id": 102, "nodes": [1, 2, 3, 1], "tags": {"area:highway": "yes"}},
        {"id": 103, "nodes": [5, 6], "tags": {"destroyed:highway": "track"}},
        {"id": 104, "nodes": [5, 6], "tags": {"building": "yes"}},
    ]
    return write_pbf(tmp_path / "simple.osm.pbf", nodes, ways)


class TestFrozenPipeline:
    def test_ways_only_pipeline_cannot_resolve_locations(self, simple_extract) -> None:
        """The reason the pipeline has its shape, made executable.

        `FileProcessor(path, WAY).with_locations()` is the obvious form and it does
        not work -- nodes must be in the entity set to reach the location cache.
        """

        with pytest.raises(RuntimeError, match="Nodes not read from file"):
            processor = osmium.FileProcessor(
                str(simple_extract), osmium.osm.WAY
            ).with_locations()
            next(iter(processor))

    def test_frozen_pipeline_yields_ways_with_resolved_locations(
        self, simple_extract
    ) -> None:
        ids, all_valid = [], []
        for way in way_processor(str(simple_extract)):
            ids.append(way.id)
            all_valid.append(all(node.location.valid() for node in way.nodes))
        assert ids == [100, 101, 102, 103, 104]
        assert all(all_valid)

    def test_yielded_way_is_invalidated_once_the_iterator_advances(
        self, simple_extract
    ) -> None:
        """Why `RetainedWay` exists: the parser reuses one object.

        Holding a yielded `Way` past its iteration step raises rather than
        returning stale data, so every field must be copied out during the step.
        """

        iterator = iter(way_processor(str(simple_extract)))
        first = next(iterator)
        assert first.id == 100
        next(iterator)
        with pytest.raises(RuntimeError, match="removed OSM object"):
            _ = first.nodes


class TestSelectionAndGeometry:
    def test_only_retained_ways_are_yielded(self, simple_extract) -> None:
        ways = list(stream_retained_ways(str(simple_extract)))
        assert [w.osm_id for w in ways] == [100, 101, 102, 103]  # 104 is a building

    def test_open_way_geometry(self, simple_extract) -> None:
        way = next(w for w in stream_retained_ways(str(simple_extract)) if w.osm_id == 100)
        assert way.node_refs == (1, 2, 3)
        assert len(way.coordinates) == 3
        assert way.coordinates[0] == pytest.approx((10.0, 50.0), abs=1e-6)
        assert way.is_closed is False
        assert way.tags == {"highway": "residential"}
        assert way.version == 1
        assert way.timestamp.startswith("2021-06-01")

    def test_closed_way_is_a_linestring_with_a_flag(self, simple_extract) -> None:
        """Not a separate geometry class -- a ring traversal plus `is_closed`."""

        way = next(w for w in stream_retained_ways(str(simple_extract)) if w.osm_id == 101)
        assert way.is_closed is True
        assert way.node_refs[0] == way.node_refs[-1] == 1
        assert len(way.coordinates) == len(way.node_refs) == 5

    def test_area_highway_is_retained_and_carries_no_area_semantics(
        self, simple_extract
    ) -> None:
        way = next(w for w in stream_retained_ways(str(simple_extract)) if w.osm_id == 102)
        assert way.is_closed is True
        assert set(way.tags) == {"area:highway"}
        assert not hasattr(way, "area")

    def test_lifecycle_only_way_is_retained(self, simple_extract) -> None:
        way = next(w for w in stream_retained_ways(str(simple_extract)) if w.osm_id == 103)
        assert way.tags == {"destroyed:highway": "track"}

    def test_is_closed_ring_agrees_with_osmium(self, simple_extract) -> None:
        for way in way_processor(str(simple_extract)):
            assert is_closed_ring([n.ref for n in way.nodes]) is bool(way.is_closed())


class TestFailsClosedOnGeometry:
    def test_unresolved_node_location_fails_closed(self, tmp_path) -> None:
        """The case pyosmium reports by staying silent.

        Way 200 references node 99, which the extract does not contain.  The
        parser yields the way regardless, with an invalid location.
        """

        path = write_pbf(
            tmp_path / "missing.osm.pbf",
            nodes={1: (10.0, 50.0), 2: (10.001, 50.0)},
            ways=[{"id": 200, "nodes": [1, 2, 99], "tags": {"highway": "track"}}],
        )

        # The parser itself does not complain -- that is the premise of §1.5.
        # Validity must be read inside the iteration step; the object is reused.
        validity = [
            all(node.location.valid() for node in way.nodes)
            for way in way_processor(str(path))
        ]
        assert validity == [False]

        with pytest.raises(InvalidWayGeometry) as excinfo:
            list(stream_retained_ways(str(path)))
        assert excinfo.value.osm_id == 200
        assert excinfo.value.node_ref == 99
        assert "unresolved node location" in str(excinfo.value)

    def test_unknown_highway_namespace_fails_closed(self, tmp_path) -> None:
        path = write_pbf(
            tmp_path / "unknown.osm.pbf",
            nodes={1: (10.0, 50.0), 2: (10.001, 50.0)},
            ways=[
                {"id": 300, "nodes": [1, 2], "tags": {"highway": "track", "mystery:highway": "x"}}
            ],
        )
        with pytest.raises(UnknownHighwayNamespace):
            list(stream_retained_ways(str(path)))


class TestRetainedWayInvariants:
    def test_refs_and_coordinates_must_agree(self) -> None:
        with pytest.raises(ValueError, match="2 refs but 1 coordinates"):
            RetainedWay(
                osm_id=1,
                version=1,
                timestamp="2021-06-01T12:00:00+00:00",
                tags={},
                node_refs=(1, 2),
                coordinates=((0.0, 0.0),),
                is_closed=False,
            )

    @pytest.mark.parametrize(
        "refs,expected",
        [((), False), ((1,), False), ((1, 1), True), ((1, 2, 1), True), ((1, 2, 3), False)],
    )
    def test_is_closed_ring_edges(self, refs, expected) -> None:
        assert is_closed_ring(refs) is expected
