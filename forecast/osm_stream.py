"""The frozen way stream: one pass per file per pass, with checked geometry.

Implements §1.1, §1.3, §1.4 and §1.5 of `OSM-NORMALISATION-PLAN.md`.

**The pipeline is frozen because the obvious form does not work.**  Node
locations are only available if nodes are in the entity set, so::

    FileProcessor(path, osmium.osm.WAY).with_locations()

raises ``RuntimeError: Nodes not read from file``.  The filter must remove nodes
*after* location assignment, not before:

    FileProcessor(path, NODE | WAY).with_locations().with_filter(EntityFilter(WAY))

That exact pipeline is the one measured: on ``indonesia-220101`` (1433 MB, the
largest extract) it streams 43,250,208 ways in 22.5 minutes with a peak commit
charge of 8.22 GB against 34.1 GB of RAM, and every one of the 4,839,062 retained
ways resolved a complete geometry.

**Silence is not evidence of valid geometry.**  Installed pyosmium's
``FileProcessor`` internally ignores missing-location errors, so a way whose nodes
were never resolved simply arrives with invalid locations and no complaint.  §1.5
therefore checks *every* node of *every* retained way and fails the stage closed
-- the measured count of invalid locations on the worst-case file is zero, which
is a checked invariant here rather than an assumption.

**Geometry is always a ``LineString``, with ``is_closed`` as a separate flag.**
An earlier draft invented a ``way_closed`` geometry class, which is not a
GeoParquet type.  A closed way is stored as its ordered ring traversal; area
semantics are excluded from Plan A entirely, and whether a plaza's perimeter,
area or centreline is the audited object is Plan B/C's decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence

import osmium

from forecast.osm_normalise import assert_known_highway_keys, retains

#: Nodes must be in the entity set for `.with_locations()` to populate the cache;
#: the filter drops them again once locations are assigned.
STREAM_ENTITIES = osmium.osm.NODE | osmium.osm.WAY

#: Frozen node-location index.  `flex_mem` is the sole backend: the measurement
#: above shows the in-memory index fits the largest extract with a wide margin,
#: which removes the on-disk backend and, with it, every question about
#: interrupted index files.
INDEX_BACKEND = "flex_mem"


class InvalidWayGeometry(Exception):
    """A retained way has an empty node list or an unresolved node location.

    Fails the stage closed rather than emitting a partial geometry, because the
    parser will not report the condition on its own.
    """

    def __init__(self, osm_id: int, reason: str, node_ref: int | None = None) -> None:
        self.osm_id = osm_id
        self.reason = reason
        self.node_ref = node_ref
        where = f" (node {node_ref})" if node_ref is not None else ""
        super().__init__(f"way {osm_id}: {reason}{where}")


@dataclass(frozen=True)
class RetainedWay:
    """What §1.3 keeps for every retained way.

    Convenience columns are deliberately absent -- they are redundant projections
    of these fields, and each one is another thing that can disagree.
    """

    osm_id: int
    version: int
    timestamp: str
    tags: dict[str, str]
    node_refs: tuple[int, ...]
    coordinates: tuple[tuple[float, float], ...]
    is_closed: bool

    def __post_init__(self) -> None:
        if len(self.node_refs) != len(self.coordinates):
            raise ValueError(
                f"way {self.osm_id}: {len(self.node_refs)} refs but "
                f"{len(self.coordinates)} coordinates"
            )


def is_closed_ring(node_refs: Sequence[int]) -> bool:
    """A way is closed iff it has at least two nodes and its ends coincide.

    Defined on the references rather than delegated, so it can be exercised
    without an osmium object; a test asserts it agrees with `osmium`'s own rule.
    """

    return len(node_refs) >= 2 and node_refs[0] == node_refs[-1]


def build_retained_way(way: osmium.osm.Way) -> RetainedWay:
    """Extract a retained way, validating every node location (§1.5).

    Raises :class:`InvalidWayGeometry` on an empty node list or any unresolved
    location.  Raises :class:`~forecast.osm_normalise.UnknownHighwayNamespace` if
    the way carries a `*:highway` key outside the frozen table.
    """

    assert_known_highway_keys(way.tags, way.id)

    nodes = way.nodes
    if not len(nodes):
        raise InvalidWayGeometry(way.id, "empty node list")

    refs: list[int] = []
    coordinates: list[tuple[float, float]] = []
    for node in nodes:
        if not node.location.valid():
            raise InvalidWayGeometry(way.id, "unresolved node location", node.ref)
        refs.append(node.ref)
        coordinates.append((node.location.lon, node.location.lat))

    return RetainedWay(
        osm_id=way.id,
        version=way.version,
        timestamp=way.timestamp.isoformat(),
        tags={tag.k: tag.v for tag in way.tags},
        node_refs=tuple(refs),
        coordinates=tuple(coordinates),
        is_closed=is_closed_ring(refs),
    )


def way_processor(path: str) -> osmium.FileProcessor:
    """The frozen pipeline (§1.1).  Nodes in, locations resolved, nodes filtered out."""

    return (
        osmium.FileProcessor(str(path), STREAM_ENTITIES)
        .with_locations(INDEX_BACKEND)
        .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
    )


def stream_retained_ways(path: str) -> Iterator[RetainedWay]:
    """Yield every retained way from one extract, in file order.

    One stream per file per pass.  Selection is by direct key lookup (§1.2);
    only retained ways pay the cost of geometry extraction and validation.
    """

    for way in way_processor(path):
        if retains(way.tags):
            yield build_retained_way(way)
