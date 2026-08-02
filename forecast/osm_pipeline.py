"""The production path: parser to committed region, and the §3 evidence artifact.

Implements the pass-1 production path §3 gates and §5 publishes.

**This module exists because §3 cannot be satisfied without it.** The gate's
measurements were taken by a benchmark harness that decoded nodes, built the
index, applied the retain predicate and validated locations -- and did **not**
build `LineString`s, intersect masks, dispatch, serialise, hash or publish
(round-4 #3). 22.5 minutes therefore bounds the parser from below and says
nothing about the stage. `ProductionPathEvidence` is what closes that gap, and
only a run through *this* path can produce one.

**Per-file, never per-corpus** (round-4 #4). `flex_mem` switches between sparse
and dense representations by node cardinality and node-ID density, and neither
is ordered by compressed PBF bytes -- so every file is measured and the worst
observation decides. `node_cardinality` and `max_node_id` are recorded because
they are the actual drivers of index size.

**The commit-charge trace is sampled from the working process** (§3.1), and the
peak is what the gate scores. Working set is recorded for §10.2's journal and is
never a gate: it counts resident pages, so a run that begins swapping reports a
*lower* number (round-6 #6).

**Every artifact is published through §5's store before the region manifest
names it**, so a kill at any point leaves either a complete committed region or
no region at all -- never a manifest pointing at bytes that were not written.

**The restart boundary is the whole input file** (§10.1). pyosmium exposes no
durable input cursor, so a kill mid-file forces a full re-parse of that file.
This driver therefore commits at the file boundary and records
`wall_clock_s` per file, which is the **maximum committed-region duration**
§10.1 defers its restart decision to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from forecast.content_store import ContentStore, digest_of
from forecast.entry_gate import FileCounters, ProductionPathEvidence, evaluate_gate
from forecast.generations import DatasetIdentity, GenerationStore
from forecast.manifests import (
    ORIGIN_DATASET,
    REGION,
    SHARD,
    STAGE,
    Manifest,
    publish_manifest,
)
from forecast.osm_lineage import UnbuildableGeometry, build_geometry
from forecast.osm_stream import InvalidWayGeometry, stream_retained_ways
from forecast.osm_windows import SiteWindow, WindowDispatch, build_site_windows
from forecast.process_memory import MemorySample, process_memory

#: Bound into every manifest this path writes; a cached artifact built under a
#: different row schema must not validate (§8.1).
SCHEMA_DIGEST = hashlib.sha256(
    b"site_id,osm_id,version,timestamp,tags,node_refs,coordinates,is_closed"
).hexdigest()

#: Ways per part file.  A part is the unit that is hashed and published, so this
#: bounds peak serialisation memory rather than being a tuning knob.
WAYS_PER_PART = 50_000

#: The modules whose bytes change what this path produces (§8.2).  Scoped
#: deliberately: hashing all uncommitted content would invalidate the cache on an
#: unrelated docs edit (round-2 #13).
PARSER_SOURCE_MODULES = (
    "forecast/osm_stream.py",
    "forecast/osm_normalise.py",
    "forecast/osm_windows.py",
    "forecast/osm_pipeline.py",
)

#: Recorded in the evidence artifact so a cached result built against different
#: libraries cannot validate (§8.1).
TRACKED_DEPENDENCIES = ("osmium", "shapely", "pyproj", "pyarrow", "geopandas")


class ProductionPathError(Exception):
    """The path failed. Nothing is published for the affected file."""


@dataclass
class ResourceTrace:
    """Peak commit and working set observed while a file was processed.

    Sampled rather than computed: the gate is on measured commit charge, and a
    figure derived from what we *think* we allocated would make the gate score
    an assumption.
    """

    peak_commit_bytes: int = 0
    peak_working_set_bytes: int = 0
    samples: int = 0

    def sample(self) -> MemorySample:
        reading = process_memory()
        self.peak_commit_bytes = max(self.peak_commit_bytes, reading.commit_bytes)
        self.peak_working_set_bytes = max(
            self.peak_working_set_bytes, reading.peak_working_set_bytes
        )
        self.samples += 1
        return reading


@dataclass(frozen=True)
class PartFile:
    """One committed part.  A region manifest may name several (§5.5)."""

    digest: str
    ways: int
    site_ids: tuple[str, ...]


@dataclass(frozen=True)
class FileOutcome:
    """What one input file produced, and what it cost."""

    name: str
    path: str
    origin: str
    region: str
    counters: FileCounters
    region_manifest: str
    parts: tuple[PartFile, ...]
    input_digest: str

    @property
    def ways(self) -> int:
        return self.counters.retained_ways


def origin_and_region(path: Path) -> tuple[str, str]:
    """`norte-220101.osm.pbf` -> origin `2022`, region `norte`.

    The origin is the archive year, which is what §2.2 keys identity closure on.
    """

    stem = path.name
    for suffix in (".osm.pbf", ".pbf"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    region, _, stamp = stem.rpartition("-")
    if not region or len(stamp) != 6 or not stamp.isdigit():
        raise ProductionPathError(
            f"cannot read region and origin from {path.name!r}; expected "
            "<region>-<YYMMDD>.osm.pbf"
        )
    return f"20{stamp[:2]}", region


def file_digest(path: Path, *, chunk: int = 8 * 1024 * 1024) -> str:
    """Hash an input extract. Streamed -- these are hundreds of megabytes."""

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            hasher.update(block)
    return hasher.hexdigest()


def parser_source_digest(repo_root: Path) -> str:
    """One digest over the sources that decide what this path emits (§8.2)."""

    hasher = hashlib.sha256()
    for relative in PARSER_SOURCE_MODULES:
        source = (repo_root / relative).read_bytes()
        hasher.update(relative.encode("utf-8"))
        hasher.update(hashlib.sha256(source).digest())
    return hasher.hexdigest()


def dependency_versions() -> dict[str, str]:
    """Resolved versions, recorded rather than assumed (§8.1)."""

    import importlib.metadata as metadata

    versions = {"python": platform.python_version()}
    for name in TRACKED_DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "absent"
    return versions


def _part_payload(
    origin: str,
    region: str,
    rows: Sequence[tuple[str, object]],
) -> bytes:
    """Serialise a part deterministically.

    Byte-determinism is load-bearing: the part's digest is its identity in the
    store, so two identical builds must produce one object rather than two.
    """

    document = {
        "origin": origin,
        "region": region,
        "rows": [
            {
                "site_id": site_id,
                "osm_id": way.osm_id,
                "version": way.version,
                "timestamp": way.timestamp,
                "tags": dict(sorted(way.tags.items())),
                "node_refs": list(way.node_refs),
                "coordinates": [list(c) for c in way.coordinates],
                "is_closed": way.is_closed,
            }
            for site_id, way in rows
        ],
    }
    return (
        json.dumps(document, indent=None, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def run_pass_one_file(
    path: str | Path,
    windows: Sequence[SiteWindow],
    store: ContentStore,
    *,
    sample_every: int = 20_000,
    ways_per_part: int = WAYS_PER_PART,
    progress: bool = False,
) -> FileOutcome:
    """Stream one extract through the full path and commit its region.

    This is the production path §3's evidence must be produced by: it decodes
    nodes, builds the index, applies the retain predicate, validates every node
    location, **builds geometry, intersects masks, dispatches, serialises,
    hashes and publishes** -- the six stages the benchmark harness skipped.
    """

    path = Path(path)
    origin, region = origin_and_region(path)
    dispatch = WindowDispatch(tuple(windows))
    trace = ResourceTrace()
    trace.sample()

    retained = 0
    with_geometry = 0
    unbuildable = 0
    max_node_id = 0
    node_cardinality = 0
    parts: list[PartFile] = []
    buffer: list[tuple[str, object]] = []
    buffered_sites: set[str] = set()

    started = time.perf_counter()

    def flush() -> None:
        nonlocal buffer, buffered_sites
        if not buffer:
            return
        payload = _part_payload(origin, region, buffer)
        result = store.publish_content_object(payload)
        if not result.committed:
            raise ProductionPathError(
                f"part of {path.name} did not commit: {result.outcome}"
            )
        parts.append(
            PartFile(result.digest, len(buffer), tuple(sorted(buffered_sites)))
        )
        buffer = []
        buffered_sites = set()

    try:
        stream = stream_retained_ways(str(path))
        for way in stream:
            retained += 1
            node_cardinality += len(way.node_refs)
            if way.node_refs:
                max_node_id = max(max_node_id, max(way.node_refs))

            # Building the LineString is one of the six stages the §3 benchmark
            # harness skipped, so it happens here rather than downstream.  Node
            # locations are already resolved -- build_retained_way raises rather
            # than emitting a way with a missing one -- but a single-node way
            # resolves fine and still cannot form a line, which is a different
            # failure and is counted separately.
            try:
                geometry = build_geometry(way.coordinates)
            except UnbuildableGeometry:
                unbuildable += 1
                continue
            with_geometry += 1

            for site_id in dispatch.sites_touching(geometry):
                buffer.append((site_id, way))
                buffered_sites.add(site_id)

            if len(buffer) >= ways_per_part:
                flush()
            if retained % sample_every == 0:
                trace.sample()
                if progress:
                    elapsed = time.perf_counter() - started
                    print(
                        f"  {path.name}: {retained:,} ways, {elapsed:,.0f}s, "
                        f"commit {trace.peak_commit_bytes / 1024**3:.2f} GB",
                        flush=True,
                    )
    except InvalidWayGeometry as exc:
        # §1.5: a way with an unresolved node location fails the stage closed.
        # Nothing published for this file is named by a region manifest, so the
        # partial parts are unreachable garbage rather than a partial region.
        raise ProductionPathError(
            f"{path.name} failed closed on an invalid node location: {exc}"
        ) from exc

    flush()
    trace.sample()
    wall_clock = time.perf_counter() - started

    shard_digests = [
        publish_manifest(
            store,
            Manifest(
                SHARD,
                f"{region}-{origin}-{index:05d}",
                (part.digest,),
                schema_digest=SCHEMA_DIGEST,
                cache_key="pass-1",
                bindings={"ways": part.ways, "site_ids": list(part.site_ids)},
            ),
        )
        for index, part in enumerate(parts)
    ]
    region_manifest = publish_manifest(
        store,
        Manifest(
            REGION,
            f"{region}-{origin}",
            tuple(shard_digests),
            schema_digest=SCHEMA_DIGEST,
            cache_key="pass-1",
            bindings={"origin": origin, "region": region, "retained_ways": retained},
        ),
    )

    counters = FileCounters(
        name=path.stem,
        node_cardinality=node_cardinality,
        max_node_id=max_node_id,
        retained_ways=retained,
        ways_with_complete_geometry=with_geometry,
        invalid_node_locations=0,  # a nonzero value fails closed above, never reaches here
        wall_clock_s=wall_clock,
        peak_commit_bytes=trace.peak_commit_bytes,
        peak_working_set_bytes=trace.peak_working_set_bytes,
    )
    return FileOutcome(
        name=path.stem,
        path=str(path),
        origin=origin,
        region=region,
        counters=counters,
        region_manifest=region_manifest,
        parts=tuple(parts),
        input_digest=file_digest(path),
    )


def build_evidence(
    outcomes: Sequence[FileOutcome],
    *,
    repo_root: Path,
    command: Sequence[str],
    stage_digest: str,
) -> ProductionPathEvidence:
    """The immutable artifact §3 refuses to authorise a corpus run without.

    Nothing here is optional: a partial artifact would let a corpus run be
    authorised by evidence that cannot be reproduced or attributed.
    """

    return ProductionPathEvidence(
        parser_source_sha256=parser_source_digest(repo_root),
        command=tuple(command),
        input_digests={o.name: o.input_digest for o in outcomes},
        dependency_versions=dependency_versions(),
        output_digests={
            **{f"region:{o.region}-{o.origin}": o.region_manifest for o in outcomes},
            "stage": stage_digest,
        },
        covers_full_production_path=True,
    )


def load_sites(manifest_path: str | Path) -> tuple[dict, ...]:
    """The Specification W site records the windows are built from."""

    document = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for value in document.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            if {"candidate_id", "west", "east", "south", "north"} <= set(value[0]):
                return tuple(value)
    raise ProductionPathError(f"no site records in {manifest_path}")


def run(
    paths: Sequence[str | Path],
    *,
    sites: Sequence[Mapping[str, object]],
    store_root: str | Path,
    repo_root: Path,
    command: Sequence[str],
    progress: bool = False,
) -> dict[str, object]:
    """Run the production path over `paths` and publish one generation.

    Returns the gate report alongside the evidence, because the two are only
    meaningful together: the measurements are a floor, and the evidence is what
    makes them an authorisation (§3).
    """

    windows = build_site_windows(sites)
    generations = GenerationStore(store_root)
    store = generations.store

    outcomes: list[FileOutcome] = []
    lease = generations.shared_lease()
    try:
        for path in paths:
            if progress:
                print(f"[{len(outcomes) + 1}/{len(paths)}] {Path(path).name}", flush=True)
            outcomes.append(
                run_pass_one_file(path, windows, store, progress=progress)
            )

        by_origin: dict[str, list[str]] = {}
        for outcome in outcomes:
            by_origin.setdefault(outcome.origin, []).append(outcome.region_manifest)

        origin_digests = [
            publish_manifest(
                store,
                Manifest(
                    ORIGIN_DATASET,
                    origin,
                    tuple(sorted(regions)),
                    schema_digest=SCHEMA_DIGEST,
                    cache_key="pass-1",
                    bindings={"origin": origin, "regions": len(regions)},
                ),
            )
            for origin, regions in sorted(by_origin.items())
        ]

        stage_digest = publish_manifest(
            store,
            Manifest(
                STAGE,
                "osm-normalisation-pass-1",
                tuple(origin_digests),
                schema_digest=SCHEMA_DIGEST,
                cache_key="pass-1",
                bindings={
                    "origin_datasets": sorted(by_origin),
                    # Pass 1 publishes no lineage; the bindings are present and
                    # explicitly null rather than absent, so a consumer can tell
                    # "not built yet" from "built and empty" (§5.1).
                    "identity_edges": None,
                    "presence_table": None,
                    "duplicate_group_preflight": None,
                    "coverage_margins": {
                        w.site_id: w.max_processing_radius_m for w in windows
                    },
                },
            ),
        )

        identity = DatasetIdentity(
            dataset="osm-normalisation-pass-1",
            schema_digest=SCHEMA_DIGEST,
            cache_key="pass-1",
        )
        token = generations.state_token(identity)
        record = generations.publish_generation(
            stage_digest, identity, token, lease=lease
        )
    finally:
        lease.release()

    evidence = build_evidence(
        outcomes, repo_root=repo_root, command=command, stage_digest=stage_digest
    )
    report = evaluate_gate([o.counters for o in outcomes], evidence=evidence)

    return {
        "generation": record.number,
        "stage": stage_digest,
        "outcomes": outcomes,
        "evidence": evidence,
        "report": report,
    }


def _evidence_document(evidence: ProductionPathEvidence) -> dict[str, object]:
    return {
        "parser_source_sha256": evidence.parser_source_sha256,
        "command": list(evidence.command),
        "input_digests": dict(evidence.input_digests),
        "dependency_versions": dict(evidence.dependency_versions),
        "output_digests": dict(evidence.output_digests),
        "covers_full_production_path": evidence.covers_full_production_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm-dir", required=True, help="directory of .osm.pbf extracts")
    parser.add_argument("--store", required=True, help="publication store root (local NTFS)")
    parser.add_argument(
        "--sites",
        default="forecast/artifacts/specification_w_manifest.json",
        help="Specification W manifest the site windows come from",
    )
    parser.add_argument(
        "--files", nargs="*", default=None, help="specific extract names; default all 36"
    )
    parser.add_argument("--limit", type=int, default=None, help="process at most N files")
    parser.add_argument(
        "--evidence-out",
        default=None,
        help="write the §3 production-path evidence artifact here",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    osm_dir = Path(args.osm_dir)
    extracts = sorted(osm_dir.glob("*.osm.pbf"))
    if args.files:
        wanted = set(args.files)
        extracts = [p for p in extracts if p.name in wanted or p.stem in wanted]
        missing = wanted - {p.name for p in extracts} - {p.stem for p in extracts}
        if missing:
            raise SystemExit(f"no such extract(s): {sorted(missing)}")
    if args.limit is not None:
        extracts = extracts[: args.limit]
    if not extracts:
        raise SystemExit(f"no .osm.pbf extracts under {osm_dir}")

    repo_root = Path(__file__).resolve().parents[1]
    sites = load_sites(args.sites)

    result = run(
        extracts,
        sites=sites,
        store_root=args.store,
        repo_root=repo_root,
        command=("python", "-m", "forecast.osm_pipeline", *argv),
        progress=not args.quiet,
    )

    report = result["report"]
    print()
    print(report.describe())
    print()
    print(f"generation {result['generation']} published; stage {result['stage'][:16]}...")
    print(f"authorises_corpus_run = {report.authorises_corpus_run}")

    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(
                {
                    "evidence": _evidence_document(result["evidence"]),
                    "files": [
                        {
                            "name": o.name,
                            "origin": o.origin,
                            "region": o.region,
                            "retained_ways": o.counters.retained_ways,
                            "node_cardinality": o.counters.node_cardinality,
                            "max_node_id": o.counters.max_node_id,
                            "geometry_availability": o.counters.geometry_availability,
                            "invalid_node_locations": o.counters.invalid_node_locations,
                            "wall_clock_s": o.counters.wall_clock_s,
                            "peak_commit_bytes": o.counters.peak_commit_bytes,
                            "peak_working_set_bytes": o.counters.peak_working_set_bytes,
                            "parts": len(o.parts),
                            "region_manifest": o.region_manifest,
                        }
                        for o in result["outcomes"]
                    ],
                    "generation": result["generation"],
                    "authorises_corpus_run": report.authorises_corpus_run,
                    "not_assessed": [c.name for c in report.not_assessed],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"evidence written to {args.evidence_out}")

    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
