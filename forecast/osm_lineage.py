"""Identity edges, the presence table, and §6.5's measurement operators.

Implements §6 of `OSM-NORMALISATION-PLAN.md`.

**Identity only.  Plan A generates no spatial candidates** (round-4 #5).  v4
froze a 2000 m outer radius and a 0.5 % saturation criterion; both are scientific
cutoffs, and a site dominated by short-distance edges passes the saturation test
while a rare renumbered road sits beyond 2 km unseen.  Identity is direct
evidence and needs no radius: a road that moved 8 km is exactly the case a radius
would have deleted.  No components, no aggregates, no `resolved`/`unresolved`
vocabulary -- those need a candidate graph, which belongs to Plan B (§6.6).

**The guarantee is bounded by the acquired corpus, and absence is `UNKNOWN`**
(§6.1, round-8 #1).  Pass 2 streams the 36 extracts, so a counterpart that moved
outside their union is silently absent.  `global_counterpart_status` is therefore
**always `UNKNOWN`** here: absence from the acquired corpus is not absence from
OSM, and only globally covering snapshots could tell them apart.

**Edges are built only between present endpoints** (§6.3).  A missing
counterpart is represented in the presence table, never as a half-populated edge
row -- otherwise a consumer cannot distinguish "no counterpart" from "counterpart
not acquired", which is the whole distinction §6.1 exists to preserve.

**The corpus origins must be passed in, not inferred from the data.**  Absence is
the fact the presence table exists to carry, and an origin with no rows for a
site is indistinguishable from an origin that was never acquired if the origin
list is derived from the rows themselves.

**One CRS per site window, never per way** (§6.5).  `SiteWindow` supplies it, so
the projection is the same rule §2.3 froze -- and specifically not a recomputed
centroid, which flips zone for the site centred at longitude exactly 24.0.
Because both endpoints are measured in the same projection, `A->B` and `B->A`
agree by construction.

**Measured against the installed Shapely before being encoded, not after:**

* `hausdorff_distance` is **already symmetric** in GEOS -- `h(A,B) == h(B,A)` on
  every probe, including an asymmetric spike.  The plan defines `hausdorff_m` as
  `max(directed(A,B), directed(B,A))`, so the max is taken explicitly anyway: it
  costs one call and keeps the emitted number equal to the stated definition even
  if a future GEOS returns a directed distance.  GEOS measures each vertex
  against the *whole* other geometry, and densifying changed nothing on the
  probes, so the discrete distance is used as-is.
* **A flat end cap makes the buffer of a zero-length way empty** -- area 0.0,
  not a disc.  A round cap would have produced 78 m² at tau=5 and quietly
  yielded a finite iou for a way that is a single point.  The two frozen buffer
  parameters interact, and the degenerate branch below is required by that
  interaction rather than by caution.
* **A one-node way cannot become a `LineString` at all** -- GEOS raises
  `IllegalArgumentException: point array must contain 0 or >1 elements`.  §1.3
  permits such a way (it only checks that refs and coordinates agree in length),
  so this is caught before geometry construction rather than at it.
* **An empty `LineString` returns `nan` from `distance` and
  `hausdorff_distance`, silently.**  A NaN would occupy a metric column looking
  like a null while carrying none of a null's meaning, so no metric is ever
  computed from a geometry that could be empty.

**Degeneracy: what is nulled, and one place where this deviates from the frozen
text.**  §6.5 says a degenerate row is emitted with "null metrics and
`degenerate_flag` set -- never a division by zero and never a silently dropped
row".  Every buffer-derived metric is nulled here, which is what that requires:
`iou_tau` is `0/0` when a buffer is empty, and a coverage of exactly `0.0`
computed against an empty buffer is an artefact of the degeneracy rather than a
measurement, which a consumer would read as "0 % covered".

`min_distance_m` and `hausdorff_m` are **emitted** for a degenerate pair whose
geometries can still be built, because they involve no division and are
well-defined for a zero-length way -- a coincident-node way sitting on top of a
road really is 0 m from it.  The stated hazard is division by zero, and nulling
these would discard real measurements no hazard requires discarding.  Where a
geometry cannot be built at all (fewer than two coordinates) every metric is
null, because there is nothing to measure.

**This deviation from a literal reading of "null metrics" was raised with the
owner and RULED ON (2026-08-01): the two measurements stay.**  The plan's hazard
is division by zero, these two carry none, and `degenerate_flag` already tells a
consumer exactly which rows to treat carefully.  The literal reading remains a
one-line revert in :func:`edge_metrics` if it is ever wanted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import shapely
from shapely.geometry import LineString

from forecast.osm_windows import SiteWindow, lineal_parts

#: Frozen coverage and overlap scales, in metres (§6.5).
TAUS = (5, 10, 25, 50)

#: Frozen buffer parameters (§6.5).  Buffer geometry is parameter-dependent, so
#: these are part of the contract rather than library defaults.
BUFFER_CAP_STYLE = "flat"
BUFFER_JOIN_STYLE = "round"
BUFFER_QUAD_SEGS = 8

#: §6.3.  Plan A never resolves this: absence from the acquired corpus is not
#: absence from OSM.
GLOBAL_COUNTERPART_STATUS = "UNKNOWN"

EDGE_COLUMNS = (
    "site_id",
    "origin_a",
    "origin_b",
    "osm_id",
    "a_intersects_window",
    "a_selected_by_predicate",
    "a_closure_only",
    "b_intersects_window",
    "b_selected_by_predicate",
    "b_closure_only",
    "min_distance_m",
    "hausdorff_m",
    *(f"iou_{tau}" for tau in TAUS),
    *(f"cov_a_in_b_{tau}" for tau in TAUS),
    *(f"cov_b_in_a_{tau}" for tau in TAUS),
    "degenerate_flag",
)

PRESENCE_COLUMNS = (
    "site_id",
    "osm_id",
    "origin",
    "presence_in_acquired_corpus",
    "global_counterpart_status",
)


class UnbuildableGeometry(Exception):
    """A way that cannot become a `LineString`."""


@dataclass(frozen=True)
class Endpoint:
    """One way as observed for one site in one origin, with its §2.2 flags.

    Coordinates are lon/lat; the projection happens once per site, here, so no
    caller has to know which zone a site froze.
    """

    site_id: str
    origin: int
    osm_id: int
    coordinates: tuple[tuple[float, float], ...]
    intersects_window: bool
    selected_by_predicate: bool

    @property
    def closure_only(self) -> bool:
        return not (self.intersects_window and self.selected_by_predicate)


@dataclass(frozen=True)
class PresenceRow:
    """§6.3, keyed `(site_id, osm_id, origin)`.

    `global_counterpart_status` is deliberately distinct from
    `presence_in_acquired_corpus` and is always `UNKNOWN`.
    """

    site_id: str
    osm_id: int
    origin: int
    presence_in_acquired_corpus: bool
    global_counterpart_status: str = GLOBAL_COUNTERPART_STATUS

    def as_row(self) -> dict[str, object]:
        return {
            "site_id": self.site_id,
            "osm_id": self.osm_id,
            "origin": self.origin,
            "presence_in_acquired_corpus": self.presence_in_acquired_corpus,
            "global_counterpart_status": self.global_counterpart_status,
        }


@dataclass(frozen=True)
class EdgeMetrics:
    """§6.5's descriptive measurements.  No cutoff, no classification (§6.4)."""

    min_distance_m: float | None
    hausdorff_m: float | None
    iou: Mapping[int, float | None]
    cov_a_in_b: Mapping[int, float | None]
    cov_b_in_a: Mapping[int, float | None]
    degenerate_flag: bool


