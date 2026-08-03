"""§4 duplicate-group preflight and origin publication, from committed checkpoints.

Implements the driver for §4 of `OSM-NORMALISATION-PLAN.md`, at step 4 of §4.6's
ordering -- which is only reachable now that §3's gate authorises the corpus run.

**This reads committed parts, never a PBF** (§4.6, round-5 #3). v5 called the
coordinate preflight cheap because coordinates are "already retained per §1.3";
they are retained only *after* the node index and parser have produced region
records, so running it before the corpus run would have required its own full
node-and-way pass -- the opposite of cheap. Running it here, over parts that are
already committed and content-addressed, is what makes it genuinely cheap.

**A dirty preflight blocks publication, and this is the gate that makes that
true** rather than a sentence in a document: :func:`deduplicate` refuses a dirty
report, so no origin dataset can be published over unresolved conflicts.

**The 2020 origin carries `ABSENT` as its header timestamp** (owner ruling,
2026-08-02). §7's authoritative field is empty in all twelve 2020 extracts, and
§4.3 requires the region header timestamp in every conflict report. Rather than
substitute a filename date, the absence is carried through and reported as
absence -- a conflict between two 2020 regions says plainly that neither side
can be dated, which is more useful than two identical invented timestamps that
look like corroboration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from forecast.content_store import ContentStore
from forecast.manifests import ORIGIN_DATASET, Manifest, publish_manifest
from forecast.osm_closure import RecordKey, SiteRecord
from forecast.osm_dedupe import (
    DirtyPreflight,
    OriginWay,
    PreflightReport,
    RegionWay,
    deduplicate,
    preflight,
)
from forecast.osm_provenance import ABSENT, ProvenanceSurvey
from forecast.osm_stream import RetainedWay


class CheckpointsMissing(Exception):
    """§4 cannot run before pass 1 has committed the regions it reads."""


def _checkpoint_documents(checkpoints: ContentStore, prefix: str) -> list[dict]:
    documents = []
    for path in sorted(checkpoints.root.iterdir()):
        if path.name.startswith(prefix) and path.name.endswith(".json"):
            documents.append(json.loads(path.read_bytes()))
    return documents


def load_region_ways(
    store: ContentStore,
    checkpoints: ContentStore,
    provenance: ProvenanceSurvey,
) -> tuple[RegionWay, ...]:
    """Rebuild §4's input from committed pass-1 parts.

    Every part is read back through :meth:`ContentStore.read_validated`, so the
    bytes §4 reasons about are rehashed at the moment they are used rather than
    trusted from when they were written.
    """

    documents = _checkpoint_documents(checkpoints, "pass1.")
    if not documents:
        raise CheckpointsMissing(
            "no committed pass-1 region checkpoints; §4.6 puts preflight after "
            "parsing, so there is nothing for it to read"
        )

    records: list[RegionWay] = []
    for document in documents:
        origin = int(document["origin"])
        region = document["region"]
        try:
            header_timestamp = provenance.origin_timestamp(document["origin"])
        except KeyError:
            header_timestamp = ABSENT

        for part in document["parts"]:
            payload = json.loads(store.read_validated(part["digest"]))
            for row in payload["rows"]:
                records.append(
                    RegionWay(
                        origin=origin,
                        source_region=region,
                        region_header_timestamp=header_timestamp,
                        way=RetainedWay(
                            osm_id=row["osm_id"],
                            version=row["version"],
                            timestamp=row["timestamp"],
                            tags=dict(row["tags"]),
                            node_refs=tuple(row["node_refs"]),
                            coordinates=tuple(tuple(c) for c in row["coordinates"]),
                            is_closed=row["is_closed"],
                        ),
                    )
                )
    return tuple(records)


def load_site_records(
    store: ContentStore, checkpoints: ContentStore
) -> tuple[SiteRecord, ...]:
    """Every per-site record both passes committed (§4.1's membership input).

    Pass 1's rows are in-window and predicate-selected by construction; pass 2's
    carry their own flags, including the closure-only cases pass 1 could not see.
    """

    records: list[SiteRecord] = []

    for document in _checkpoint_documents(checkpoints, "pass1."):
        origin = int(document["origin"])
        region = document["region"]
        for part in document["parts"]:
            payload = json.loads(store.read_validated(part["digest"]))
            for row in payload["rows"]:
                records.append(
                    SiteRecord(
                        key=RecordKey(row["site_id"], origin, region, row["osm_id"]),
                        intersects_window=True,
                        selected_by_predicate=True,
                    )
                )

    for document in _checkpoint_documents(checkpoints, "pass2."):
        origin = int(document["origin"])
        region = document["region"]
        for part in document["parts"]:
            payload = json.loads(store.read_validated(part["digest"]))
            for row in payload["records"]:
                records.append(
                    SiteRecord(
                        key=RecordKey(row["site_id"], origin, region, row["osm_id"]),
                        intersects_window=row["intersects_window"],
                        selected_by_predicate=row["selected_by_predicate"],
                    )
                )

    return tuple(records)


def _origin_payload(origin: int, ways: Sequence[OriginWay]) -> bytes:
    document = {
        "origin": origin,
        "ways": [
            {
                "osm_id": w.osm_id,
                "osm_type": w.osm_type,
                "version": w.version,
                "timestamp": w.timestamp,
                "tags": dict(sorted(w.tags.items())),
                "node_refs": list(w.node_refs),
                "coordinates": [list(c) for c in w.coordinates],
                "is_closed": w.is_closed,
                "source_regions": list(w.source_regions),
            }
            for w in ways
        ],
    }
    return (
        json.dumps(document, indent=None, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


#: The origin-dataset row schema, distinct from a region part's.
ORIGIN_SCHEMA = (
    "osm_id,osm_type,version,timestamp,tags,node_refs,coordinates,is_closed,source_regions"
)


@dataclass(frozen=True)
class PreflightOutcome:
    """What §4 found, and what it published if it was allowed to."""

    report: PreflightReport
    origin_manifests: Mapping[int, str]
    origin_ways: Mapping[int, int]
    region_records: int
    site_records: int

    @property
    def published(self) -> bool:
        return bool(self.origin_manifests)


def run_preflight(
    store: ContentStore,
    checkpoints: ContentStore,
    provenance: ProvenanceSurvey,
    *,
    publish: bool = True,
    schema_digest: str = "",
    cache_key: str = "pass-1",
) -> PreflightOutcome:
    """Run §4 over the committed corpus, and publish only if it is clean.

    Returns the report either way. A dirty report is not an exception here --
    §4 collects every conflict rather than stopping at the first, and the
    caller needs all of them -- but it does stop publication.
    """

    records = load_region_ways(store, checkpoints, provenance)
    site_records = load_site_records(store, checkpoints)
    report = preflight(records, site_records=site_records)

    manifests: dict[int, str] = {}
    counts: dict[int, int] = {}
    if publish:
        try:
            deduplicated = deduplicate(records, report)
        except DirtyPreflight:
            # §4.6: a dirty preflight blocks publication. The report is still
            # returned, because the conflicts are the useful output.
            return PreflightOutcome(
                report=report,
                origin_manifests={},
                origin_ways={},
                region_records=len(records),
                site_records=len(site_records),
            )

        by_origin: dict[int, list[OriginWay]] = {}
        for way in deduplicated:
            by_origin.setdefault(way.origin, []).append(way)

        for origin, ways in sorted(by_origin.items()):
            ordered = sorted(ways, key=lambda w: (w.osm_type, w.osm_id))
            digest = store.publish_content_object(_origin_payload(origin, ordered)).digest
            manifests[origin] = publish_manifest(
                store,
                Manifest(
                    ORIGIN_DATASET,
                    f"deduplicated-{origin}",
                    (digest,),
                    schema_digest=schema_digest or ORIGIN_SCHEMA,
                    cache_key=cache_key,
                    bindings={
                        "origin": origin,
                        "ways": len(ordered),
                        "header_timestamp": provenance.origin_timestamp(str(origin)),
                    },
                ),
            )
            counts[origin] = len(ordered)

    return PreflightOutcome(
        report=report,
        origin_manifests=manifests,
        origin_ways=counts,
        region_records=len(records),
        site_records=len(site_records),
    )
