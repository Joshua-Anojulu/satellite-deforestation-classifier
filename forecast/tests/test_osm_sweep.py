"""§5.4 collection driven the way it must be driven: survey, then collect.

These tests exist because `GenerationStore.sweep` was correct and still one call
away from deleting Plan A's deliverable.  The invariant it enforces -- collect
nothing without an anchor -- was never violated.  What was missing was a caller
obliged to look at the collectable set before authorising it.
"""

from __future__ import annotations

import json

import pytest

from forecast.generations import DatasetIdentity, GenerationStore
from forecast.manifests import SHARD, STAGE, Manifest, publish_manifest
from forecast.osm_seal import SEAL_DATASET, seal
from forecast.osm_sweep import CollectionRefused, classify, collect, retire_superseded, survey

SCHEMA = "a" * 64
IDENTITY = DatasetIdentity(SEAL_DATASET, SCHEMA, "pass-1")


@pytest.fixture
def local_root(tmp_path):
    assert "onedrive" not in str(tmp_path).lower()
    return tmp_path


def _leaf(store, text):
    return store.publish_content_object(text.encode()).digest


def _shard(store, name, children):
    return publish_manifest(
        store,
        Manifest(SHARD, name, tuple(children), schema_digest=SCHEMA, cache_key="pass-1"),
    )


def sealed_store(local_root, *, superseded_payload="old-closure"):
    """A store with a superseded generation, a current one, and a seal.

    Mirrors the corpus: generation 1 carries closure records that generation 2
    replaced, and the deliverable hangs off the seal.
    """

    generations = GenerationStore(local_root / "store")
    store = generations.store
    identity = DatasetIdentity("osm-normalisation-pass-1", SCHEMA, "pass-1")

    def publish_stage(closure_text):
        closure = _shard(store, "closure-region", (_leaf(store, closure_text),))
        return publish_manifest(
            store,
            Manifest(
                STAGE, "osm-normalisation-pass-1", (closure,),
                schema_digest=SCHEMA, cache_key="pass-1",
                bindings={
                    "origin_datasets": ["2020"], "identity_edges": None,
                    "presence_table": None, "duplicate_group_preflight": None,
                    "coverage_margins": {"F1": 5000.0},
                },
            ),
        )

    roots = []
    for text in (superseded_payload, "new-closure-with-geometry"):
        root = publish_stage(text)
        lease = generations.shared_lease()
        try:
            generations.publish_generation(
                root, identity, generations.state_token(identity), lease=lease
            )
        finally:
            lease.release()
        roots.append(root)

    origins = {2020: _shard(store, "deduplicated-2020", (_leaf(store, "o2020"),))}
    edges = _shard(store, "identity-edges", (_leaf(store, "edges"),))
    presence = _shard(store, "presence-table", (_leaf(store, "presence"),))
    seal(
        generations,
        origin_manifests=origins, edges_manifest=edges, presence_manifest=presence,
        preflight_report={"clean": True}, coverage_margins={"F1": 5000.0},
        pass_one_root=roots[1], schema_digest=SCHEMA,
    )
    protected = {"edges": edges, "presence": presence, "origin-2020": origins[2020]}
    return generations, roots, protected


def test_a_survey_deletes_nothing(local_root):
    generations, _, protected = sealed_store(local_root)
    before = set(generations.store.content_objects())

    survey(generations, protected=protected)

    assert set(generations.store.content_objects()) == before


