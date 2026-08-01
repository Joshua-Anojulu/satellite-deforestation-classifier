"""Duplicate-group preflight and origin-level deduplication.

Implements §4 of `OSM-NORMALISATION-PLAN.md`.

**Dedup collapses regional copies to one record per `(origin, osm_type, osm_id)`,
and the published origin dataset names only `source_regions[]`** (§4.1).  Site
membership does not survive that key -- a single-origin way has nowhere to carry
which sites contain it, and identity edges cannot supply it either (round-8 #3).
The membership table is therefore its own manifest-bound artifact keyed
`(site_id, origin, osm_type, osm_id)`, built here rather than left for a consumer
to re-derive.

**Attributes are checked before any geometry comparison** (§4.2, round-2 #6).
Version, timestamp and the canonical tag map must agree first; a group that fails
that check is reported and its geometry is never compared, because two records
that disagree about *what way this is* have nothing to say about where it runs.

**Node-reference equality alone is not geometric equality** (§4.3, round-4 #2).
A referenced node can be *moved* between two regional build cutoffs without
touching the containing way's version, timestamp, tags or node-reference list --
the way object is genuinely unchanged, because only the node changed.  Checking
references alone would then see two identical ways and silently pick one of two
differing coordinate sequences.  Both are checked.

**Exact equality is the correct predicate, and that is a measured property of the
format, not an assumption.**  OSM stores coordinates as int32 at 1e-7 degrees and
pyosmium's `Location.lon` is that integer divided by 1e7, so the same input file
yields bitwise-identical floats across runs -- `Location(0.1 + 0.2).lon` is
exactly `0.3`, because the grid absorbs the float noise.  No tolerance is needed
and none is used.  The stated limit: the grid is ~1.1 cm at the equator, so a
node moved less than 1e-7 degrees is invisible to this check.  It detects moves
of ~1.1 cm and larger, which is not the same as detecting any move at all.

**Nothing here reconciles anything** (§4.3).  v3 tried to merge fragments into a
"unique consistent global sequence", which is undefined for repeated nodes,
closed-ring rotations, reversals and competing supersequences, and could produce
a way present in no source.  Geofabrik keeps ways crossing an extract boundary
complete -- measured across 32,369 shared IDs in 7 land-border pairs at origin
2020, with zero node-reference and zero version mismatches -- so a fragment pair
should not arise.  If one does, the sources disagree, and the response is to stop
and report.

**The report is collected, not raised on first sight.**  §4.3 requires conflicts
reported with both sequences, the conflicting node IDs and coordinates, the
regions involved and their header timestamps.  Raising at the first mismatch
would surface one conflict per run and hide the shape of the disagreement.

**Ordering (§4.6, round-5 #3).**  Preflight reads committed region checkpoints
only -- never a PBF -- which is the sole reason it is cheap.  Coordinates are
retained per §1.3, but only *after* the node index and parser have produced
region records, so running this before the corpus run would need its own full
node-and-way pass.  A dirty preflight **blocks publication**; it does not block
parsing, which it never could.  `deduplicate` enforces that gate directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from forecast.osm_closure import SiteRecord
from forecast.osm_stream import RetainedWay

#: Plan A streams ways only; the key carries the type so the published schema
#: does not have to change when nodes or relations are added.
OSM_TYPE_WAY = "way"

#: The coordinate grid, in degrees.  Stated because it bounds what §4.3 detects.
COORDINATE_GRID_DEG = 1e-7


class DirtyPreflight(Exception):
    """Publication was attempted with unresolved duplicate-group conflicts."""

    def __init__(self, report: "PreflightReport") -> None:
        self.report = report
        super().__init__(
            f"preflight is dirty: {len(report.attribute_conflicts)} attribute, "
            f"{len(report.geometry_conflicts)} geometry, "
            f"{len(report.membership_conflicts)} membership conflicts"
        )


class GroupKey(tuple):
    """`(origin, osm_type, osm_id)` -- the §4.1 deduplication key."""

    __slots__ = ()

    def __new__(cls, origin: int, osm_type: str, osm_id: int) -> "GroupKey":
        return super().__new__(cls, (origin, osm_type, osm_id))

    @property
    def origin(self) -> int:
        return self[0]

    @property
    def osm_type(self) -> str:
        return self[1]

    @property
    def osm_id(self) -> int:
        return self[2]


class MembershipKey(tuple):
    """`(site_id, origin, osm_type, osm_id)` -- the §4.1 membership key."""

    __slots__ = ()

    def __new__(
        cls, site_id: str, origin: int, osm_type: str, osm_id: int
    ) -> "MembershipKey":
        return super().__new__(cls, (site_id, origin, osm_type, osm_id))

    @property
    def site_id(self) -> str:
        return self[0]


@dataclass(frozen=True)
class RegionWay:
    """One way as retained from one committed `(origin, source_region)` checkpoint.

    Carries the region header timestamp because §4.3 requires it in every
    conflict report -- when two regions disagree, which snapshots they were cut
    from is the first thing needed to tell why.
    """

    origin: int
    source_region: str
    region_header_timestamp: str
    way: RetainedWay
    osm_type: str = OSM_TYPE_WAY

    @property
    def group_key(self) -> GroupKey:
        return GroupKey(self.origin, self.osm_type, self.way.osm_id)


@dataclass(frozen=True)
class OriginWay:
    """The deduplicated record: one way per `(origin, osm_type, osm_id)`."""

    origin: int
    osm_type: str
    osm_id: int
    version: int
    timestamp: str
    tags: Mapping[str, str]
    node_refs: tuple[int, ...]
    coordinates: tuple[tuple[float, float], ...]
    is_closed: bool
    source_regions: tuple[str, ...]


@dataclass(frozen=True)
class MembershipRow:
    """§4.1's per-site row, which the dedup key cannot carry."""

    key: MembershipKey
    intersects_window: bool
    selected_by_predicate: bool

    @property
    def closure_only(self) -> bool:
        return not (self.intersects_window and self.selected_by_predicate)

    @property
    def in_road_supply(self) -> bool:
        return self.intersects_window and self.selected_by_predicate


