"""§5.4 collection over a real store — survey first, collect second.

A sweep is only as safe as its reachability roots, and on the corpus store that
stopped being an abstract remark. Before §5.5's seal existed, :func:`survey`
reported that a sweep would collect ten objects totalling **101.1 MB**: §4's
three origin-dataset manifests, §6's identity-edges and presence-table shards,
and their five content leaves. That is not garbage, it is the deliverable, and
the sweep would have been correct to delete it because no root named it.

**So collection is a two-step procedure and the first step writes nothing.**
:func:`survey` classifies every collectable object by manifest kind and reports
by name any digest a caller says it cares about. `101.1 MB across 10 objects` and
`the presence table would be deleted` are different findings, and only the second
one stops a sweep.

:func:`collect` refuses unless a survey has been taken and its `protected`
digests all came back reachable. The refusal is the point: `GenerationStore.sweep`
already enforces the anchor invariant correctly, and it was still one call away
from destroying Plan A's output. What was missing was not a stronger invariant
but a caller obliged to look first.

**What a real collection cost, measured.** With the deliverable sealed and
generations 1-3 retired as superseded -- all three share one root, and their
pass-2 records predate the geometry columns §6 needs -- the sweep collected 71
objects for 58,862 bytes: 54 closure manifests and 17 content leaves. Every
protected digest survived. The store went from 267 objects to 196.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from forecast.content_store import ContentStore, StoreLease
from forecast.generations import (
    DatasetIdentity,
    GenerationStore,
    SweepRefused,
)
from forecast.manifests import MANIFEST_KINDS, Budget


class CollectionRefused(SweepRefused):
    """A survey was not taken, or it named a protected artifact. Nothing deleted."""


def classify(store: ContentStore, digest: str) -> str:
    """`<kind>/<name>` for a manifest, `content` for a leaf, `unreadable` otherwise.

    An unreadable object is reported as such rather than assumed to be a leaf: a
    sweep deletes it either way, and a survey that called it a data leaf would be
    describing a deletion it had not actually understood.
    """

    try:
        payload = store.read_validated(digest)
    except Exception:  # noqa: BLE001 - every read failure reports the same way
        return "unreadable"
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "content"
    if isinstance(document, dict) and document.get("kind") in MANIFEST_KINDS:
        return f"{document['kind']}/{document.get('name')}"
    return "content"


@dataclass(frozen=True)
class Survey:
    """What a sweep would do, measured without doing it."""

    objects: int
    reachable: int
    collectable: tuple[str, ...]
    collectable_bytes: int
    by_kind: Mapping[str, int]
    endangered: Mapping[str, str]
    orphans: tuple[str, ...]
    generations: tuple[int, ...]
    retired: tuple[int, ...]
    anchor: int | None

    @property
    def safe(self) -> bool:
        """True when no protected artifact is in the collectable set."""

        return not self.endangered

    def document(self) -> dict[str, Any]:
        return {
            "objects": self.objects,
            "reachable": self.reachable,
            "collectable": len(self.collectable),
            "collectable_bytes": self.collectable_bytes,
            "by_kind": dict(sorted(self.by_kind.items())),
            "endangered": dict(sorted(self.endangered.items())),
            "orphans": len(self.orphans),
            "generations": list(self.generations),
            "retired": list(self.retired),
            "anchor": self.anchor,
            "safe": self.safe,
        }


def survey(
    generations: GenerationStore,
    *,
    protected: Mapping[str, str] = {},
    budget: Budget = Budget(),
) -> Survey:
    """Report what :meth:`GenerationStore.sweep` would collect. Deletes nothing.

    `protected` maps a label to a digest -- typically the artifacts a previous
    run recorded under `forecast/artifacts/`. Any that fall outside the reachable
    set come back in :attr:`Survey.endangered`, named.
    """

    store = generations.store
    reachable = generations.reachable_objects(budget=budget)
    objects = store.content_objects()

    collectable: list[str] = []
    collectable_bytes = 0
    by_kind: dict[str, int] = {}
    for digest in objects:
        if digest in reachable:
            continue
        collectable.append(digest)
        try:
            collectable_bytes += store.path_for(digest).stat().st_size
        except OSError:
            pass
        kind = classify(store, digest)
        by_kind[kind] = by_kind.get(kind, 0) + 1

    doomed = set(collectable)
    return Survey(
        objects=len(objects),
        reachable=len(reachable),
        collectable=tuple(collectable),
        collectable_bytes=collectable_bytes,
        by_kind=by_kind,
        endangered={label: d for label, d in protected.items() if d in doomed},
        orphans=tuple(p.name for p in store.orphans()),
        generations=generations.generation_numbers(),
        retired=tuple(sorted(generations.retired())),
        anchor=generations.anchor(),
    )


def retire_superseded(
    generations: GenerationStore,
    numbers: Iterable[int],
    *,
    lease: StoreLease,
) -> tuple[int, ...]:
    """Retire generations before their objects are collected (round-13 #10).

    Refuses to retire the anchor: the anchor is the invariant a sweep is checked
    against, and retiring it would leave :meth:`GenerationStore.sweep` collecting
    against a root it had just invalidated.
    """

    anchor = generations.anchor()
    ordered = tuple(sorted(set(numbers)))
    if anchor is not None and anchor in ordered:
        raise CollectionRefused(
            f"generation {anchor} is the anchor; retiring it would collect against "
            "an invariant that no longer holds"
        )
    for number in ordered:
        generations.retire(number, lease=lease)
    return ordered


def collect(
    generations: GenerationStore,
    identity: DatasetIdentity,
    *,
    lease: StoreLease,
    survey_result: Survey,
    budget: Budget = Budget(),
) -> dict[str, Any]:
    """Run the sweep, but only against a survey that came back safe.

    The survey must have been taken against this same store state; a caller that
    retires generations between surveying and collecting is asking to delete
    something it never measured, so the collectable set is re-derived here and
    compared. A mismatch is refused rather than reconciled.
    """

    if not survey_result.safe:
        raise CollectionRefused(
            "the survey named protected artifacts as collectable: "
            + ", ".join(sorted(survey_result.endangered))
        )

    fresh = survey(generations, budget=budget)
    if set(fresh.collectable) != set(survey_result.collectable):
        raise CollectionRefused(
            f"the store moved between survey and collection: {len(survey_result.collectable)} "
            f"objects surveyed, {len(fresh.collectable)} collectable now; re-survey"
        )

    report = generations.sweep(identity, lease=lease, budget=budget)
    report["surveyed"] = len(survey_result.collectable)
    return report
