"""§5 crash safety: kills injected into the real primitive, on real NTFS.

The Proof section's remaining §5 obligations -- injected kills at every step,
an interrupted sweep, and a simulated reordered-namespace power loss.  These
were the gap left when §5 was built: every *mechanism* had been probed, but the
scenarios that compose them had not been run.

**The kill is a separate process calling `os._exit` inside the real Win32
call**, not an exception in this one.  An exception unwinds, runs `finally`
blocks and closes handles -- which is precisely the tidying a killed process
does not get to do, so it would prove the opposite of what is claimed.

**The invariant asserted at every kill point is the one §5.2 promises:** the
highest generation always names a fully-written DAG, because the DAG is written
before the generation record is created.  So after any kill, a reader either
gets a complete validated DAG or a hard error -- never a partial read.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from forecast.content_store import TEMPORARY_PREFIX
from forecast.generations import (
    DatasetIdentity,
    GenerationStore,
    NoValidGeneration,
    SweepRefused,
)
from forecast.manifests import Manifest, SHARD, STAGE, publish_manifest, validate_dag
from forecast.tests.crash_worker import DIED, IDENTITY, KILL_POINTS, NO_KILL

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="§5 is a Windows/NTFS design"
)

WORKER = Path(__file__).resolve().parent / "crash_worker.py"


@pytest.fixture
def root(tmp_path):
    assert "onedrive" not in str(tmp_path).lower(), (
        f"§5 requires a local NTFS volume; got {tmp_path}"
    )
    return tmp_path / "store"


def kill_at(root: Path, kill_point: str, payload: bytes = b"crash payload"):
    """Run a publisher that dies at `kill_point`.  Returns its exit code."""

    result = subprocess.run(
        [sys.executable, str(WORKER), str(root), kill_point, payload.decode()],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def assert_never_partial(generations: GenerationStore) -> str:
    """A reader gets a complete validated DAG or a hard error.  Never a slice.

    This is the assertion the whole file exists for, so it is deliberately
    positive: when a generation IS returned, its entire DAG is revalidated here
    rather than trusted.
    """

    try:
        selection = generations.select(IDENTITY)
    except NoValidGeneration:
        return "no generation"

    report = validate_dag(generations.store, selection.root_digest)
    assert report.manifests >= 2, (
        "a selected generation must name the full manifest chain, not a fragment"
    )
    assert report.leaves >= 1
    return f"generation {selection.number}"


# --------------------------------------------------------------------------
# A kill at every step of the publication path
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kill_point", KILL_POINTS)
def test_a_kill_at_any_step_never_leaves_a_partial_read(root, kill_point):
    """The core §5.2 crash-safety claim, run once per injection point."""

    result = kill_at(root, kill_point)
    assert result.returncode == DIED, (
        f"worker did not die at {kill_point}: rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )

    generations = GenerationStore(root)
    assert_never_partial(generations)


@pytest.mark.parametrize("kill_point", KILL_POINTS)
def test_a_kill_never_publishes_a_generation_before_its_dag(root, kill_point):
    """Ordering is the whole guarantee: DAG first, then the name that finds it.

    If a generation record could appear before its artifacts were durable, this
    is the test that would catch it -- every generation present after the kill
    must validate completely.
    """

    kill_at(root, kill_point)
    generations = GenerationStore(root)

    for number in generations.generation_numbers():
        record = generations.read_generation(number)
        report = validate_dag(generations.store, record.root_digest)
        assert report.manifests >= 2, (
            f"generation {number} exists but names an incomplete DAG after a "
            f"kill at {kill_point}"
        )


@pytest.mark.parametrize("kill_point", KILL_POINTS)
def test_a_kill_never_leaves_a_temporary_in_a_canonical_namespace(root, kill_point):
    """A half-written file must not be reachable as an object or a generation."""

    kill_at(root, kill_point)
    generations = GenerationStore(root)

    for digest in generations.store.content_objects():
        assert not digest.startswith(TEMPORARY_PREFIX)
        # Canonical objects are named by their own digest, so a truncated file
        # left by a kill cannot masquerade as one.
        generations.store.read_validated(digest)

    for number in generations.generation_numbers():
        assert (generations.generations_dir / f"gen.{number:010d}").exists()


@pytest.mark.parametrize("kill_point", KILL_POINTS)
def test_the_store_still_accepts_a_publisher_after_a_kill(root, kill_point):
    """No deadlock: the dead publisher's lease died with it (§5.4).

    An existence-based lock would strand the store here, and the failure would
    look exactly like a hung job.
    """

    kill_at(root, kill_point)

    result = kill_at(root, NO_KILL, payload=b"the recovery publication")
    assert result.returncode == 0, (
        f"a later publisher could not proceed after a kill at {kill_point}: "
        f"{result.stderr}"
    )

    generations = GenerationStore(root)
    selection = generations.select(IDENTITY)
    assert validate_dag(generations.store, selection.root_digest).manifests >= 2


def test_a_kill_after_the_generation_rename_is_a_complete_publication(root):
    """The narrow window that matters: the name exists, the process is gone.

    Nothing remains to be done after the rename, so this must be a *successful*
    publication rather than a survivable one.
    """

    result = kill_at(root, "after_generation_rename", payload=b"committed anyway")
    assert result.returncode == DIED

    generations = GenerationStore(root)
    selection = generations.select(IDENTITY)
    assert selection.number == 1
    assert validate_dag(generations.store, selection.root_digest).manifests == 2


def test_the_high_water_mark_never_regresses_across_kills(root):
    """Names are consumed monotonically however many publishers die."""

    marks = []
    for index, kill_point in enumerate(KILL_POINTS):
        kill_at(root, kill_point, payload=f"payload {index}".encode())
        marks.append(GenerationStore(root).high_water())

    assert marks == sorted(marks), f"high-water mark regressed across kills: {marks}"


# --------------------------------------------------------------------------
# Simulated reordered-namespace power loss (§5.3)
# --------------------------------------------------------------------------


def _publish(generations, payload: bytes):
    lease = generations.shared_lease()
    try:
        leaf = generations.store.publish_content_object(payload)
        shard = publish_manifest(
            generations.store,
            Manifest(SHARD, "s", (leaf.digest,), "schema-v1", "cache-key-v1"),
        )
        stage = publish_manifest(
            generations.store,
            Manifest(
                STAGE, "stage", (shard,), "schema-v1", "cache-key-v1",
                {
                    "origin_datasets": ["2020", "2021", "2022"],
                    "identity_edges": "edges",
                    "presence_table": "presence",
                    "duplicate_group_preflight": "preflight",
                    "coverage_margins": "margins",
                },
            ),
        )
        token = generations.state_token(IDENTITY)
        return generations.publish_generation(stage, IDENTITY, token, lease=lease), leaf.digest
    finally:
        lease.release()


def test_power_loss_losing_a_deep_leaf_invalidates_the_generation_and_falls_back(root):
    """§5.3's honest limit, made concrete.

    NTFS may persist namespace changes out of order, so a generation record can
    survive while an artifact it transitively references does not.  The
    generation must then FAIL validation -- not return the parts that survived --
    and the reader falls back to one that does validate.
    """

    generations = GenerationStore(root)
    first, _ = _publish(generations, b"the durable generation")
    second, lost_leaf = _publish(generations, b"the generation power loss ate")

    # The leaf is two levels below the generation record: the reordering has to
    # be caught by revalidating the whole DAG, not by checking the root.
    generations.store.path_for(lost_leaf).unlink()

    selection = generations.select(IDENTITY)
    assert selection.number == first.number, "must fall back to the intact generation"
    assert selection.degraded
    assert selection.rejected[0].number == second.number
    assert "DAG invalid" in selection.rejected[0].reason

    # And the fallback is a complete read, not a salvaged one.
    assert validate_dag(generations.store, selection.root_digest).manifests == 2


def test_power_loss_losing_every_generation_is_a_hard_error(root):
    """Never a silent partial read -- if nothing validates, nothing is returned."""

    generations = GenerationStore(root)
    _, leaf = _publish(generations, b"only generation")
    generations.store.path_for(leaf).unlink()

    with pytest.raises(NoValidGeneration):
        generations.select(IDENTITY)


def test_a_lost_generation_record_leaves_the_store_usable(root):
    """The other reordering direction: the record vanishes, artifacts survive."""

    generations = GenerationStore(root)
    first, _ = _publish(generations, b"first")
    second, _ = _publish(generations, b"second")
    (generations.generations_dir / f"gen.{second.number:010d}").unlink()

    selection = generations.select(IDENTITY)
    assert selection.number == first.number
    assert validate_dag(generations.store, selection.root_digest).manifests == 2


# --------------------------------------------------------------------------
# Interrupted sweep
# --------------------------------------------------------------------------


def test_an_interrupted_sweep_is_harmless_and_resumable(root):
    """Collection deletes only unreachable objects, so stopping part-way is safe.

    Modelled by deleting a subset of what a sweep would have collected and then
    letting a real sweep finish: the live generation must read identically
    before, between and after.
    """

    generations = GenerationStore(root)
    first, _ = _publish(generations, b"superseded")
    second, _ = _publish(generations, b"live")

    lease = generations.exclusive_lease()
    try:
        generations.retire(first.number, lease=lease)
        assert generations.establish_anchor(IDENTITY, lease=lease) == second.number
        doomed = sorted(
            set(generations.store.content_objects()) - generations.reachable_objects()
        )
        assert doomed, "the fixture must actually produce garbage to collect"

        # Interrupt: only the first unreachable object is collected.
        generations.store.path_for(doomed[0]).unlink()

        # Selected under the sweeper's own exclusive lease -- a shared one is
        # unobtainable here, `LockFileEx` ranges being per handle.
        mid = generations.select(IDENTITY, lease=lease)
        assert mid.number == second.number
        assert validate_dag(generations.store, mid.root_digest).manifests == 2

        report = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    after = generations.select(IDENTITY)
    assert after.number == second.number
    assert validate_dag(generations.store, after.root_digest).manifests == 2
    assert all(d not in generations.store.content_objects() for d in doomed)
    assert report["anchor"] == second.number


@pytest.mark.parametrize("kill_point", ["after_create", "after_write", "after_flush"])
def test_a_crashed_publishers_temporary_is_reaped_by_a_later_sweep(root, kill_point):
    """The loop between a crash and GC, closed.

    A publisher killed while its temporary was open cannot delete it -- the
    process is gone.  Measured across the three pre-rename kill points, each
    leaves exactly one orphan.  Nothing else may collect it, because reaping
    happens only under the exclusive lease; a sweep is what finally does.
    """

    kill_at(root, kill_point)
    generations = GenerationStore(root)
    stranded = generations.store.orphans()
    assert len(stranded) == 1, (
        f"a kill at {kill_point} should strand exactly one temporary; got {stranded}"
    )

    # A crashed publisher leaves no generation, so give the store something an
    # anchor can be established on before collecting.
    assert kill_at(root, NO_KILL, payload=b"recovery").returncode == 0

    lease = generations.exclusive_lease()
    try:
        assert generations.establish_anchor(IDENTITY, lease=lease) is not None
        report = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    assert stranded[0].name in report["orphans_reaped"]
    assert generations.store.orphans() == ()
    assert not stranded[0].exists()

    # And the recovery publication is untouched by the reaping.
    selection = generations.select(IDENTITY)
    assert validate_dag(generations.store, selection.root_digest).manifests == 2


def test_a_sweep_is_idempotent(root):
    """Running it twice collects nothing the second time and breaks nothing."""

    generations = GenerationStore(root)
    first, _ = _publish(generations, b"superseded")
    second, _ = _publish(generations, b"live")

    lease = generations.exclusive_lease()
    try:
        generations.retire(first.number, lease=lease)
        generations.establish_anchor(IDENTITY, lease=lease)
        one = generations.sweep(IDENTITY, lease=lease)
        two = generations.sweep(IDENTITY, lease=lease)
    finally:
        lease.release()

    assert one["deleted"], "the first sweep must actually collect something"
    assert two["deleted"] == [], "the second must find nothing left to collect"
    assert generations.select(IDENTITY).number == second.number


def test_a_sweep_cannot_run_while_a_publisher_holds_the_shared_lease(root):
    """Round-14 #4's race, closed by the lease rather than by timing.

    The publisher's shared lease is what makes the sweeper's exclusive request
    fail, so the sweep never starts mid-publication.
    """

    generations = GenerationStore(root)
    _publish(generations, b"content")

    publisher = generations.shared_lease()
    try:
        from forecast.content_store import LeaseUnavailable

        with pytest.raises(LeaseUnavailable):
            generations.exclusive_lease()
    finally:
        publisher.release()

    sweeper = generations.exclusive_lease()
    assert sweeper.held
    sweeper.release()
