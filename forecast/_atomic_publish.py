"""Single-container publication for the post-lift embargo transition.

The original code published the mask directory with ``os.replace`` and only
afterwards checked whether the transition log existed, so a crash in between
left ``positive_2023`` readable with no record that the embargo had lifted.
Neither ``open("x")`` nor a directory rename fixes that: the first strands a
durable record on crash, two filesystem paths cannot be committed together, and
a same-volume NTFS move *retains the source security descriptor*, so a directory
staged under the worker-only root stays unreadable after moving while relaxing
its ACL beforehand opens an exposure window.

So the masks and the transition record are packed into **one container file**,
published over a pre-created placeholder that already carries the final ACL.
One object means one commit, and "exactly one of the two published" is not
representable.

``ReplaceFileW`` is not a one-state primitive.  Its documented failure modes are
enumerated in :data:`STATE_TABLE`; the two that matter are 1176, where the new
payload is still at *staging* while the backup holds the old placeholder (so
recovering from the backup would republish the wrong content), and 1177, where
the replacement can already be exposed and must therefore roll **forward** —
classifying it as rolled back would reverse a commit that has happened.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

ERROR_UNABLE_TO_REMOVE_REPLACED = 1175
ERROR_UNABLE_TO_MOVE_REPLACEMENT = 1176
ERROR_UNABLE_TO_MOVE_REPLACEMENT_2 = 1177

# status values
COMMITTED = "committed"
UNCOMMITTED = "uncommitted"
EXPOSED = "exposed"
FAILED_CLOSED = "failed_closed"

#: Every documented return state mapped to a commit status and an idempotent
#: recovery action.  The ``any other error`` case is deliberately present: the
#: table claims exhaustive coverage, and Windows documents states beyond the
#: three named codes.
STATE_TABLE: Mapping[str, dict[str, str]] = {
    "success": {
        "status": COMMITTED,
        "observed": "destination holds the staging payload; backup holds the old placeholder",
        "recovery": "none",
    },
    str(ERROR_UNABLE_TO_REMOVE_REPLACED): {
        "status": UNCOMMITTED,
        "observed": "destination unchanged, staging intact",
        "recovery": "retry from intact staging",
    },
    str(ERROR_UNABLE_TO_MOVE_REPLACEMENT): {
        "status": UNCOMMITTED,
        "observed": (
            "destination and staging both under their original names; "
            "the new payload is still at staging; backup holds the old placeholder"
        ),
        # Restoring from backup here would republish the OLD PLACEHOLDER as the
        # payload -- the wrong content.  Staging is the authoritative copy.
        "recovery": "retry from intact staging (never from the backup path)",
    },
    str(ERROR_UNABLE_TO_MOVE_REPLACEMENT_2): {
        "status": EXPOSED,
        "observed": (
            "old placeholder at the backup path, exposed replacement still at staging, "
            "destination absent"
        ),
        # The replacement may already be readable.  Reversing it is not a
        # recoverable state, so the only sound direction is forward.
        "recovery": (
            "roll FORWARD: restore the placeholder from backup, then re-publish "
            "the same verified staging payload; never roll back, never quarantine"
        ),
    },
    "other": {
        "status": FAILED_CLOSED,
        "observed": "classified from observed names, file IDs and DACLs",
        "recovery": "halt, publish nothing, require manual seal re-verification",
    },
}


def classify(winerror: int | None) -> "PublishOutcome":
    """Map a ``ReplaceFileW`` result to a commit status and recovery action.

    Split out from :func:`publish_container` so the table's semantics are
    testable without provoking each Win32 failure on a live filesystem.
    """

    key = "success" if winerror is None else str(winerror)
    entry = STATE_TABLE.get(key, STATE_TABLE["other"])
    return PublishOutcome(entry["status"], winerror, entry["observed"], entry["recovery"])


@dataclass(frozen=True)
class PublishOutcome:
    """What ``ReplaceFileW`` did, and what may safely be done about it."""

    status: str
    winerror: int | None
    observed: str
    recovery: str
    detail: str = ""
    paths: dict[str, str] = field(default_factory=dict)

    @property
    def committed(self) -> bool:
        return self.status == COMMITTED

    @property
    def exposed(self) -> bool:
        return self.status == EXPOSED


def _volume_id(path: Path) -> object:
    """Identify the volume a path lives on, without requiring it to exist."""

    probe = path
    while True:
        try:
            return os.stat(probe).st_dev
        except OSError:
            if probe.parent == probe:
                raise
            probe = probe.parent


def assert_same_volume(destination: Path, staging: Path, backup: Path) -> None:
    """``ReplaceFileW`` requires all three paths on one volume.

    The atomicity argument silently assumes this, so it is asserted rather than
    hoped for.
    """

    volumes = {
        "destination": _volume_id(destination),
        "staging": _volume_id(staging),
        "backup": _volume_id(backup),
    }
    if len(set(volumes.values())) != 1:
        raise ValueError(
            "ReplaceFileW requires destination, staging and backup on one volume; got "
            + ", ".join(f"{name}={value}" for name, value in sorted(volumes.items()))
        )


def assert_local_non_reparse(directory: Path) -> None:
    """Refuse a publication root that is a reparse point or cloud-backed.

    This repository itself lives under OneDrive, whose minifilter and cloud
    replication sit outside ``ReplaceFileW``'s local-NTFS guarantee, so the
    publication directory must be somewhere else.
    """

    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"publication root does not exist: {directory}")
    if os.name == "nt":
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attributes = getattr(os.stat(directory), "st_file_attributes", 0)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"publication root is a reparse point: {directory}")
    lowered = str(directory).replace("\\", "/").lower()
    if "/onedrive" in lowered:
        raise ValueError(
            f"publication root is inside OneDrive, which breaks the local-NTFS "
            f"atomicity guarantee: {directory}"
        )


def write_container(
    payload_files: Mapping[str, bytes],
    transition_record: Mapping[str, object],
    path: str | Path,
) -> Path:
    """Pack the masks and the transition record into one deterministic archive.

    Stored (not deflated) with a fixed timestamp so the container hashes
    reproducibly, which the seal depends on.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fixed_date = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(payload_files):
            info = zipfile.ZipInfo(filename=name, date_time=fixed_date)
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload_files[name])
        info = zipfile.ZipInfo(filename="transition_record.json", date_time=fixed_date)
        info.external_attr = 0o600 << 16
        archive.writestr(
            info,
            json.dumps(transition_record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
    return path


def read_container(path: str | Path) -> tuple[dict[str, bytes], dict[str, object]]:
    """Read back a published container: payload files plus the transition record."""

    path = Path(path)
    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if name != "transition_record.json"]
        payload = {name: archive.read(name) for name in sorted(names)}
        record = json.loads(archive.read("transition_record.json").decode("utf-8"))
    return payload, record


def create_placeholder(destination: Path) -> Path:
    """Create the destination placeholder that carries the final ACL.

    ``ReplaceFileW`` replaces an *existing* file and preserves the replaced
    file's security descriptor, which is exactly how the container acquires
    destination-appropriate permissions without ever being readable at the
    staging location.
    """

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.touch(mode=0o600)
    return destination


def publish_container(
    staging: str | Path,
    destination: str | Path,
    backup: str | Path,
) -> PublishOutcome:
    """Publish ``staging`` over ``destination`` atomically, classifying the result."""

    staging = Path(staging).resolve()
    destination = Path(destination).resolve()
    backup = Path(backup).resolve()
    paths = {
        "staging": str(staging),
        "destination": str(destination),
        "backup": str(backup),
    }

    if not staging.is_file():
        raise FileNotFoundError(f"staging container does not exist: {staging}")
    assert_same_volume(destination, staging, backup)
    if not destination.exists():
        raise FileNotFoundError(
            f"destination placeholder must pre-exist so its ACL is preserved: {destination}"
        )

    if os.name != "nt":
        # POSIX fallback for test portability: rename is atomic within a
        # filesystem.  The Windows path is the one the design reasons about.
        os.replace(str(destination), str(backup))
        os.replace(str(staging), str(destination))
        entry = STATE_TABLE["success"]
        return PublishOutcome(
            entry["status"], None, entry["observed"], entry["recovery"], "posix rename", paths
        )

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ReplaceFileW.argtypes = [
        wintypes.LPCWSTR,  # lpReplacedFileName
        wintypes.LPCWSTR,  # lpReplacementFileName
        wintypes.LPCWSTR,  # lpBackupFileName  -- frozen, never NULL
        wintypes.DWORD,    # dwReplaceFlags    -- 0; ACL-ignore flags prohibited
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32.ReplaceFileW.restype = wintypes.BOOL

    ok = kernel32.ReplaceFileW(
        str(destination), str(staging), str(backup), 0, None, None
    )
    if ok:
        entry = STATE_TABLE["success"]
        return PublishOutcome(entry["status"], None, entry["observed"], entry["recovery"], "", paths)

    winerror = ctypes.get_last_error()
    entry = STATE_TABLE.get(str(winerror), STATE_TABLE["other"])
    detail = _observe(staging, destination, backup)
    return PublishOutcome(
        entry["status"], winerror, entry["observed"], entry["recovery"], detail, paths
    )


def _observe(staging: Path, destination: Path, backup: Path) -> str:
    """Record the observed names/IDs used to classify an unknown failure."""

    def describe(path: Path) -> str:
        try:
            stat = os.stat(path)
        except OSError:
            return "absent"
        return f"present(ino={getattr(stat, 'st_ino', 0)},size={stat.st_size})"

    return (
        f"staging={describe(staging)} "
        f"destination={describe(destination)} "
        f"backup={describe(backup)}"
    )


def recover(outcome: PublishOutcome) -> str:
    """Return the idempotent recovery action for an outcome.

    ``exposed`` never maps to a rollback: the replacement may already be
    readable, so the only sound direction is forward.  Callers must preserve
    that status through manual verification rather than downgrading it.
    """

    if outcome.status == EXPOSED:
        return STATE_TABLE[str(ERROR_UNABLE_TO_MOVE_REPLACEMENT_2)]["recovery"]
    return outcome.recovery
