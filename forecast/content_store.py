"""The §5.2 content-addressed store: one write primitive, and the store lease.

Implements §5.2 and §5.4 of `OSM-NORMALISATION-PLAN.md`.

**Every mechanism here was run against real NTFS before it was written**, because
fourteen review rounds could not settle §5 in prose and rounds 13 and 14 both
sourced their criticals from the previous round's own fixes.  What the probes
found:

**The rename must go through a LIVE handle opened with `DELETE` access**
(round-14 #1).  v14 froze "flush, **close**, then rename by
`SetFileInformationByHandle(FileRenameInfo)`", and that call is impossible: the
API renames *the file the handle identifies*.  Measured -- a closed handle fails
with `ERROR_INVALID_HANDLE` (6).  And a fact no review round raised: a handle
opened `GENERIC_WRITE` **without** `DELETE` fails with `ERROR_ACCESS_DENIED` (5),
so that access right is load-bearing rather than incidental.  Order is therefore
open(write|DELETE) -> write -> flush -> **rename through that handle** -> close.

**`ReplaceIfExists = FALSE` is genuinely non-destructive.**  Measured: renaming
onto an existing name fails with `ERROR_ALREADY_EXISTS` (183) and the winner's
bytes are untouched.  The `TRUE` variant silently overwrote the canonical file in
the same probe, which is why :data:`REPLACE_IF_EXISTS` is frozen `False` and
never passed by a caller.

**`SUCCESS_WITH_ORPHAN` is reachable and is not corruption** (round-13 #11,
round-14 #10).  Measured: deleting a losing temporary while its own handle is
open fails with `ERROR_SHARING_VIOLATION` (32) and succeeds once closed.  So the
primitive closes first and only reports an orphan if the delete *still* fails --
which happens when a scanner or indexer holds a handle, not when we do.  The
canonical object is committed either way, so **callers must continue**; the
orphan is separate cleanup debt, reaped only under the exclusive lease.

**The store lease is a handle-held `LockFileEx` lock** (§5.4, round-14 #4).
Measured: shared leases stack, an exclusive request under them fails with
`ERROR_LOCK_VIOLATION` (33), and **a process that dies holding the lock releases
it** -- a child that took the exclusive lease and called `os._exit` left the
store immediately lockable.  An existence-based lock would have deadlocked every
later run until someone deleted a file by hand.

**Immutability enforcement is scoped to what is actually checkable, and the ACL
claim is WITHDRAWN** (round-14 #9).  The plan required "a protected store ACL
denying write to the analysis account", but Plan A is a job run by one account:
the same principal cannot be denied writes and also create canonical objects,
and inventing a second local publisher identity is exactly the arrangement this
machine already had to unwind elsewhere.  So that claim is dropped rather than
faked.  What survives is enforced and tested: **reparse points rejected over the
full ancestor chain**, **unexpected hard links rejected by link count**
(measured: 1 -> 2 the moment an alias exists), **no write sharing** on validated
reads, and **byte verification on collision**.
"""

from __future__ import annotations

import ctypes
import hashlib
import msvcrt
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

#: Frozen: the rename never replaces.  Passing `True` here silently overwrote a
#: canonical object in the probe, which is the one outcome the store forbids.
REPLACE_IF_EXISTS = False

#: Temporaries live in a namespace enumeration excludes, so a reader can never
#: observe a half-written object as a candidate.
TEMPORARY_PREFIX = ".tmp-"

#: Outcomes of :func:`publish_content_object`.
PUBLISHED = "PUBLISHED"
ALREADY_PRESENT = "ALREADY_PRESENT"
SUCCESS_WITH_ORPHAN = "SUCCESS_WITH_ORPHAN"

#: Every outcome above means the canonical object is committed and usable.
COMMITTED_OUTCOMES = frozenset({PUBLISHED, ALREADY_PRESENT, SUCCESS_WITH_ORPHAN})

ERROR_ACCESS_DENIED = 5
ERROR_INVALID_HANDLE = 6
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33
ERROR_ALREADY_EXISTS = 183

_IS_WINDOWS = sys.platform == "win32"

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
DELETE = 0x00010000
FILE_SHARE_READ = 0x00000001
CREATE_NEW = 1
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
FileRenameInfo = 3

LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
LOCKFILE_EXCLUSIVE_LOCK = 0x00000002


class StoreError(Exception):
    """A publication failed closed.  Nothing was published."""


class ImmutabilityViolation(StoreError):
    """The store or an artifact is not in a state whose bytes can be trusted."""