@dataclass(frozen=True)
class AttributeConflict:
    """§4.2: group members disagree on identity before geometry is looked at."""

    group: GroupKey
    field: str
    values: tuple[tuple[str, str, object], ...]  # (region, header_timestamp, value)

    def describe(self) -> str:
        rendered = "; ".join(
            f"{region}@{header}={value!r}" for region, header, value in self.values
        )
        return f"{self.group}: {self.field} disagrees -- {rendered}"


@dataclass(frozen=True)
class GeometryConflict:
    """§4.3: everything needed to diagnose the disagreement, in one row."""

    group: GroupKey
    kind: str  # "node_refs" | "coordinates"
    a_region: str
    b_region: str
    a_header_timestamp: str
    b_header_timestamp: str
    positions: tuple[int, ...]
    a_node_refs: tuple[int, ...]
    b_node_refs: tuple[int, ...]
    a_coordinates: tuple[tuple[float, float], ...]
    b_coordinates: tuple[tuple[float, float], ...]

    @property
    def conflicting_node_ids(self) -> tuple[tuple[int | None, int | None], ...]:
        return tuple(
            (
                self.a_node_refs[i] if i < len(self.a_node_refs) else None,
                self.b_node_refs[i] if i < len(self.b_node_refs) else None,
            )
            for i in self.positions
        )

    @property
    def conflicting_coordinates(self):
        return tuple(
            (
                self.a_coordinates[i] if i < len(self.a_coordinates) else None,
                self.b_coordinates[i] if i < len(self.b_coordinates) else None,
            )
            for i in self.positions
        )

    def describe(self) -> str:
        return (
            f"{self.group}: {self.kind} differ between {self.a_region}"
            f"@{self.a_header_timestamp} and {self.b_region}"
            f"@{self.b_header_timestamp} at positions {self.positions}"
        )


