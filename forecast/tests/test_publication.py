"""§5 publication and GC: the rounds 10-14 findings as a kill-test list.

Fourteen review rounds could not converge §5, and rounds 13 and 14 both sourced
their criticals from the previous round's own fixes.  These tests are the list
the owner decided to settle it with, one test per finding, run against real
NTFS in a local temporary directory.

Discipline throughout, as elsewhere in this project: **assert the positive case,
not the absence of a symptom.**  A test that only checked "no exception" would
pass against a primitive that published nothing at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forecast.content_store import (
    ALREADY_PRESENT,
    ERROR_ALREADY_EXISTS,
    PUBLISHED,
    REPLACE_IF_EXISTS,
    SUCCESS_WITH_ORPHAN,
    ContentStore,
    ImmutabilityViolation,
    LeaseUnavailable,
    StoreError,
    StoreLease,
    digest_of,
    link_count,
)
from forecast.generations import (
    CURRENT,
    DEGRADED_FALLBACK,
    DatasetIdentity,
    GenerationStore,
    NoValidGeneration,
    PublicationAborted,
    StateToken,
    SweepRefused,
    generation_name,
    generation_number,
)
from forecast.manifests import (
    ORIGIN_DATASET,
    REGION,
    SHARD,
    STAGE,
    Budget,
    BudgetExceeded,
    Manifest,
    ValidationError,
    load_manifest,
    publish_manifest,
    validate_dag,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="§5 is a Windows/NTFS design"
)


@pytest.fixture
def local_root(tmp_path):
    """A root on a LOCAL volume, asserted rather than assumed.

    This repository lives under OneDrive, whose minifilter and cloud replication
    sit outside the local-NTFS guarantee the whole of §5 rests on.  pytest's
    `tmp_path` is under the local temp root, but that is an assumption worth
    checking once here rather than discovering through a confusing failure.
    """

    assert "onedrive" not in str(tmp_path).lower(), (
        f"§5 requires a local NTFS volume; got {tmp_path}"
    )
    return tmp_path


@pytest.fixture
def store(local_root):
    return ContentStore(local_root / "objects")


@pytest.fixture
def generations(local_root):
    return GenerationStore(local_root / "store")


IDENTITY = DatasetIdentity(
    dataset="specification_w_osm",
    schema_digest="schema-v1",
    cache_key="cache-key-v1",
)


def _stage_manifest(children, *, identity=IDENTITY) -> Manifest:
    return Manifest(
        kind=STAGE,
        name="stage",
        children=tuple(children),
        schema_digest=identity.schema_digest,
        cache_key=identity.cache_key,
        bindings={
            "origin_datasets": ["2020", "2021", "2022"],
            "identity_edges": "edges",
            "presence_table": "presence",
            "duplicate_group_preflight": "preflight",
            "coverage_margins": "margins",
        },
    )


# --------------------------------------------------------------------------
# Kill test: the rename primitive (round-14 #1)
# --------------------------------------------------------------------------


def test_publishing_writes_the_exact_bytes_to_the_content_address(store):
    """The primitive publishes, and the canonical file holds the payload."""

    payload = b"the normalised way geometry"
    result = store.publish_content_object(payload)

    assert result.outcome == PUBLISHED
    assert result.digest == digest_of(payload)
    assert result.path.name == digest_of(payload)
    assert result.path.read_bytes() == payload
    assert result.committed


def test_the_rename_survives_because_the_handle_is_still_open(store):
    """Round-14 #1: v14's flush-close-then-rename is impossible.

    The probe measured `ERROR_INVALID_HANDLE` (6) for a closed handle, so the
    primitive keeps the handle open across the rename.  If it ever reverted to
    closing first, this publish would raise rather than produce a file.
    """

    result = store.publish_content_object(b"live handle rename")

    assert result.path.exists()
    assert store.read_validated(result.digest) == b"live handle rename"
    # No temporary survived: the rename moved the very file that was written.
    assert store.orphans() == ()


def test_republishing_identical_content_is_idempotent_and_keeps_one_object(store):
    payload = b"same bytes twice"
    first = store.publish_content_object(payload)
    second = store.publish_content_object(payload)

    assert first.outcome == PUBLISHED
    assert second.outcome in (ALREADY_PRESENT, SUCCESS_WITH_ORPHAN)
    assert second.committed
    assert second.digest == first.digest
    assert store.content_objects() == (first.digest,)
    assert first.path.read_bytes() == payload


def test_replace_if_exists_is_frozen_false(store):
    """The probe watched `TRUE` silently overwrite a canonical object.

    That is the single outcome the store forbids, so the flag is a constant.
    """

    assert REPLACE_IF_EXISTS is False


def test_a_collision_with_different_bytes_fails_closed(store):
    """Unequal bytes at one address are corruption, never assumed away."""

    payload = b"authentic"
    result = store.publish_content_object(payload)
    # Simulate the impossible-by-construction case the design refuses to
    # assume away: the canonical name holding foreign bytes.
    result.path.write_bytes(b"tampered")

    with pytest.raises(ImmutabilityViolation) as excinfo:
        store.publish_content_object(payload)
    assert "different bytes" in str(excinfo.value)


def test_reading_a_tampered_object_fails_closed(store):
    result = store.publish_content_object(b"original")
    result.path.write_bytes(b"rewritten to a different length")

    with pytest.raises(ImmutabilityViolation):
        store.read_validated(result.digest)


# --------------------------------------------------------------------------
# Kill test: the delete-failure branch (round-13 #11, round-14 #10)
# --------------------------------------------------------------------------


def test_success_with_orphan_is_a_commit_and_names_the_debt(store, monkeypatch):
    """Round-14 #10: the caller contract.

    The probe measured `ERROR_SHARING_VIOLATION` (32) deleting a temporary
    whose handle another process holds.  When that happens the canonical object
    is already renamed into place, so the outcome must be a commit carrying
    cleanup debt -- a caller that halted would abandon a successful publication.
    """

    payload = b"orphan branch"
    store.publish_content_object(payload)

    real_unlink = os.unlink

    def refuse_once(path, *args, **kwargs):
        raise PermissionError(32, "sharing violation")

    monkeypatch.setattr(os, "unlink", refuse_once)
    result = store.publish_content_object(payload)
    monkeypatch.setattr(os, "unlink", real_unlink)

    assert result.outcome == SUCCESS_WITH_ORPHAN
    assert result.committed, "an orphaned temporary must not unwind a commit"
    assert result.orphan is not None
    assert result.orphan.exists()
    assert result.path.read_bytes() == payload
    assert result.orphan in store.orphans()


def test_orphans_are_excluded_from_the_canonical_namespace(store, monkeypatch):
    payload = b"namespace separation"
    store.publish_content_object(payload)
    monkeypatch.setattr(os, "unlink", lambda *a, **k: (_ for _ in ()).throw(PermissionError(32, "x")))
    result = store.publish_content_object(payload)

    assert result.orphan is not None
    assert store.content_objects() == (result.digest,), (
        "a leftover temporary must never appear as a content object"
    )


# --------------------------------------------------------------------------
# Kill test: immutability enforcement (round-13 #9)
# --------------------------------------------------------------------------


def test_the_reparse_check_walks_the_whole_ancestor_chain(local_root, monkeypatch):
    """Round-13 #9: checking only the final directory is what was wrong before.

    A junction *above* the store redirects everything beneath it, so a check
    that stops at the leaf validates a path an attacker already controls.  This
    plants the reparse attribute on a grandparent and requires it to be caught.
    """

    from forecast import content_store

    nested = local_root / "a" / "b" / "objects"
    nested.mkdir(parents=True)
    grandparent = (local_root / "a").resolve()

    real_stat = os.stat

    def stat_with_reparse_on_grandparent(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if Path(path) == grandparent:
            class _Faked:
                st_file_attributes = content_store.FILE_ATTRIBUTE_REPARSE_POINT
            return _Faked()
        return result

    monkeypatch.setattr(content_store.os, "stat", stat_with_reparse_on_grandparent)

    with pytest.raises(ImmutabilityViolation) as excinfo:
        content_store.assert_no_reparse_ancestry(nested)
    assert str(grandparent) in str(excinfo.value)


def test_a_hard_linked_canonical_object_is_rejected(store):
    """Measured: link count goes 1 -> 2 the moment an alias exists.

    An alias can rewrite bytes after validation, so a read refuses it.
    """

    result = store.publish_content_object(b"aliasable")
    assert link_count(result.path) == 1
    assert store.read_validated(result.digest) == b"aliasable"

    alias = store.root / "alias"
    os.link(result.path, alias)
    assert link_count(result.path) == 2

    with pytest.raises(ImmutabilityViolation) as excinfo:
        store.read_validated(result.digest)
    assert "hard link" in str(excinfo.value)


# --------------------------------------------------------------------------
# Kill test: the store lease (§5.4, round-14 #4)
# --------------------------------------------------------------------------


def test_two_readers_hold_the_shared_lease_at_once(tmp_path):
    path = tmp_path / "store.lease"
    a = StoreLease(path).acquire(exclusive=False)
    b = StoreLease(path).acquire(exclusive=False)

    assert a.held and b.held
    a.release()
    b.release()


def test_a_sweep_cannot_take_the_exclusive_lease_under_a_reader(tmp_path):
    """Measured: `ERROR_LOCK_VIOLATION` (33).

    This is the mechanism the publisher/sweep race fix rests on (round-14 #4).
    """

    path = tmp_path / "store.lease"
    reader = StoreLease(path).acquire(exclusive=False)
    try:
        with pytest.raises(LeaseUnavailable):
            StoreLease(path).acquire(exclusive=True)
    finally:
        reader.release()

    sweeper = StoreLease(path).acquire(exclusive=True)
    assert sweeper.held, "the exclusive lease must become available once readers leave"
    sweeper.release()


def test_a_crashed_holder_releases_the_lease(tmp_path):
    """§5.4's whole argument for handle-held locks, run for real.

    An existence-based lock would leave every later run deadlocked until a human
    deleted a file, a failure indistinguishable from a hung job.
    """

    path = tmp_path / "store.lease"
    path.touch()
    child = tmp_path / "holder.py"
    child.write_text(
        "import os, sys\n"
        "sys.path.insert(0, r'%s')\n"
        "from forecast.content_store import StoreLease\n"
        "lease = StoreLease(r'%s').acquire(exclusive=True)\n"
        "print('held', flush=True)\n"
        "os._exit(9)\n" % (str(Path(__file__).resolve().parents[2]), str(path))
    )
    result = subprocess.run([sys.executable, str(child)], capture_output=True, text=True)
    assert result.stdout.strip() == "held"
    assert result.returncode == 9

    survivor = StoreLease(path).acquire(exclusive=True)
    assert survivor.held, "the OS must release a dead process's lock"
    survivor.release()


# --------------------------------------------------------------------------
# Kill test: the hash-linked DAG (§5.1, round-3 #5)
# --------------------------------------------------------------------------


def test_a_parent_is_publishable_only_after_its_children_verify(store):
    leaf = store.publish_content_object(b"part file")
    shard = Manifest(SHARD, "shard-0", (leaf.digest,), "schema-v1", "cache-key-v1")
    shard_digest = publish_manifest(store, shard)

    loaded = load_manifest(store, shard_digest)
    assert loaded.children == (leaf.digest,)
    assert loaded.kind == SHARD


def test_a_manifest_naming_an_absent_child_cannot_be_published(store):
    absent = digest_of(b"never written")
    shard = Manifest(SHARD, "shard-0", (absent,), "schema-v1", "cache-key-v1")

    with pytest.raises(StoreError):
        publish_manifest(store, shard)


def test_a_stage_manifest_must_bind_lineage_and_preflight(store):
    """§5.1: v3 bound only regions, so a stage could exist with no lineage."""

    thin = Manifest(STAGE, "stage", (), "schema-v1", "cache-key-v1", {"origin_datasets": []})
    with pytest.raises(ValidationError) as excinfo:
        publish_manifest(store, thin)
    assert "identity_edges" in str(excinfo.value)


def test_validate_dag_walks_the_whole_tree(store):
    leaf_a = store.publish_content_object(b"part a")
    leaf_b = store.publish_content_object(b"part b")
    shard = Manifest(SHARD, "s", (leaf_a.digest, leaf_b.digest), "schema-v1", "cache-key-v1")
    shard_digest = publish_manifest(store, shard)
    region = Manifest(REGION, "r", (shard_digest,), "schema-v1", "cache-key-v1")
    region_digest = publish_manifest(store, region)
    dataset = Manifest(ORIGIN_DATASET, "2020", (region_digest,), "schema-v1", "cache-key-v1")
    dataset_digest = publish_manifest(store, dataset)
    stage_digest = publish_manifest(store, _stage_manifest([dataset_digest]))

    report = validate_dag(store, stage_digest)
    assert report.manifests == 4
    assert report.leaves == 2
    assert report.depth == 5


def test_a_missing_child_makes_the_whole_dag_invalid_on_read(store):
    """§5.3: the power-loss case.  A parent survives, a child does not."""

    leaf = store.publish_content_object(b"part")
    shard = Manifest(SHARD, "s", (leaf.digest,), "schema-v1", "cache-key-v1")
    shard_digest = publish_manifest(store, shard)

    leaf.path.unlink()

    with pytest.raises(StoreError):
        validate_dag(store, shard_digest)


def test_budgets_are_bounded_not_merely_finite(store):
    """Round-14 #7: "finite" is not "bounded"."""

    leaf = store.publish_content_object(b"part")
    shard = Manifest(SHARD, "s", (leaf.digest,), "schema-v1", "cache-key-v1")
    shard_digest = publish_manifest(store, shard)
    region_digest = publish_manifest(
        store, Manifest(REGION, "r", (shard_digest,), "schema-v1", "cache-key-v1")
    )

    with pytest.raises(BudgetExceeded):
        validate_dag(store, region_digest, budget=Budget(max_depth=1))

    with pytest.raises(BudgetExceeded):
        validate_dag(store, region_digest, budget=Budget(max_nodes=1))

    assert validate_dag(store, region_digest).manifests == 2


def test_a_shared_child_is_hashed_once(store):
    """Memoization (round-13 #7): a wide DAG must not rehash quadratically."""

    leaf = store.publish_content_object(b"shared part")
    shard_digest = publish_manifest(
        store, Manifest(SHARD, "s", (leaf.digest,), "schema-v1", "cache-key-v1")
    )
    parent = Manifest(REGION, "r", (shard_digest, shard_digest), "schema-v1", "cache-key-v1")
    parent_digest = publish_manifest(store, parent)

    report = validate_dag(store, parent_digest)
    assert report.manifests == 2, "the shared shard must be visited once, not twice"


def test_manifest_parsing_is_strict(store):
    junk = store.publish_content_object(b'{"kind": "shard", "name": "x"}')
    with pytest.raises(ValidationError):
        load_manifest(store, junk.digest)


# --------------------------------------------------------------------------
# Kill test: generation naming and the derived high-water mark (round-14 #3)
# --------------------------------------------------------------------------


def test_generation_names_round_trip():
    assert generation_name(1) == "gen.0000000001"
    assert generation_number(generation_name(4321)) == 4321
    with pytest.raises(ValueError):
        generation_number("pointer.1")


def test_high_water_is_derived_from_names_and_a_hole_is_not_a_barrier(generations):
    """Round-13 #3 and round-14 #3 together.

    v13's "observe N, create N+1" deadlocks forever once an invalid N+1 exists.
    v14 fixed it with a persisted mark that had no protocol at all.  Here the
    mark is `max(name)` over records that are retained forever, so an invalid
    generation is a hole and the mark is unaffected -- and there is no second
    file whose consistency could be lost.
    """

    assert generations.high_water() == 0

    for number in (1, 2, 4):
        (generations.generations_dir / generation_name(number)).write_bytes(b"{}")

    assert generations.generation_numbers() == (1, 2, 4)
    assert generations.high_water() == 4, "a hole at 3 must not lower the mark"

    # Generation 4 is unparseable, i.e. invalid.  Allocation still moves past it.
    assert generations.high_water() + 1 == 5


def test_a_temporary_is_never_a_generation_candidate(generations):
    (generations.generations_dir / generation_name(1)).write_bytes(b"{}")
    (generations.generations_dir / ".tmp-1234-1-00000001").write_bytes(b"half written")

    assert generations.generation_numbers() == (1,)
    assert generations.high_water() == 1


# --------------------------------------------------------------------------
# Kill test: publication, the predecessor token and ABA (round-14 #2)
# --------------------------------------------------------------------------


def _publish(generations, payload=b"part", identity=IDENTITY, expected=None):
    lease = generations.shared_lease()
    try:
        leaf = generations.store.publish_content_object(payload)
        shard_digest = publish_manifest(
            generations.store,
            Manifest(SHARD, "s", (leaf.digest,), identity.schema_digest, identity.cache_key),
        )
        stage = _stage_manifest([shard_digest], identity=identity)
        stage_digest = publish_manifest(generations.store, stage)
        token = expected if expected is not None else generations.state_token(identity)
        return generations.publish_generation(stage_digest, identity, token, lease=lease)
    finally:
        lease.release()


def test_the_first_publication_is_generation_one_and_is_selectable(generations):
    record = _publish(generations)

    assert record.number == 1
    selection = generations.select(IDENTITY)
    assert selection.outcome == CURRENT
    assert selection.number == 1
    assert selection.root_digest == record.root_digest
    assert selection.rejected == ()


def test_a_second_publication_supersedes_the_first(generations):
    _publish(generations, b"first")
    second = _publish(generations, b"second")

    assert second.number == 2
    assert generations.select(IDENTITY).number == 2
    assert generations.high_water() == 2


def test_a_stale_build_is_aborted_and_never_renumbered(generations):
    """Round-13 #2: `CREATE_NEW` is not a compare-and-swap."""

    _publish(generations, b"first")
    stale = StateToken(current=None, high_water=0)

    with pytest.raises(PublicationAborted) as excinfo:
        _publish(generations, b"stale", expected=stale)
    assert "stale" in str(excinfo.value)
    assert generations.high_water() == 1, "an aborted build must not consume a name"


def test_the_predecessor_token_survives_aba_after_fallback(generations):
    """Round-14 #2, the critical v14's own fallback mechanism created.

    P records the state at generation 1.  Q publishes generation 2.  Generation
    2 is then invalidated (its DAG is lost, exactly the power-loss reordering
    §5.3 admits), so selection FALLS BACK to 1 and `current` reads 1 again --
    the value P recorded.  A token carrying only `current` would let P publish
    its stale DAG.  The high-water mark still reads 2, so P aborts.
    """

    _publish(generations, b"generation one")
    p_token = generations.state_token(IDENTITY)
    assert p_token == StateToken(current=1, high_water=1)

    q = _publish(generations, b"generation two")
    assert q.number == 2

    # Invalidate generation 2's DAG the way power loss can.
    for digest in generations.store.content_objects():
        if digest == q.root_digest:
            generations.store.path_for(digest).unlink()

    fell_back = generations.select(IDENTITY)
    assert fell_back.outcome == DEGRADED_FALLBACK
    assert fell_back.number == 1, "selection must fall back to the valid generation"

    observed = generations.state_token(IDENTITY)
    assert observed.current == p_token.current, "this is the ABA: current is 1 again"
    assert observed.high_water == 2, "but the mark moved, and never moves back"
    assert observed != p_token

    with pytest.raises(PublicationAborted):
        _publish(generations, b"P's stale DAG", expected=p_token)


def test_a_publisher_without_the_shared_lease_is_refused(generations):
    """Round-14 #4: the normative rule v14 deleted while the proof kept it."""

    lease = generations.shared_lease()
    leaf = generations.store.publish_content_object(b"part")
    shard_digest = publish_manifest(
        generations.store, Manifest(SHARD, "s", (leaf.digest,), "schema-v1", "cache-key-v1")
    )
    stage_digest = publish_manifest(generations.store, _stage_manifest([shard_digest]))
    token = generations.state_token(IDENTITY)
    lease.release()

    with pytest.raises(StoreError) as excinfo:
        generations.publish_generation(stage_digest, IDENTITY, token, lease=lease)
    assert "SHARED store lease" in str(excinfo.value)


def test_publishing_an_invalid_dag_is_refused_before_a_name_is_taken(generations):
    lease = generations.shared_lease()
    try:
        token = generations.state_token(IDENTITY)
        with pytest.raises(StoreError):
            generations.publish_generation(
                digest_of(b"never written"), IDENTITY, token, lease=lease
            )
    finally:
        lease.release()

    assert generations.high_water() == 0, "a refused publication consumes no name"


# --------------------------------------------------------------------------
# Kill test: selection, fallback and identity (round-13 #4, #8)
# --------------------------------------------------------------------------


def test_fallback_names_every_rejected_generation_with_a_reason(generations):
    _publish(generations, b"good")
    bad = _publish(generations, b"bad")
    generations.store.path_for(bad.root_digest).unlink()

    selection = generations.select(IDENTITY)
    assert selection.outcome == DEGRADED_FALLBACK
    assert selection.number == 1
    assert selection.fallback_depth == 1
    assert selection.rejected[0].number == 2
    assert "DAG invalid" in selection.rejected[0].reason


def test_a_cryptographically_valid_generation_with_the_wrong_identity_is_rejected(
    generations,
):
    """Round-13 #8: validity is not usability."""

    other = DatasetIdentity("specification_w_osm", "schema-v2", "cache-key-v2")
    _publish(generations, b"v1 content", identity=IDENTITY)
    _publish(generations, b"v2 content", identity=other)

    selection = generations.select(IDENTITY)
    assert selection.number == 1
    assert "identity mismatch" in selection.rejected[0].reason
    assert selection.rejected[0].identity_mismatch is True

    # And the store is perfectly usable for the other consumer.
    assert generations.select(other).number == 2


def test_another_dataset_above_this_one_is_not_degradation(generations):
    """Measured on the corpus store once §5.5's seal gave it a second dataset.

    Generation 4 is pass-1's own current generation and nothing about it is
    broken; the seal simply sits above it.  Reporting `DEGRADED_FALLBACK` there
    would make the signal that means "something below the high-water mark is
    broken" fire permanently on a healthy store -- for every dataset except
    whichever was published last.
    """

    other = DatasetIdentity("specification_w_osm", "schema-v2", "cache-key-v2")
    _publish(generations, b"mine", identity=IDENTITY)
    _publish(generations, b"theirs", identity=other)

    selection = generations.select(IDENTITY)

    assert selection.outcome == CURRENT
    assert selection.degraded is False
    assert selection.fallback_depth == 0, "skipped, not fallen past"
    assert len(selection.rejected) == 1, "and still reported, in full"


def test_a_real_fallback_is_still_degraded_with_another_dataset_present(generations):
    """The correction must not suppress the signal it exists to preserve."""

    other = DatasetIdentity("specification_w_osm", "schema-v2", "cache-key-v2")
    _publish(generations, b"good")
    broken = _publish(generations, b"broken")
    generations.store.path_for(broken.root_digest).unlink()
    _publish(generations, b"theirs", identity=other)

    selection = generations.select(IDENTITY)

    assert selection.outcome == DEGRADED_FALLBACK
    assert selection.number == 1
    assert selection.fallback_depth == 1, "one real fallback; the other dataset is not one"
    assert len(selection.rejected) == 2


def test_no_valid_generation_is_a_hard_error_not_an_empty_success(generations):
    with pytest.raises(NoValidGeneration):
        generations.select(IDENTITY)


def test_selection_refuses_a_lease_that_is_not_held(generations):
    """Round-13 #4: the hazard is selecting with NO lease.

    v13 let a reader select and then install a lease, so a sweep could collect
    the selection in the gap.  A released lease is that same gap wearing a
    lease-shaped object, so it is refused.
    """

    _publish(generations, b"content")
    lease = generations.shared_lease()
    lease.release()

    with pytest.raises(StoreError) as excinfo:
        generations.select(IDENTITY, lease=lease)
    assert "HELD" in str(excinfo.value)


def test_a_sweeper_can_select_under_its_own_exclusive_lease(generations):
    """Shared is not a requirement; a HELD lease is.

    `LockFileEx` ranges are per handle, so a process holding the exclusive lease
    cannot also take a shared one -- insisting on shared made selection
    impossible from inside a sweep, which is where establishing an anchor
    happens.  Exclusive is strictly stronger here: nothing else can be
    collecting.
    """

    _publish(generations, b"content")
    exclusive = generations.exclusive_lease()
    try:
        selection = generations.select(IDENTITY, lease=exclusive)
        assert selection.number == 1
        assert selection.outcome == CURRENT
    finally:
        exclusive.release()


def test_the_candidate_set_is_capped(generations):
    from forecast.generations import MAX_CANDIDATE_GENERATIONS

    for number in range(1, MAX_CANDIDATE_GENERATIONS + 10):
        (generations.generations_dir / generation_name(number)).write_bytes(b"{}")

    assert len(generations._candidates()) == MAX_CANDIDATE_GENERATIONS


# --------------------------------------------------------------------------
# Kill test: retirement, anchor and sweep (round-13 #6, #10; round-14 #5)
# --------------------------------------------------------------------------


def test_a_retired_generation_leaves_the_mark_intact(generations):
    """Round-13 #10: deleting the file would permit numeric reuse."""

    _publish(generations, b"first")
    _publish(generations, b"second")

    lease = generations.exclusive_lease()
    try:
        generations.retire(1, lease=lease)
    finally:
        lease.release()

    assert 1 in generations.retired()
    assert generations.high_water() == 2
    assert (generations.generations_dir / generation_name(1)).exists(), (
        "the record is retained so the number can never be reused"
    )


def test_a_retired_generation_is_not_a_fallback_candidate(generations):
    first = _publish(generations, b"first")
    second = _publish(generations, b"second")
    generations.store.path_for(second.root_digest).unlink()

    lease = generations.exclusive_lease()
    try:
        generations.retire(1, lease=lease)
    finally:
        lease.release()

    with pytest.raises(NoValidGeneration):
        generations.select(IDENTITY)


def test_a_sweep_without_an_anchor_is_refused(generations):
    _publish(generations, b"content")
    lease = generations.exclusive_lease()
    try:
        assert generations.anchor() is None
        with pytest.raises(SweepRefused):
            generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()


def test_establishing_an_anchor_on_a_fresh_store_yields_none(generations):
    lease = generations.exclusive_lease()
    try:
        assert generations.establish_anchor(IDENTITY, lease=lease) is None
    finally:
        lease.release()


def test_a_sweep_collects_only_unreachable_objects(generations):
    """The whole point: garbage goes, the live DAG stays byte-identical."""

    first = _publish(generations, b"superseded content")
    second = _publish(generations, b"live content")

    lease = generations.exclusive_lease()
    try:
        generations.retire(1, lease=lease)
        assert generations.establish_anchor(IDENTITY, lease=lease) == 2
        report = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    assert report["anchor"] == 2
    assert first.root_digest in report["deleted"]
    assert second.root_digest not in report["deleted"]
    assert report["freed_bytes"] > 0

    selection = generations.select(IDENTITY)
    assert selection.number == 2
    assert selection.outcome == CURRENT
    assert validate_dag(generations.store, second.root_digest).manifests == 2


def test_a_pinned_generation_survives_a_sweep(generations):
    first = _publish(generations, b"pinned content")
    _publish(generations, b"newer content")

    shared = generations.shared_lease()
    try:
        generations.pin("build-7", 1, lease=shared)
    finally:
        shared.release()

    lease = generations.exclusive_lease()
    try:
        generations.retire(1, lease=lease)
        generations.establish_anchor(IDENTITY, lease=lease)
        report = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    assert first.root_digest not in report["deleted"], (
        "a pin must keep its generation's objects alive even once retired"
    )
    assert validate_dag(generations.store, first.root_digest).manifests == 2


def test_a_sweep_reaps_orphaned_temporaries(generations):
    _publish(generations, b"content")
    orphan = generations.store.root / ".tmp-9999-1-00000001"
    orphan.write_bytes(b"left behind")

    lease = generations.exclusive_lease()
    try:
        generations.establish_anchor(IDENTITY, lease=lease)
        report = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    assert orphan.name in report["orphans_reaped"]
    assert not orphan.exists()


def test_collection_requires_the_exclusive_lease(generations):
    _publish(generations, b"content")
    shared = generations.shared_lease()
    try:
        with pytest.raises(StoreError):
            generations.sweep(IDENTITY, lease=shared)
    finally:
        shared.release()


def test_retirement_requires_the_exclusive_lease(generations):
    _publish(generations, b"content")
    shared = generations.shared_lease()
    try:
        with pytest.raises(StoreError):
            generations.retire(1, lease=shared)
    finally:
        shared.release()
