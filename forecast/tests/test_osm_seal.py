"""§5.5 the seal, and the sweep behaviour that made it necessary.

The first test here is the one whose absence cost 101.1 MB of deliverable in a
dry run: **publish §4 and §6, then ask what a sweep would collect.** Every §5
test until now published everything under one generation, so the drivers'
habit of publishing outside the generation namespace was invisible.
"""

from __future__ import annotations

import json

import pytest

from forecast.content_store import ContentStore
from forecast.generations import (
    DatasetIdentity,
    GenerationStore,
    NoValidGeneration,
    SweepRefused,
)
from forecast.manifests import (
    REQUIRED_STAGE_BINDINGS,
    SHARD,
    STAGE,
    Manifest,
    publish_manifest,
    validate_dag,
)
from forecast.osm_seal import (
    SEAL_DATASET,
    SEAL_NAME,
    SealIncomplete,
    assert_bindings_resolve,
    bound_digests,
    seal,
)

SCHEMA = "a" * 64


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


def build_store(local_root):
    """A store shaped like the corpus one: a pass-1 stage, then loose drivers."""

    generations = GenerationStore(local_root / "store")
    store = generations.store

    region = _shard(store, "region-1", (_leaf(store, "ways"),))
    pass_one = publish_manifest(
        store,
        Manifest(
            STAGE, "osm-normalisation-pass-1", (region,),
            schema_digest=SCHEMA, cache_key="pass-1",
            bindings={
                "origin_datasets": ["2020", "2022"],
                "identity_edges": None,
                "presence_table": None,
                "duplicate_group_preflight": None,
                "coverage_margins": {"F1": 5000.0},
            },
        ),
    )
    identity = DatasetIdentity("osm-normalisation-pass-1", SCHEMA, "pass-1")
    lease = generations.shared_lease()
    try:
        generations.publish_generation(
            pass_one, identity, generations.state_token(identity), lease=lease
        )
    finally:
        lease.release()

    # §4 and §6 publish straight into the object store, as they really do.
    origins = {
        2020: _shard(store, "deduplicated-2020", (_leaf(store, "o2020"),)),
        2022: _shard(store, "deduplicated-2022", (_leaf(store, "o2022"),)),
    }
    edges = _shard(store, "identity-edges", (_leaf(store, "edges"),))
    presence = _shard(store, "presence-table", (_leaf(store, "presence"),))
    return generations, pass_one, origins, edges, presence


def test_an_unsealed_store_leaves_the_deliverable_collectable(local_root):
    """The corpus finding, reproduced in miniature.

    §4's and §6's manifests are valid, published and unreachable.  A sweep would
    be entirely correct to delete them, which is why the seal exists.
    """

    generations, _, origins, edges, presence = build_store(local_root)
    reachable = generations.reachable_objects()

    for digest in (*origins.values(), edges, presence):
        assert digest not in reachable, (
            "an artifact no root mentions is garbage, however valid it is"
        )


def test_sealing_makes_every_deliverable_artifact_reachable(local_root):
    generations, pass_one, origins, edges, presence = build_store(local_root)

    result = seal(
        generations,
        origin_manifests=origins,
        edges_manifest=edges,
        presence_manifest=presence,
        preflight_report={"clean": True, "duplicate_groups": 34},
        coverage_margins={"F1": 5003.18},
        pass_one_root=pass_one,
        schema_digest=SCHEMA,
    )

    reachable = generations.reachable_objects()
    for digest in (*origins.values(), edges, presence, pass_one):
        assert digest in reachable
    assert result.preflight_digest in reachable
    assert result.coverage_digest in reachable


