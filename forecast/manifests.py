"""The §5.1 hash-linked DAG, and §5.3's validation in both directions.

Implements §5.1 and §5.3 of `OSM-NORMALISATION-PLAN.md`.

**No node is reachable until its children validate** (round-3 #5).  v3 named a
manifest hierarchy but bound none of its edges, so the "hierarchy" carried no
integrity claim at all -- a parent could name a child that had never been
written.  Here a parent is constructed only after every child's recorded digest
is **recomputed from the store and matched**, which is what makes the edge mean
something.

**The stage manifest binds all three origin datasets, the lineage artifacts, the
preflight report and the coverage margins** (§5.1).  v3 bound only regions, so a
consumer could read a stage that had no lineage and not be able to tell.

**Validation runs bottom-up on write and top-down on read** (round-10 #6,
round-13 #13).  Write-side validation alone cannot protect a consumer across a
reboot: NTFS may persist namespace changes out of order under power loss, so a
generation record can survive while a child manifest does not.  A generation that
validated at publication time can therefore reference an incomplete DAG
afterwards -- so **every dereference revalidates the complete DAG**, and a
consumer that cannot validate gets a structured error, never a partial read.

**Traversal is bounded, not merely finite** (round-14 #7).  "Snapshot a finite
set and validate it" terminates but can still exhaust handles or spend unbounded
time on a large append-only namespace.  Manifest size, DAG depth, node count and
total hashed bytes all carry explicit budgets, and exceeding one is a typed hard
error rather than a slow success.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from forecast.content_store import ContentStore, StoreError

#: Manifest kinds, parent-last.  The order is the DAG's own topology.
SHARD = "shard"
REGION = "region"
ORIGIN_DATASET = "origin_dataset"
STAGE = "stage"

MANIFEST_KINDS = (SHARD, REGION, ORIGIN_DATASET, STAGE)

#: §5.1: the stage manifest must bind all of these, not just regions.
REQUIRED_STAGE_BINDINGS = (
    "origin_datasets",
    "identity_edges",
    "presence_table",
    "duplicate_group_preflight",
    "coverage_margins",
)

#: Round-14 #7's budgets.  Every one is a hard error when exceeded.
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_DAG_DEPTH = 8
MAX_DAG_NODES = 500_000
MAX_HASHED_BYTES = 64 * 1024**3


class ValidationError(StoreError):
    """The DAG did not validate.  No artifact is returned."""


class BudgetExceeded(ValidationError):
    """A traversal budget was exhausted (round-14 #7).

    Typed separately because "too big to check" and "checked and wrong" are
    different operational facts, and collapsing them hides a growing store.
    """


@dataclass(frozen=True)
class Budget:
    """Mutable-by-replacement traversal budget."""

    max_nodes: int = MAX_DAG_NODES
    max_depth: int = MAX_DAG_DEPTH
    max_manifest_bytes: int = MAX_MANIFEST_BYTES
    max_hashed_bytes: int = MAX_HASHED_BYTES


@dataclass
class _Spend:
    nodes: int = 0
    hashed_bytes: int = 0


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """Serialise a manifest deterministically.

    Byte-determinism is not cosmetic here: the manifest's digest **is** its
    identity, so two builds of the same logical manifest must produce the same
    address or the store fills with duplicates that no longer dedupe.
    """

    return (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class Manifest:
    """One node of the DAG.  Every child is named by digest, never by path."""

    kind: str
    name: str
    children: tuple[str, ...]
    schema_digest: str
    cache_key: str
    bindings: Mapping[str, Any] = field(default_factory=dict)

    def document(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "children": list(self.children),
            "schema_digest": self.schema_digest,
            "cache_key": self.cache_key,
            "bindings": dict(self.bindings),
        }

    def to_bytes(self) -> bytes:
        return canonical_bytes(self.document())


def manifest_from_document(document: Mapping[str, Any]) -> Manifest:
    """Strict parsing (round-13 #7): unknown shape is an error, not a default."""

    required = {"kind", "name", "children", "schema_digest", "cache_key", "bindings"}
    keys = set(document)
    if keys != required:
        missing = sorted(required - keys)
        extra = sorted(keys - required)
        raise ValidationError(
            f"manifest shape is wrong; missing={missing} unexpected={extra}"
        )
    if document["kind"] not in MANIFEST_KINDS:
        raise ValidationError(f"unknown manifest kind: {document['kind']!r}")
    children = document["children"]
    if not isinstance(children, list) or not all(isinstance(c, str) for c in children):
        raise ValidationError("children must be a list of digest strings")
    return Manifest(
        kind=document["kind"],
        name=document["name"],
        children=tuple(children),
        schema_digest=document["schema_digest"],
        cache_key=document["cache_key"],
        bindings=document["bindings"],
    )


def publish_manifest(
    store: ContentStore,
    manifest: Manifest,
    *,
    verify_children: bool = True,
) -> str:
    """Publish a manifest **after** recomputing every child's digest (§5.1).

    This is the bottom-up half of §5.3.  `verify_children=False` exists only for
    tests that deliberately construct a broken DAG; production never sets it.
    """

    if manifest.kind == STAGE:
        missing = [k for k in REQUIRED_STAGE_BINDINGS if k not in manifest.bindings]
        if missing:
            raise ValidationError(
                "a stage manifest must bind all three origin datasets, the lineage "
                f"artifacts, the preflight report and the coverage margins; missing {missing}"
            )

    if verify_children:
        for child in manifest.children:
            # Recompute, never trust the recorded digest.  Reading through the
            # store rehashes the bytes and rejects an aliased canonical file.
            store.read_validated(child)

    return store.publish_content_object(manifest.to_bytes()).digest


def load_manifest(store: ContentStore, digest: str, budget: Budget = Budget()) -> Manifest:
    payload = store.read_validated(digest)
    if len(payload) > budget.max_manifest_bytes:
        raise BudgetExceeded(
            f"manifest {digest} is {len(payload)} bytes, over the "
            f"{budget.max_manifest_bytes} budget"
        )
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"manifest {digest} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidationError(f"manifest {digest} is not an object")
    return manifest_from_document(document)


@dataclass(frozen=True)
class DagReport:
    """What a top-down validation found."""

    root: str
    manifests: int
    leaves: int
    depth: int
    hashed_bytes: int


def validate_dag(
    store: ContentStore,
    root: str,
    *,
    budget: Budget = Budget(),
) -> DagReport:
    """Revalidate the complete hash-linked DAG top-down (§5.3).

    Digest results are memoized, so a shared child is hashed once however many
    parents name it -- which is what keeps a wide DAG from quadratic rehashing
    (round-13 #7).
    """

    spend = _Spend()
    seen: dict[str, int] = {}
    manifests = 0
    leaves = 0
    max_depth = 0

    stack: list[tuple[str, int]] = [(root, 1)]
    while stack:
        digest, depth = stack.pop()
        max_depth = max(max_depth, depth)

        if depth > budget.max_depth:
            raise BudgetExceeded(
                f"DAG depth {depth} exceeds the {budget.max_depth} budget at {digest}"
            )
        if digest in seen:
            continue

        spend.nodes += 1
        if spend.nodes > budget.max_nodes:
            raise BudgetExceeded(
                f"DAG has more than {budget.max_nodes} distinct nodes"
            )

        payload = store.read_validated(digest)
        spend.hashed_bytes += len(payload)
        if spend.hashed_bytes > budget.max_hashed_bytes:
            raise BudgetExceeded(
                f"validation hashed more than {budget.max_hashed_bytes} bytes"
            )
        seen[digest] = depth

        try:
            document = json.loads(payload)
            is_manifest = isinstance(document, dict) and document.get("kind") in MANIFEST_KINDS
        except (json.JSONDecodeError, UnicodeDecodeError):
            is_manifest = False

        if not is_manifest:
            leaves += 1
            continue

        manifest = manifest_from_document(document)
        manifests += 1
        for child in manifest.children:
            stack.append((child, depth + 1))

    return DagReport(
        root=root,
        manifests=manifests,
        leaves=leaves,
        depth=max_depth,
        hashed_bytes=spend.hashed_bytes,
    )
