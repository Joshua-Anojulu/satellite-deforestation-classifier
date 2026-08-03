"""§5.5 the seal — the root that makes Plan A's deliverable reachable.

Implements the step §5 specified and no code ever performed, discovered by
running §5.4's sweep against the real corpus store as a dry run.

**What the dry run found.** The corpus store holds 264 objects. Reachability
from its four generations covers 254 of them. The other ten are:

    3  origin_dataset manifests   (§4's deduplicated 2020 / 2021 / 2022)
    1  shard/identity-edges       (§6)
    1  shard/presence-table       (§6)
    5  content leaves             (their payloads)

which is 101.1 MB and is not garbage: it is the entire deliverable. A sweep run
at that moment would have deleted Plan A's output and been correct to, because
nothing in the store referred to it.

**Nothing was broken; a step was missing.** §5.1 already requires a stage
manifest to bind `origin_datasets`, `identity_edges`, `presence_table`,
`duplicate_group_preflight` and `coverage_margins` -- exactly the deliverable.
Pass 1 binds the lineage keys to `null` **on purpose**, so a consumer can tell
"not built yet" from "built and empty", and that is right: pass 1 has no edges to
name. The gap is that §4 and §6 then published their manifests straight into the
object store and **no later stage ever re-bound them**. The DAG's roots were all
pass-1 roots. The drivers' output hung off nothing.

`REQUIRED_STAGE_BINDINGS` did not catch it because it checks that the *keys* are
present, never that they name anything. `{"identity_edges": None}` satisfies it.
So does `{"origin_datasets": ["2020", "2021", "2022"]}` -- year labels where §5.1
means digests, which is the same omission in a second costume.

**This module is where that check is real.** :func:`seal` refuses to publish
unless every required binding resolves to an object actually in the store, and
the sealed stage's children are the bound digests themselves, so binding and
reachability cannot drift apart: a consumer that reads the binding and a sweep
that walks the children traverse the same edges.

The two bindings that had no object at all -- the preflight report and the
coverage margins, both previously inline dicts or files outside the store -- are
published as content objects here, because a binding that names no object is the
defect this module exists to close.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from forecast.content_store import ContentStore, StoreLease
from forecast.generations import (
    DatasetIdentity,
    GenerationRecord,
    GenerationStore,
)
from forecast.manifests import (
    MANIFEST_KINDS,
    REQUIRED_STAGE_BINDINGS,
    STAGE,
    Budget,
    Manifest,
    ValidationError,
    publish_manifest,
)

#: The sealed stage's name, distinct from `osm-normalisation-pass-1`.
SEAL_NAME = "osm-normalisation-sealed"

#: The sealed dataset's identity is its own: a consumer asking for the
#: deliverable must not be handed a pass-1 stage that merely validates.
SEAL_DATASET = "osm-normalisation-deliverable"


class SealIncomplete(ValidationError):
    """A required binding names nothing, or names something not in the store."""


@dataclass(frozen=True)
class Seal:
    """The published seal, and what it made reachable."""

    stage_digest: str
    generation: int
    anchor: int
    bindings: Mapping[str, Any]
    children: tuple[str, ...]
    preflight_digest: str
    coverage_digest: str

    def document(self) -> dict[str, Any]:
        return {
            "stage_digest": self.stage_digest,
            "generation": self.generation,
            "anchor": self.anchor,
            "bindings": dict(self.bindings),
            "children": list(self.children),
            "preflight_digest": self.preflight_digest,
            "coverage_digest": self.coverage_digest,
        }


def _canonical(document: Any) -> bytes:
    return (
        json.dumps(document, indent=None, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def bound_digests(bindings: Mapping[str, Any]) -> tuple[str, ...]:
    """Every digest a binding names, in sorted order.

    A binding is a digest, a list of digests, or a mapping whose values are
    digests. Anything else -- `None`, a year label, an inline dict of floats --
    names no object, and :func:`assert_bindings_resolve` rejects it.
    """

    digests: set[str] = set()
    for value in bindings.values():
        candidates: Sequence[Any]
        if isinstance(value, str):
            candidates = (value,)
        elif isinstance(value, Mapping):
            candidates = tuple(value.values())
        elif isinstance(value, (list, tuple)):
            candidates = tuple(value)
        else:
            candidates = ()
        for candidate in candidates:
            if isinstance(candidate, str) and len(candidate) == 64:
                try:
                    int(candidate, 16)
                except ValueError:
                    continue
                digests.add(candidate)
    return tuple(sorted(digests))


def assert_bindings_resolve(store: ContentStore, bindings: Mapping[str, Any]) -> tuple[str, ...]:
    """Every required binding must name at least one object that exists.

    This is the check `REQUIRED_STAGE_BINDINGS` does not perform. It reads each
    object back through :meth:`ContentStore.read_validated`, so the bytes are
    rehashed at seal time rather than trusted from when they were written -- a
    binding that names a digest the store no longer holds is exactly the state a
    premature sweep would leave behind.
    """

    missing = [key for key in REQUIRED_STAGE_BINDINGS if key not in bindings]
    if missing:
        raise SealIncomplete(f"the seal is missing required bindings: {missing}")

    empty = [
        key
        for key in REQUIRED_STAGE_BINDINGS
        if not bound_digests({key: bindings[key]})
    ]
    if empty:
        raise SealIncomplete(
            f"these bindings name no object in the store: {empty}; a stage that "
            "binds a label or a null is why the deliverable was collectable"
        )

    digests = bound_digests(bindings)
    for digest in digests:
        try:
            store.read_validated(digest)
        except Exception as exc:  # noqa: BLE001 - any failure to resolve is fatal here
            raise SealIncomplete(
                f"binding names {digest[:16]} which does not resolve: {exc}"
            ) from exc
    return digests


def seal(
    generations: GenerationStore,
    *,
    origin_manifests: Mapping[int, str],
    edges_manifest: str,
    presence_manifest: str,
    preflight_report: Mapping[str, Any],
    coverage_margins: Mapping[str, float],
    pass_one_root: str,
    schema_digest: str,
    cache_key: str = "pass-1",
    budget: Budget = Budget(),
) -> Seal:
    """Publish the sealed stage, make it a generation, and anchor it.

    The order is forced by the lease rules and is not incidental:

    1. publish the two missing content objects and the stage manifest;
    2. publish the generation under the **shared** lease, held from the first
       object write through publication (round-14 #4);
    3. release it, take the **exclusive** lease, establish the anchor.

    Steps 2 and 3 cannot overlap: `LockFileEx` ranges are per handle, so one
    process cannot hold both leases on the same byte range at once.
    """

    store = generations.store

    lease = generations.shared_lease()
    try:
        preflight_digest = store.publish_content_object(_canonical(dict(preflight_report))).digest
        coverage_digest = store.publish_content_object(_canonical(dict(coverage_margins))).digest

        bindings = {
            "origin_datasets": {str(k): v for k, v in sorted(origin_manifests.items())},
            "identity_edges": edges_manifest,
            "presence_table": presence_manifest,
            "duplicate_group_preflight": preflight_digest,
            "coverage_margins": coverage_digest,
            "pass_one_stage": pass_one_root,
        }
        digests = assert_bindings_resolve(store, bindings)

        # The children ARE the bound digests, plus the pass-1 root so the whole
        # upstream DAG stays under one root.  Binding and reachability traverse
        # the same edges by construction.
        children = tuple(sorted(set(digests) | {pass_one_root}))
        stage_digest = publish_manifest(
            store,
            Manifest(
                STAGE,
                SEAL_NAME,
                children,
                schema_digest=schema_digest,
                cache_key=cache_key,
                bindings=bindings,
            ),
        )

        identity = DatasetIdentity(
            dataset=SEAL_DATASET, schema_digest=schema_digest, cache_key=cache_key
        )
        expected = generations.state_token(identity)
        record = generations.publish_generation(
            stage_digest, identity, expected, lease=lease, budget=budget
        )
    finally:
        lease.release()

    exclusive = generations.exclusive_lease()
    try:
        anchor = generations.establish_anchor(identity, lease=exclusive)
    finally:
        exclusive.release()

    if anchor is None:
        raise SealIncomplete(
            "the seal published but no anchor could be established; a sweep would "
            "still be refused, which is the safe direction"
        )

    return Seal(
        stage_digest=stage_digest,
        generation=record.number,
        anchor=anchor,
        bindings=bindings,
        children=children,
        preflight_digest=preflight_digest,
        coverage_digest=coverage_digest,
    )