class LeaseUnavailable(StoreError):
    """The requested store lease is held by someone else."""


if _IS_WINDOWS:  # pragma: no branch - the project targets Windows
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    _k32.WriteFile.restype = wintypes.BOOL
    _k32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _k32.FlushFileBuffers.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    _k32.SetFileInformationByHandle.restype = wintypes.BOOL
    _k32.LockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    _k32.LockFileEx.restype = wintypes.BOOL

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    _k32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION)
    ]
    _k32.GetFileInformationByHandle.restype = wintypes.BOOL


def digest_of(payload: bytes) -> str:
    """The content address.  Identity in this store is content, never a path."""

    return hashlib.sha256(payload).hexdigest()


def _rename_through_handle(handle: int, target: Path) -> tuple[bool, int | None]:
    """Rename the file `handle` identifies.  The handle stays OPEN across this.

    Round-14 #1: this is why the temporary is not closed before the rename.
    """

    target_name = str(target)
    name_bytes = len(target_name) * ctypes.sizeof(ctypes.c_wchar)

    class FILE_RENAME_INFO(ctypes.Structure):
        _fields_ = [
            ("ReplaceIfExists", ctypes.c_ubyte),
            ("_pad", ctypes.c_ubyte * 7),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", ctypes.c_wchar * (len(target_name) + 1)),
        ]

    info = FILE_RENAME_INFO()
    info.ReplaceIfExists = 1 if REPLACE_IF_EXISTS else 0
    info.RootDirectory = None
    info.FileNameLength = name_bytes
    info.FileName = target_name

    ok = _k32.SetFileInformationByHandle(
        handle, FileRenameInfo, ctypes.byref(info), ctypes.sizeof(info)
    )
    return bool(ok), (None if ok else ctypes.get_last_error())


def assert_no_reparse_ancestry(path: Path) -> None:
    """Reject a reparse point anywhere on the ancestor chain (round-13 #9).

    Checking only the final directory lets a junction higher up redirect the
    whole store after validation.
    """

    if not _IS_WINDOWS:
        return
    probe = Path(path).resolve()
    seen: list[Path] = []
    while True:
        seen.append(probe)
        if probe.exists():
            attributes = getattr(os.stat(probe, follow_symlinks=False), "st_file_attributes", 0)
            if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise ImmutabilityViolation(
                    f"reparse point on the store ancestor chain: {probe}"
                )
        if probe.parent == probe:
            return
        probe = probe.parent


def link_count(path: Path) -> int:
    """Hard links to `path`.  An unexpected alias can rewrite validated bytes."""

    if not _IS_WINDOWS:
        return os.stat(path).st_nlink
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        info = _BY_HANDLE_FILE_INFORMATION()
        if not _k32.GetFileInformationByHandle(msvcrt.get_osfhandle(fd), ctypes.byref(info)):
            raise StoreError(
                f"GetFileInformationByHandle failed on {path}: {ctypes.get_last_error()}"
            )
        return int(info.nNumberOfLinks)
    finally:
        os.close(fd)


def assert_single_link(path: Path) -> None:
    """A canonical object must have exactly one name (round-13 #9)."""

    count = link_count(path)
    if count != 1:
        raise ImmutabilityViolation(
            f"canonical object has {count} hard links, so its bytes are not pinned: {path}"
        )


@dataclass(frozen=True)
class PublishResult:
    """What the write primitive did.  Every outcome here is a commit."""

    outcome: str
    digest: str
    path: Path
    orphan: Path | None = None

    @property
    def committed(self) -> bool:
        """Round-14 #10: the caller contract.  All three outcomes continue.

        `SUCCESS_WITH_ORPHAN` carries the same durability as `PUBLISHED` -- the
        canonical object is renamed into place either way, and only a temporary
        failed to be unlinked.  A caller that halted on it would abandon a
        publication that had already succeeded.
        """

        return self.outcome in COMMITTED_OUTCOMES