@dataclass(frozen=True)
class MembershipConflict:
    """Two regional copies of one way disagree about a site flag.

    Coordinates and tags are already proven identical by the time this can fire,
    so the two copies must produce the same answer.  A disagreement means the
    dispatch or the predicate is not a function of the record, which is a defect
    in this pipeline rather than in the sources.
    """

    key: MembershipKey
    field: str
    values: tuple[tuple[str, bool], ...]  # (source_region, value)


@dataclass(frozen=True)
class PreflightReport:
    attribute_conflicts: tuple[AttributeConflict, ...]
    geometry_conflicts: tuple[GeometryConflict, ...]
    membership_conflicts: tuple[MembershipConflict, ...]
    groups_checked: int
    duplicate_groups: int

    @property
    def is_clean(self) -> bool:
        return not (
            self.attribute_conflicts
            or self.geometry_conflicts
            or self.membership_conflicts
        )

    def require_clean(self) -> None:
        if not self.is_clean:
            raise DirtyPreflight(self)

    def describe(self) -> str:
        lines = [
            f"{self.groups_checked} groups checked, "
            f"{self.duplicate_groups} with more than one regional copy"
        ]
        lines += [conflict.describe() for conflict in self.attribute_conflicts]
        lines += [conflict.describe() for conflict in self.geometry_conflicts]
        lines += [
            f"{conflict.key}: {conflict.field} disagrees -- {conflict.values}"
            for conflict in self.membership_conflicts
        ]
        return "\n".join(lines)


