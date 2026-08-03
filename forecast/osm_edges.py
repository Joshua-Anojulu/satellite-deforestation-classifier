"""§6 identity edges and presence table — Plan A's deliverable to Plan B.

Implements the driver for §6 of `OSM-NORMALISATION-PLAN.md`, over artifacts §4
has already published and validated.

**Endpoints are built from §4's membership table joined to deduplicated
geometry, not from raw region parts.** `build_identity_edges` refuses more than
one endpoint per origin for a `(site, osm_id)` and says why: *"dedup (§4) must
run before lineage"*. The corpus has **34 duplicate groups** -- ways appearing in
two regions of one origin at a Geofabrik border -- so feeding it raw parts would
raise on real data. The membership table is the structure that collapses those
onto `(site_id, origin, osm_type, osm_id)` **and reports disagreement rather
than merging it**, which is exactly the join §6 needs.

**Geometry comes from two places, and closure-only ways are why.** §4's
deduplicated origin datasets carry every way pass 1 dispatched; they do **not**
carry the counterparts pass 2 recovered, because those were never in a window
and so were never dispatched. Those live in the committed pass-2 closure
records. A way that moved 8 km between origins is measurable only from its new
coordinates, and that way is precisely what §6.1 promises to link.

**Absence is emitted, never inferred** (§6.3, round-9 #5). The presence table is
built over **every** corpus origin explicitly, so an origin where a way is absent
is distinguishable from an origin that was never acquired.
`global_counterpart_status` stays `UNKNOWN` throughout: absence from the acquired
corpus is not absence from OSM, and Plan A acquires no globally covering
snapshot that could say otherwise.

**Edges are built only between present endpoints** (§6.3). A missing counterpart
is represented by the presence table, never by a half-populated edge row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from forecast.content_store import ContentStore
from forecast.manifests import Manifest, SHARD, publish_manifest
from forecast.osm_dedupe import MembershipRow, build_membership_table
from forecast.osm_lineage import (
    EDGE_COLUMNS,
    Endpoint,
    IdentityEdge,
    PresenceRow,
    build_identity_edges,
    build_presence_table,
)
from forecast.osm_preflight import _checkpoint_documents, load_site_records
from forecast.osm_windows import SiteWindow


class LineageInputMissing(Exception):
    """§6 cannot run before §4 has published what it reads."""


def load_geometry(
    store: ContentStore,
    checkpoints: ContentStore,
    origin_manifests: Mapping[int, str],
) -> dict[tuple[int, int], tuple[tuple[float, float], ...]]:
    """Coordinates keyed `(origin, osm_id)`, from §4's output plus pass-2 records.

    §4's datasets are preferred where both have a way: those coordinates have
    been through the duplicate-group preflight, and the pass-2 copy has not.
    """

    geometry: dict[tuple[int, int], tuple[tuple[float, float], ...]] = {}

    # Closure-only counterparts first, so §4's validated geometry overwrites any
    # way present in both rather than the other way round.
    for document in _checkpoint_documents(checkpoints, "pass2."):
        origin = int(document["origin"])
        for part in document["parts"]:
            payload = json.loads(store.read_validated(part["digest"]))
            for row in payload["records"]:
                coordinates = row.get("coordinates")
                if not coordinates:
                    continue
                geometry[(origin, row["osm_id"])] = tuple(tuple(c) for c in coordinates)

    for origin, manifest_digest in origin_manifests.items():
        manifest = json.loads(store.read_validated(manifest_digest))
        for child in manifest["children"]:
            payload = json.loads(store.read_validated(child))
            for way in payload["ways"]:
                geometry[(origin, way["osm_id"])] = tuple(
                    tuple(c) for c in way["coordinates"]
                )

    if not geometry:
        raise LineageInputMissing(
            "no geometry available; §6 runs after §4 has published origin datasets"
        )
    return geometry


def build_endpoints(
    membership: Sequence[MembershipRow],
    geometry: Mapping[tuple[int, int], tuple[tuple[float, float], ...]],
) -> tuple[tuple[Endpoint, ...], tuple[MembershipRow, ...]]:
    """Join membership flags to geometry.

    Returns the endpoints and, separately, the membership rows for which **no
    geometry exists**. Those are not silently dropped: a row whose way cannot be
    located is a gap in the join, and Plan B needs to know the difference between
    "absent from this origin" and "present but unlocatable".
    """

    endpoints: list[Endpoint] = []
    orphaned: list[MembershipRow] = []

    for row in membership:
        coordinates = geometry.get((row.key[1], row.key[3]))
        if coordinates is None:
            orphaned.append(row)
            continue
        endpoints.append(
            Endpoint(
                site_id=row.key.site_id,
                origin=row.key[1],
                osm_id=row.key[3],
                coordinates=coordinates,
                intersects_window=row.intersects_window,
                selected_by_predicate=row.selected_by_predicate,
            )
        )
    return tuple(endpoints), tuple(orphaned)


def _edges_payload(edges: Sequence[IdentityEdge]) -> bytes:
    return (
        json.dumps(
            {"columns": list(EDGE_COLUMNS), "rows": [e.as_row() for e in edges]},
            indent=None,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _presence_payload(rows: Sequence[PresenceRow]) -> bytes:
    return (
        json.dumps(
            {"rows": [r.as_row() for r in rows]},
            indent=None,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class LineageOutcome:
    """§6's two artifacts, and what went into them."""

    edges_digest: str
    presence_digest: str
    edges_manifest: str
    presence_manifest: str
    edges: int
    presence_rows: int
    endpoints: int
    degenerate_edges: int
    closure_only_endpoints: int
    orphaned_membership_rows: int
    origins: tuple[int, ...]