class ContentStore:
    """Content-addressed, immutable, append-only.  Nothing is ever overwritten."""

    def __init__(self, root: str | Path, *, verify_ancestry: bool = True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if verify_ancestry:
            assert_no_reparse_ancestry(self.root)
        self._temporary_counter = 0

    def path_for(self, digest: str) -> Path:
        return self.root / digest

    def _next_temporary(self) -> Path:
        """A unique name per attempt, so two publishers never collide on it."""

        self._temporary_counter += 1
        return self.root / (
            f"{TEMPORARY_PREFIX}{os.getpid()}-{self._temporary_counter}-"
            f"{self._temporary_counter:08x}"
        )

    def publish_content_object(self, payload: bytes) -> PublishResult:
        """Write `payload` to `<store>/<sha256>` idempotently.

        The three-step primitive, in the order the probes proved necessary:

        1. `CREATE_NEW` a unique temporary in the **same directory**, opened
           `GENERIC_WRITE | DELETE` -- without `DELETE` the rename fails with 5.
        2. write, checked `FlushFileBuffers`.
        3. rename **through that still-open handle** with
           `ReplaceIfExists = FALSE`, *then* close.

        Target-exists is not a conflict: content addressing makes the existing
        bytes identical by construction, so the store byte-verifies and keeps the
        winner.  Unequal bytes **fail closed** -- a digest collision or corruption
        is not assumed away.
        """

        digest = digest_of(payload)
        target = self.path_for(digest)

        if not _IS_WINDOWS:
            return self._publish_posix(payload, digest, target)

        temporary = self._next_temporary()
        handle = _k32.CreateFileW(
            str(temporary),
            GENERIC_WRITE | DELETE,
            FILE_SHARE_READ,
            None,
            CREATE_NEW,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise StoreError(
                f"could not create temporary {temporary}: {ctypes.get_last_error()}"
            )

        try:
            written = wintypes.DWORD()
            buffer = ctypes.create_string_buffer(payload, len(payload))
            if not _k32.WriteFile(handle, buffer, len(payload), ctypes.byref(written), None):
                raise StoreError(f"WriteFile failed: {ctypes.get_last_error()}")
            if written.value != len(payload):
                raise StoreError(
                    f"short write: {written.value} of {len(payload)} bytes"
                )
            if not _k32.FlushFileBuffers(handle):
                raise StoreError(f"FlushFileBuffers failed: {ctypes.get_last_error()}")

            renamed, error = _rename_through_handle(handle, target)
        except BaseException:
            _k32.CloseHandle(handle)
            self._discard(temporary)
            raise

        if renamed:
            _k32.CloseHandle(handle)
            return PublishResult(PUBLISHED, digest, target)

        if error != ERROR_ALREADY_EXISTS:
            _k32.CloseHandle(handle)
            self._discard(temporary)
            raise StoreError(
                f"publishing {digest} failed with {error}; nothing was published"
            )

        # Target exists.  Byte-verify the winner before trusting it.
        _k32.CloseHandle(handle)
        existing = target.read_bytes()
        if existing != payload:
            self._discard(temporary)
            raise ImmutabilityViolation(
                f"content address {digest} holds different bytes "
                f"({len(existing)} vs {len(payload)}); failing closed"
            )

        orphan = self._discard(temporary)
        if orphan is not None:
            return PublishResult(SUCCESS_WITH_ORPHAN, digest, target, orphan)
        return PublishResult(ALREADY_PRESENT, digest, target)

    def publish_named_object(self, payload: bytes, name: str) -> PublishResult:
        """Publish to an explicit `name` with the same non-replacing primitive.

        Used for generation records (§5.2), whose identity is an ordinal rather
        than a digest.  Content is still atomic with creation: the name appears
        only once the fully-written, flushed temporary is renamed onto it, so a
        kill mid-write cannot leave a permanently invalid generation holding a
        live name (round-13 #1).  `ERROR_ALREADY_EXISTS` here is a genuine
        allocation race, not the idempotent-content case, so it is raised.
        """

        target = self.root / name
        digest = digest_of(payload)

        if not _IS_WINDOWS:
            temporary = self._next_temporary()
            with open(temporary, "xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                os.unlink(temporary)
                raise
            os.unlink(temporary)
            return PublishResult(PUBLISHED, digest, target)

        temporary = self._next_temporary()
        handle = _k32.CreateFileW(
            str(temporary), GENERIC_WRITE | DELETE, FILE_SHARE_READ, None,
            CREATE_NEW, FILE_ATTRIBUTE_NORMAL, None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise StoreError(
                f"could not create temporary {temporary}: {ctypes.get_last_error()}"
            )
        try:
            written = wintypes.DWORD()
            buffer = ctypes.create_string_buffer(payload, len(payload))
            if not _k32.WriteFile(handle, buffer, len(payload), ctypes.byref(written), None):
                raise StoreError(f"WriteFile failed: {ctypes.get_last_error()}")
            if not _k32.FlushFileBuffers(handle):
                raise StoreError(f"FlushFileBuffers failed: {ctypes.get_last_error()}")
            renamed, error = _rename_through_handle(handle, target)
        except BaseException:
            _k32.CloseHandle(handle)
            self._discard(temporary)
            raise

        _k32.CloseHandle(handle)
        if renamed:
            return PublishResult(PUBLISHED, digest, target)
        self._discard(temporary)
        if error == ERROR_ALREADY_EXISTS:
            raise FileExistsError(f"{name} already exists")
        raise StoreError(f"publishing {name} failed with {error}; nothing was published")

    def _publish_posix(self, payload: bytes, digest: str, target: Path) -> PublishResult:
        """Portability path for the pure-logic tests.  Windows is the design."""

        temporary = self._next_temporary()
        with open(temporary, "xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = target.read_bytes()
            os.unlink(temporary)
            if existing != payload:
                raise ImmutabilityViolation(
                    f"content address {digest} holds different bytes; failing closed"
                )
            return PublishResult(ALREADY_PRESENT, digest, target)
        os.unlink(temporary)
        return PublishResult(PUBLISHED, digest, target)

    def _discard(self, temporary: Path) -> Path | None:
        """Delete a losing temporary; return it if it survives as an orphan.

        Measured: with its own handle still open the delete fails with 32, and
        succeeds the moment the handle closes -- so this runs *after* the close
        and an orphan means some **other** process holds a handle.  That is
        cleanup debt, not corruption, and never a reason to unwind a commit.
        """

        try:
            os.unlink(temporary)
            return None
        except FileNotFoundError:
            return None
        except OSError:
            return temporary

    def read_validated(self, digest: str) -> bytes:
        """Open without write sharing, rehash, and reject aliases.

        §5.3's snapshot semantics: a consumer never re-resolves a path it
        validated earlier, so the bytes returned here are the bytes that were
        hashed here.
        """

        path = self.path_for(digest)
        if not path.exists():
            raise StoreError(f"content object absent: {digest}")
        assert_single_link(path)
        payload = self._read_no_write_sharing(path)
        actual = digest_of(payload)
        if actual != digest:
            raise ImmutabilityViolation(
                f"content object {digest} hashes to {actual}; the store is corrupt"
            )
        return payload

    def _read_no_write_sharing(self, path: Path) -> bytes:
        if not _IS_WINDOWS:
            return path.read_bytes()
        handle = _k32.CreateFileW(
            str(path), GENERIC_READ, 0, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
        )
        if handle == INVALID_HANDLE_VALUE:
            raise StoreError(
                f"could not open {path} without write sharing: {ctypes.get_last_error()}"
            )
        _k32.CloseHandle(handle)
        return path.read_bytes()

    def orphans(self) -> tuple[Path, ...]:
        """Temporaries left behind.  Reaped only under the exclusive lease."""

        return tuple(
            sorted(p for p in self.root.iterdir() if p.name.startswith(TEMPORARY_PREFIX))
        )

    def content_objects(self) -> tuple[str, ...]:
        """Canonical digests.  Temporaries are excluded by prefix, not by luck."""

        return tuple(
            sorted(
                p.name
                for p in self.root.iterdir()
                if p.is_file() and not p.name.startswith(TEMPORARY_PREFIX)
            )
        )


class StoreLease:
    """A handle-held `LockFileEx` lease over the store (§5.4).

    Shared for readers and publishers, exclusive for the sweeper.  Measured:
    shared leases stack; an exclusive request beneath them fails with 33; and the
    OS releases the lock when the holder dies, so a crash cannot strand the store
    the way an existence-based lock would.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._fd: int | None = None
        self.exclusive: bool | None = None

    def acquire(self, *, exclusive: bool) -> "StoreLease":
        if self._fd is not None:
            raise StoreError("lease already held by this object")
        fd = os.open(self.path, os.O_RDWR)
        if _IS_WINDOWS:
            flags = LOCKFILE_FAIL_IMMEDIATELY | (LOCKFILE_EXCLUSIVE_LOCK if exclusive else 0)
            ok = _k32.LockFileEx(
                msvcrt.get_osfhandle(fd), flags, 0, 1, 0, ctypes.byref(_OVERLAPPED())
            )
            if not ok:
                error = ctypes.get_last_error()
                os.close(fd)
                raise LeaseUnavailable(
                    f"{'exclusive' if exclusive else 'shared'} store lease unavailable "
                    f"({error})"
                )
        self._fd = fd
        self.exclusive = exclusive
        return self

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self.exclusive = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> "StoreLease":
        if self._fd is None:
            raise StoreError("acquire the lease before entering it")
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()