def test_a_survey_names_an_endangered_artifact_rather_than_counting_it(local_root):
    """The corpus finding in miniature: an unsealed deliverable is collectable.

    A count would have said "10 objects"; the name is what stops a sweep.
    """

    generations = GenerationStore(local_root / "store")
    store = generations.store
    identity = DatasetIdentity("osm-normalisation-pass-1", SCHEMA, "pass-1")
    root = publish_manifest(
        store,
        Manifest(
            STAGE, "osm-normalisation-pass-1", (_shard(store, "r", (_leaf(store, "w"),)),),
            schema_digest=SCHEMA, cache_key="pass-1",
            bindings={
                "origin_datasets": ["2020"], "identity_edges": None,
                "presence_table": None, "duplicate_group_preflight": None,
                "coverage_margins": {},
            },
        ),
    )
    lease = generations.shared_lease()
    try:
        generations.publish_generation(
            root, identity, generations.state_token(identity), lease=lease
        )
    finally:
        lease.release()
    edges = _shard(store, "identity-edges", (_leaf(store, "edges"),))

    result = survey(generations, protected={"§6 identity edges": edges})

    assert result.endangered == {"§6 identity edges": edges}
    assert result.safe is False


def test_collection_is_refused_when_the_survey_is_unsafe(local_root):
    """A genuinely endangered artifact, not a forced flag.

    Generation 1 is retired, so its closure leaf really is collectable.  A caller
    that protects it gets a refusal instead of a deletion.
    """

    generations, _, _ = sealed_store(local_root)
    store = generations.store
    superseded_leaf = next(
        d for d in store.content_objects()
        if store.path_for(d).read_bytes() == b"old-closure"
    )

    lease = generations.exclusive_lease()
    try:
        retire_superseded(generations, [1], lease=lease)
        unsafe = survey(generations, protected={"still wanted": superseded_leaf})
        assert unsafe.safe is False

        with pytest.raises(CollectionRefused, match="protected artifacts"):
            collect(generations, IDENTITY, lease=lease, survey_result=unsafe)
    finally:
        lease.release()

    assert store.path_for(superseded_leaf).exists(), "the refusal must not have deleted it"


def test_collection_is_refused_when_the_store_moved_after_the_survey(local_root):
    """Retiring between survey and collection would delete what was never measured."""

    generations, _, protected = sealed_store(local_root)
    taken = survey(generations, protected=protected)

    lease = generations.exclusive_lease()
    try:
        retire_superseded(generations, [1], lease=lease)
        with pytest.raises(CollectionRefused, match="store moved"):
            collect(generations, IDENTITY, lease=lease, survey_result=taken)
    finally:
        lease.release()


def test_retiring_the_anchor_is_refused(local_root):
    generations, _, _ = sealed_store(local_root)
    anchor = generations.anchor()

    lease = generations.exclusive_lease()
    try:
        with pytest.raises(CollectionRefused, match="is the anchor"):
            retire_superseded(generations, [anchor], lease=lease)
    finally:
        lease.release()
    assert generations.retired() == frozenset()


def test_retire_then_survey_then_collect_frees_the_superseded_objects(local_root):
    """The whole procedure, and the deliverable survives it."""

    generations, roots, protected = sealed_store(local_root)
    store = generations.store
    superseded_leaf = next(
        d for d in store.content_objects()
        if store.path_for(d).read_bytes() == b"old-closure"
    )

    lease = generations.exclusive_lease()
    try:
        retire_superseded(generations, [1], lease=lease)
        taken = survey(generations, protected=protected)
        assert taken.safe
        assert superseded_leaf in taken.collectable
        report = collect(generations, IDENTITY, lease=lease, survey_result=taken)
    finally:
        lease.release()

    assert superseded_leaf in report["deleted"]
    assert report["freed_bytes"] > 0
    assert report["surveyed"] == len(report["deleted"])
    for digest in protected.values():
        assert store.path_for(digest).exists(), "the seal kept the deliverable"


def test_classify_reports_an_unreadable_object_as_unreadable(local_root):
    """A sweep deletes it either way; the survey must not call it a data leaf."""

    generations, _, _ = sealed_store(local_root)
    store = generations.store
    digest = _leaf(store, "corruptible")
    store.path_for(digest).write_bytes(b"tampered")

    assert classify(store, digest) == "unreadable"


def test_classify_names_the_manifest_it_found(local_root):
    generations, _, protected = sealed_store(local_root)
    assert classify(generations.store, protected["edges"]) == "shard/identity-edges"