def run_lineage(
    store: ContentStore,
    checkpoints: ContentStore,
    origin_manifests: Mapping[int, str],
    windows: Mapping[str, SiteWindow],
    *,
    origins: Sequence[int],
    cache_key: str = "pass-1",
) -> LineageOutcome:
    """Emit §6.1's identity edges and §6.3's presence table, and publish both."""

    if not origins:
        raise ValueError("the corpus origins must be given; absence cannot be inferred")

    site_records = load_site_records(store, checkpoints)
    membership, conflicts = build_membership_table(site_records)
    if conflicts:
        raise LineageInputMissing(
            f"{len(conflicts)} membership conflicts; §4 must be clean before §6 runs"
        )

    geometry = load_geometry(store, checkpoints, origin_manifests)
    endpoints, orphaned = build_endpoints(membership, geometry)

    edges = build_identity_edges(endpoints, windows)
    presence = build_presence_table(endpoints, origins=origins)

    edges_digest = store.publish_content_object(_edges_payload(edges)).digest
    presence_digest = store.publish_content_object(_presence_payload(presence)).digest

    edges_manifest = publish_manifest(
        store,
        Manifest(
            SHARD, "identity-edges", (edges_digest,),
            schema_digest=",".join(EDGE_COLUMNS),
            cache_key=cache_key,
            bindings={"edges": len(edges), "origins": list(origins)},
        ),
    )
    presence_manifest = publish_manifest(
        store,
        Manifest(
            SHARD, "presence-table", (presence_digest,),
            schema_digest="site_id,osm_id,origin,presence_in_acquired_corpus,global_counterpart_status",
            cache_key=cache_key,
            bindings={"rows": len(presence), "origins": list(origins)},
        ),
    )

    return LineageOutcome(
        edges_digest=edges_digest,
        presence_digest=presence_digest,
        edges_manifest=edges_manifest,
        presence_manifest=presence_manifest,
        edges=len(edges),
        presence_rows=len(presence),
        endpoints=len(endpoints),
        degenerate_edges=sum(1 for e in edges if e.metrics.degenerate_flag),
        closure_only_endpoints=sum(1 for e in endpoints if e.closure_only),
        orphaned_membership_rows=len(orphaned),
        origins=tuple(sorted(origins)),
    )
