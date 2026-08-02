"""A publisher that dies at a named point inside the REAL §5 primitive.

Spawned by `test_crash_injection.py`.  Run as a script, never *executed* in the
suite's own process -- the whole point is that it is a separate process that can
be killed without unwinding, which is what `os._exit` gives us and what an
exception inside the test process could never simulate.  The test imports this
module for its constants only; nothing below `main()` runs on import.

**The kill is injected by wrapping the Win32 calls the real primitive makes**,
not by re-implementing the primitive with kill points in it.  A
re-implementation would prove that a *copy* of the publication path is
crash-safe, which is worth nothing.  Here `publish_content_object` and
`publish_generation` run exactly as production runs them, and the process
disappears mid-call.

Exit code 70 means "died at the requested point", so a test can tell a
successful injection from a worker that crashed for some other reason.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from forecast import content_store as cs  # noqa: E402
from forecast.content_store import ContentStore  # noqa: E402
from forecast.generations import DatasetIdentity, GenerationStore  # noqa: E402
from forecast.manifests import Manifest, SHARD, STAGE, publish_manifest  # noqa: E402

DIED = 70

#: Run the publication through to completion with nothing patched.  Used by the
#: recovery tests, and the only argument for which exit 0 is correct.
NO_KILL = "no_kill"

IDENTITY = DatasetIdentity(
    dataset="specification_w_osm",
    schema_digest="schema-v1",
    cache_key="cache-key-v1",
)

#: Every point at which a kill is injected, in the order the primitive reaches
#: them.  `*_generation` variants fire only while the generation record -- not
#: an artifact -- is being written, which is the ordering §5.2 depends on.
KILL_POINTS = (
    "after_create",
    "after_write",
    "after_flush",
    "after_rename",
    "after_objects",
    "before_generation_rename",
    "after_generation_rename",
    "after_generation",
)


def _die():
    # os._exit, not sys.exit: no unwinding, no atexit, no buffered flush.  A
    # process killed by the OS does not get to tidy up, so neither does this.
    os._exit(DIED)


def _targets_generation(target) -> bool:
    return Path(target).name.startswith("gen.")


def install(kill_point: str) -> None:
    """Wrap the real Win32 entry points so the worker dies inside them.

    The `after_objects`, `after_generation` and :data:`NO_KILL` points need no
    wrapper -- :func:`main` reaches them directly -- so this installing nothing
    for them is correct, not an oversight.
    """

    real_create = cs._k32.CreateFileW
    real_write = cs._k32.WriteFile
    real_flush = cs._k32.FlushFileBuffers
    real_rename = cs._rename_through_handle

    if kill_point == "after_create":
        def create(*args):
            handle = real_create(*args)
            # Only die creating a temporary for writing, not on a read open.
            if args[1] & cs.DELETE:
                _die()
            return handle

        cs._k32.CreateFileW = create

    elif kill_point == "after_write":
        def write(*args):
            real_write(*args)
            _die()

        cs._k32.WriteFile = write

    elif kill_point == "after_flush":
        def flush(handle):
            real_flush(handle)
            _die()

        cs._k32.FlushFileBuffers = flush

    elif kill_point == "after_rename":
        def rename(handle, target):
            real_rename(handle, target)
            # The canonical name now exists and the handle is still open --
            # the narrowest window the primitive has.
            _die()

        cs._rename_through_handle = rename

    elif kill_point == "before_generation_rename":
        def rename(handle, target):
            if _targets_generation(target):
                _die()
            return real_rename(handle, target)

        cs._rename_through_handle = rename

    elif kill_point == "after_generation_rename":
        def rename(handle, target):
            result = real_rename(handle, target)
            if _targets_generation(target):
                _die()
            return result

        cs._rename_through_handle = rename


def main() -> int:
    root = sys.argv[1]
    kill_point = sys.argv[2]
    payload = sys.argv[3].encode()

    # A name that reaches neither `install` nor a branch below would publish
    # cleanly and exit 0, and every invariant the caller then asserted about the
    # crash would hold vacuously.  Refuse the argument instead.
    if kill_point not in KILL_POINTS and kill_point != NO_KILL:
        raise SystemExit(f"unknown kill point {kill_point!r}")

    generations = GenerationStore(root)
    install(kill_point)

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

        if kill_point == "after_objects":
            # Every artifact is durable; no generation names them yet.
            _die()

        token = generations.state_token(IDENTITY)
        generations.publish_generation(stage, IDENTITY, token, lease=lease)

        if kill_point == "after_generation":
            _die()
    finally:
        lease.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