@dataclass(frozen=True)
class IdentityEdge:
    """One row per `(site_id, origin_pair, osm_id)`, origins canonically ordered.

    The six endpoint flags are carried per endpoint (round-6 #1).  Without them a
    consumer cannot tell an edge between two genuinely in-window ways from one
    whose far endpoint exists only as closure -- precisely the distinction Plan B
    needs.
    """

    site_id: str
    osm_id: int
    a: Endpoint
    b: Endpoint
    metrics: EdgeMetrics

    def as_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "site_id": self.site_id,
            "origin_a": self.a.origin,
            "origin_b": self.b.origin,
            "osm_id": self.osm_id,
            "a_intersects_window": self.a.intersects_window,
            "a_selected_by_predicate": self.a.selected_by_predicate,
            "a_closure_only": self.a.closure_only,
            "b_intersects_window": self.b.intersects_window,
            "b_selected_by_predicate": self.b.selected_by_predicate,
            "b_closure_only": self.b.closure_only,
            "min_distance_m": self.metrics.min_distance_m,
            "hausdorff_m": self.metrics.hausdorff_m,
        }
        for tau in TAUS:
            row[f"iou_{tau}"] = self.metrics.iou[tau]
        for tau in TAUS:
            row[f"cov_a_in_b_{tau}"] = self.metrics.cov_a_in_b[tau]
        for tau in TAUS:
            row[f"cov_b_in_a_{tau}"] = self.metrics.cov_b_in_a[tau]
        row["degenerate_flag"] = self.metrics.degenerate_flag
        return row


def build_geometry(coordinates: Sequence[tuple[float, float]]) -> LineString:
    """A way's `LineString`, or a refusal.

    A one-node way raises in GEOS rather than producing a degenerate geometry,
    and an empty `LineString` yields `nan` from every metric without raising, so
    neither is allowed to reach a measurement.
    """

    if len(coordinates) < 2:
        raise UnbuildableGeometry(
            f"a way needs at least two coordinates, got {len(coordinates)}"
        )
    return LineString(coordinates)