def canonical_tags(tags: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """The canonical tag map: key-sorted pairs.

    Dict equality is already order-independent, so this exists for *reporting* --
    a conflict must render the same way whatever order the parser emitted tags in.
    """

    return tuple(sorted(tags.items()))


def group_by_identity(
    records: Iterable[RegionWay],
) -> dict[GroupKey, tuple[RegionWay, ...]]:
    """Bucket regional records by the §4.1 key, preserving input order."""

    groups: dict[GroupKey, list[RegionWay]] = {}
    for record in records:
        groups.setdefault(record.group_key, []).append(record)
    return {key: tuple(members) for key, members in groups.items()}


def _attribute_conflicts(
    key: GroupKey, members: Sequence[RegionWay]
) -> list[AttributeConflict]:
    conflicts: list[AttributeConflict] = []
    fields = (
        ("version", lambda r: r.way.version),
        ("timestamp", lambda r: r.way.timestamp),
        ("tags", lambda r: canonical_tags(r.way.tags)),
    )
    for field, read in fields:
        values = {read(member) for member in members}
        if len(values) > 1:
            conflicts.append(
                AttributeConflict(
                    group=key,
                    field=field,
                    values=tuple(
                        (m.source_region, m.region_header_timestamp, read(m))
                        for m in members
                    ),
                )
            )
    return conflicts


def _differing_positions(a: Sequence, b: Sequence) -> tuple[int, ...]:
    """Positions that differ, including every position past a length mismatch."""

    positions = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    positions.extend(range(min(len(a), len(b)), max(len(a), len(b))))
    return tuple(positions)


def _geometry_conflicts(
    key: GroupKey, members: Sequence[RegionWay]
) -> list[GeometryConflict]:
    """Compare every member against the first, on references then coordinates."""

    conflicts: list[GeometryConflict] = []
    anchor = members[0]
    for other in members[1:]:
        for kind, left, right in (
            ("node_refs", anchor.way.node_refs, other.way.node_refs),
            ("coordinates", anchor.way.coordinates, other.way.coordinates),
        ):
            positions = _differing_positions(left, right)
            if positions:
                conflicts.append(
                    GeometryConflict(
                        group=key,
                        kind=kind,
                        a_region=anchor.source_region,
                        b_region=other.source_region,
                        a_header_timestamp=anchor.region_header_timestamp,
                        b_header_timestamp=other.region_header_timestamp,
                        positions=positions,
                        a_node_refs=anchor.way.node_refs,
                        b_node_refs=other.way.node_refs,
                        a_coordinates=anchor.way.coordinates,
                        b_coordinates=other.way.coordinates,
                    )
                )
    return conflicts


def build_membership_table(
    site_records: Iterable[SiteRecord],
    *,
    osm_type: str = OSM_TYPE_WAY,
) -> tuple[tuple[MembershipRow, ...], tuple[MembershipConflict, ...]]:
    """Collapse per-region site records onto the §4.1 membership key.

    Regional copies of one way must agree on both flags -- their tags and
    coordinates are identical by the time this runs, so the flags are functions
    of the same input.  Disagreement is reported rather than merged; an `OR`
    would paper over a non-deterministic dispatch, which is exactly the defect
    worth surfacing.
    """

    seen: dict[MembershipKey, list[SiteRecord]] = {}
    for record in site_records:
        key = MembershipKey(
            record.key.site_id, record.key.origin, osm_type, record.key.osm_id
        )
        seen.setdefault(key, []).append(record)

    rows: list[MembershipRow] = []
    conflicts: list[MembershipConflict] = []
    for key, records in seen.items():
        dirty = False
        for field in ("intersects_window", "selected_by_predicate"):
            values = {getattr(record, field) for record in records}
            if len(values) > 1:
                dirty = True
                conflicts.append(
                    MembershipConflict(
                        key=key,
                        field=field,
                        values=tuple(
                            (record.key.source_region, getattr(record, field))
                            for record in records
                        ),
                    )
                )
        if not dirty:
            rows.append(
                MembershipRow(
                    key=key,
                    intersects_window=records[0].intersects_window,
                    selected_by_predicate=records[0].selected_by_predicate,
                )
            )
    return tuple(sorted(rows, key=lambda row: row.key)), tuple(conflicts)


def preflight(
    records: Iterable[RegionWay],
    *,
    site_records: Iterable[SiteRecord] = (),
) -> PreflightReport:
    """Run the §4 duplicate-group preflight over committed region checkpoints.

    Attributes are compared first and geometry is skipped for any group that
    fails them (§4.2).  Every conflict is collected; nothing raises here.

    `records` is materialised on entry: a caller passing one generator to both
    this and :func:`deduplicate` would otherwise publish an empty dataset with
    a clean report and nothing raised anywhere.
    """

    groups = group_by_identity(tuple(records))
    attribute: list[AttributeConflict] = []
    geometry: list[GeometryConflict] = []
    duplicates = 0

    for key, members in groups.items():
        if len(members) < 2:
            continue
        duplicates += 1
        group_attribute = _attribute_conflicts(key, members)
        if group_attribute:
            attribute.extend(group_attribute)
            continue  # §4.2: no geometry comparison for a group that disagrees
        geometry.extend(_geometry_conflicts(key, members))

    _, membership_conflicts = build_membership_table(site_records)

    return PreflightReport(
        attribute_conflicts=tuple(attribute),
        geometry_conflicts=tuple(geometry),
        membership_conflicts=membership_conflicts,
        groups_checked=len(groups),
        duplicate_groups=duplicates,
    )


def deduplicate(
    records: Iterable[RegionWay], report: PreflightReport
) -> tuple[OriginWay, ...]:
    """Collapse to one record per `(origin, osm_type, osm_id)` (§4.1).

    Refuses to run on a dirty report.  §4.6: a dirty preflight blocks
    publication -- it does not block parsing, and this is the gate that makes
    that true rather than a statement in a document.
    """

    report.require_clean()

    groups = group_by_identity(tuple(records))
    published: list[OriginWay] = []
    for key, members in sorted(groups.items()):
        first = members[0].way
        published.append(
            OriginWay(
                origin=key.origin,
                osm_type=key.osm_type,
                osm_id=key.osm_id,
                version=first.version,
                timestamp=first.timestamp,
                tags=dict(first.tags),
                node_refs=first.node_refs,
                coordinates=first.coordinates,
                is_closed=first.is_closed,
                source_regions=tuple(
                    sorted({member.source_region for member in members})
                ),
            )
        )
    return tuple(published)