def test_a_sweep_after_sealing_collects_nothing_from_the_deliverable(local_root):
    """The seal's whole purpose, asserted as the sweep's actual behaviour."""

    generations, pass_one, origins, edges, presence = build_store(local_root)
    seal(
        generations,
        origin_manifests=origins, edges_manifest=edges, presence_manifest=presence,
        preflight_report={"clean": True}, coverage_margins={"F1": 1.0},
        pass_one_root=pass_one, schema_digest=SCHEMA,
    )
    identity = DatasetIdentity(SEAL_DATASET, SCHEMA, "pass-1")

    lease = generations.exclusive_lease()
    try:
        report = generations.sweep(identity, lease=lease)
    finally:
        lease.release()

    assert report["deleted"] == []
    assert report["freed_bytes"] == 0
    for digest in (*origins.values(), edges, presence):
        assert generations.store.path_for(digest).exists()


def test_the_seal_is_selectable_under_its_own_identity(local_root):
    """A consumer asking for the deliverable must not be handed a pass-1 stage."""

    generations, pass_one, origins, edges, presence = build_store(local_root)
    result = seal(
        generations,
        origin_manifests=origins, edges_manifest=edges, presence_manifest=presence,
        preflight_report={"clean": True}, coverage_margins={"F1": 1.0},
        pass_one_root=pass_one, schema_digest=SCHEMA,
    )

    lease = generations.shared_lease()
    try:
        selection = generations.select(DatasetIdentity(SEAL_DATASET, SCHEMA, "pass-1"))
    finally:
        lease.release()

    assert selection.number == result.generation
    assert selection.root_digest == result.stage_digest
    assert selection.degraded is False


def test_a_binding_that_names_a_label_is_refused(local_root):
    """`origin_datasets: ["2020", "2022"]` is the same omission as `None`.

    Both satisfy `REQUIRED_STAGE_BINDINGS`, and neither names an object.
    """

    generations, *_ = build_store(local_root)
    bindings = {k: None for k in REQUIRED_STAGE_BINDINGS}
    bindings["origin_datasets"] = ["2020", "2022"]

    with pytest.raises(SealIncomplete, match="name no object"):
        assert_bindings_resolve(generations.store, bindings)


def test_a_binding_naming_a_digest_the_store_lost_is_refused(local_root):
    """Rehashed at seal time, not trusted from when it was written."""

    generations, pass_one, origins, edges, presence = build_store(local_root)
    generations.store.path_for(edges).unlink()

    bindings = {
        "origin_datasets": {"2020": origins[2020]},
        "identity_edges": edges,
        "presence_table": presence,
        "duplicate_group_preflight": pass_one,
        "coverage_margins": pass_one,
    }
    with pytest.raises(SealIncomplete, match="does not resolve"):
        assert_bindings_resolve(generations.store, bindings)


def test_the_sealed_stage_binds_what_it_reaches(local_root):
    """Binding and reachability must not drift: same edges, both ways."""

    generations, pass_one, origins, edges, presence = build_store(local_root)
    result = seal(
        generations,
        origin_manifests=origins, edges_manifest=edges, presence_manifest=presence,
        preflight_report={"clean": True}, coverage_margins={"F1": 1.0},
        pass_one_root=pass_one, schema_digest=SCHEMA,
    )

    document = json.loads(generations.store.read_validated(result.stage_digest))
    assert document["name"] == SEAL_NAME
    assert set(bound_digests(document["bindings"])) <= set(document["children"])


def test_a_sweep_is_still_refused_without_an_anchor(local_root):
    """The seal establishes the anchor; without one, nothing is collected."""

    generations, *_ = build_store(local_root)
    identity = DatasetIdentity("osm-normalisation-pass-1", SCHEMA, "pass-1")

    lease = generations.exclusive_lease()
    try:
        with pytest.raises(SweepRefused):
            generations.sweep(identity, lease=lease)
    finally:
        lease.release()


def test_bound_digests_ignores_values_that_are_not_digests():
    assert bound_digests({"a": None, "b": ["2020"], "c": {"x": 1.5}}) == ()
    assert bound_digests({"a": "z" * 64}) == (), "64 chars is not enough; it must be hex"
    assert bound_digests({"a": "b" * 64}) == ("b" * 64,)