def buffer(line: LineString, tau: float):
    """The frozen buffer (§6.5): flat end cap, round join, 8 quadrant segments."""

    return line.buffer(
        tau,
        cap_style=BUFFER_CAP_STYLE,
        join_style=BUFFER_JOIN_STYLE,
        quad_segs=BUFFER_QUAD_SEGS,
    )


def _covered_length(line: LineString, other_buffer) -> float:
    return sum(part.length for part in lineal_parts(line.intersection(other_buffer)))


def edge_metrics(a_line: LineString | None, b_line: LineString | None) -> EdgeMetrics:
    """Measure one endpoint pair, both already in the site's frozen UTM.

    `None` means the geometry could not be built at all.  A zero-length geometry
    is degenerate: its flat-capped buffer is empty, so every buffer-derived
    metric would divide by zero.
    """

    unbuildable = a_line is None or b_line is None
    degenerate = unbuildable or a_line.length == 0.0 or b_line.length == 0.0

    if unbuildable:
        nulls = {tau: None for tau in TAUS}
        return EdgeMetrics(None, None, nulls, dict(nulls), dict(nulls), True)

    # No division anywhere in these two, and both are well-defined for a
    # zero-length way, so they are emitted even when the row is degenerate.
    min_distance = a_line.distance(b_line)
    hausdorff = max(
        shapely.hausdorff_distance(a_line, b_line),
        shapely.hausdorff_distance(b_line, a_line),
    )

    if degenerate:
        nulls = {tau: None for tau in TAUS}
        return EdgeMetrics(min_distance, hausdorff, nulls, dict(nulls), dict(nulls), True)

    iou: dict[int, float | None] = {}
    cov_a_in_b: dict[int, float | None] = {}
    cov_b_in_a: dict[int, float | None] = {}
    for tau in TAUS:
        a_buffer, b_buffer = buffer(a_line, tau), buffer(b_line, tau)
        union = a_buffer.union(b_buffer).area
        iou[tau] = a_buffer.intersection(b_buffer).area / union if union else None
        cov_a_in_b[tau] = _covered_length(a_line, b_buffer) / a_line.length
        cov_b_in_a[tau] = _covered_length(b_line, a_buffer) / b_line.length

    return EdgeMetrics(min_distance, hausdorff, iou, cov_a_in_b, cov_b_in_a, False)


def build_presence_table(
    endpoints: Iterable[Endpoint], *, origins: Sequence[int]
) -> tuple[PresenceRow, ...]:
    """§6.3.  One row per `(site_id, osm_id, origin)` over **every** corpus origin.

    Absence is the fact this table exists to carry, so `origins` is required
    rather than inferred: an origin with no rows for a site would otherwise be
    indistinguishable from an origin that was never acquired.
    """

    if not origins:
        raise ValueError("the corpus origins must be given; absence cannot be inferred")

    observed: set[tuple[str, int, int]] = set()
    pairs: set[tuple[str, int]] = set()
    for endpoint in endpoints:
        observed.add((endpoint.site_id, endpoint.osm_id, endpoint.origin))
        pairs.add((endpoint.site_id, endpoint.osm_id))

    return tuple(
        PresenceRow(
            site_id=site_id,
            osm_id=osm_id,
            origin=origin,
            presence_in_acquired_corpus=(site_id, osm_id, origin) in observed,
        )
        for site_id, osm_id in sorted(pairs)
        for origin in sorted(origins)
    )


def build_identity_edges(
    endpoints: Iterable[Endpoint], windows: Mapping[str, SiteWindow]
) -> tuple[IdentityEdge, ...]:
    """§6.1.  Link ways sharing an `osm_id` across origins, at any separation.

    Only present endpoints are paired.  Distance never enters the decision --
    pass 2 retained out-of-window counterparts specifically so these edges can
    exist, and a radius would delete the very cases they are for.
    """

    grouped: dict[tuple[str, int], list[Endpoint]] = {}
    for endpoint in endpoints:
        grouped.setdefault((endpoint.site_id, endpoint.osm_id), []).append(endpoint)

    edges: list[IdentityEdge] = []
    for (site_id, osm_id), members in sorted(grouped.items()):
        window = windows[site_id]
        by_origin = {member.origin: member for member in members}
        if len(by_origin) != len(members):
            raise ValueError(
                f"{site_id}/{osm_id}: more than one endpoint per origin -- "
                "dedup (§4) must run before lineage"
            )

        projected: dict[int, LineString | None] = {}
        for origin, member in by_origin.items():
            try:
                projected[origin] = window.to_utm(build_geometry(member.coordinates))
            except UnbuildableGeometry:
                projected[origin] = None

        ordered = sorted(by_origin)
        for i, origin_a in enumerate(ordered):
            for origin_b in ordered[i + 1 :]:
                edges.append(
                    IdentityEdge(
                        site_id=site_id,
                        osm_id=osm_id,
                        a=by_origin[origin_a],
                        b=by_origin[origin_b],
                        metrics=edge_metrics(projected[origin_a], projected[origin_b]),
                    )
                )
    return tuple(edges)
