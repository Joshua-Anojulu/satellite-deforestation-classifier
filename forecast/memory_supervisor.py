"""The supervised child that enforces §3's memory ceiling.

Implements the frozen design in §3 of `OSM-NORMALISATION-PLAN.md`.

**A Job Object memory limit does not terminate anything by itself, and v7 said it
did** (round-7 #4).  `JOB_OBJECT_LIMIT_PROCESS_MEMORY` makes an over-limit
*allocation fail*; the process keeps running.  v7 also claimed the mechanism was
"exercised" in `forecast/sandbox_process.py`, which sets
`LimitFlags = 0x2000 | 0x400` -- kill-on-close and die-on-unhandled-exception --
and assigns **no memory limit at all**.  Job Objects are used there for process
containment, a different purpose.

**The limit is job-wide, not per-process** (`JOB_OBJECT_LIMIT_JOB_MEMORY`), so
the node index *and* the resident closure table `S` count against one total.  A
per-process limit would let two components each stay under the bar while the
stage as a whole went over it.

**The notification must be the guaranteed one** (round-8 #9).  v8 relied on the
supervisor being told about a breach, but Microsoft documents ordinary
completion-port messages such as `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT` as *not
guaranteed to be delivered*, so "the supervisor terminates on every breach" was
not a promise v8 could keep.  A `JobObjectNotificationLimitInformation` soft
threshold is registered **before the child starts** and the supervisor terminates
on `JOB_OBJECT_MSG_NOTIFICATION_LIMIT`, which is guaranteed.

**Kill-tested on this machine rather than argued.**  A job with a 100 MB
notification threshold and a 400 MB hard limit, a child that touched 250 MB: the
completion port received `NEW_PROCESS` then `NOTIFICATION_LIMIT`, the supervisor
called `TerminateJobObject`, and the child exited 124.  The mechanism the plan
freezes is the mechanism that ran.

**Both failure shapes are stage failure.**  An over-limit allocation failing
inside the child, and the child exiting abnormally, are treated identically:
the hard limit stays a backstop, never the detection mechanism.

**Every signature is declared** -- an undeclared `HANDLE` return truncates to 32
bits on 64-bit Windows and the call fails with `ERROR_INVALID_HANDLE`.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

#: The frozen authorisation ceiling (§3).  The supervisor terminates here.
AUTHORISATION_CEILING_BYTES = int(14.0 * 1024**3)

#: The hard limit, a backstop only.  v9 said merely "below 17 GB", which froze
#: nothing (round-9 #6), so both numbers are named and neither is implied.
HARD_LIMIT_BYTES = int(17.0 * 1024**3)

#: Exit code the supervisor terminates a breaching job with.
TERMINATION_EXIT_CODE = 124

_JobObjectAssociateCompletionPortInformation = 7
_JobObjectExtendedLimitInformation = 9
_JobObjectNotificationLimitInformation = 12

_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
_JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
_JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000

_PROCESS_ALL_ACCESS = 0x001F0FFF

#: Completion-port message codes.  `NOTIFICATION_LIMIT` is the guaranteed one;
#: `JOB_MEMORY_LIMIT` is the message round-8 #9 established cannot be relied on.
MSG_NEW_PROCESS = 6
MSG_EXIT_PROCESS = 7
MSG_ABNORMAL_EXIT_PROCESS = 8
MSG_PROCESS_MEMORY_LIMIT = 9
MSG_JOB_MEMORY_LIMIT = 10
MSG_NOTIFICATION_LIMIT = 11

MSG_NOTIFICATION_LIMIT_NAME = "NOTIFICATION_LIMIT"

#: `subprocess` does not export `CREATE_SUSPENDED`; `sandbox_process` already
#: carries this fallback, and both start children the same way.
_CREATE_SUSPENDED = getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)

_IS_WINDOWS = sys.platform == "win32"


class SupervisorUnavailable(Exception):
    """The supervised-child mechanism cannot run on this platform."""


class MemoryCeilingBreached(Exception):
    """The job crossed the authorisation ceiling and was terminated."""


if _IS_WINDOWS:  # pragma: no branch - the project targets Windows

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.POINTER(wintypes.ULONG)),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _JOBOBJECT_NOTIFICATION_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("IoReadBytesLimit", ctypes.c_ulonglong),
            ("IoWriteBytesLimit", ctypes.c_ulonglong),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("JobMemoryLimit", ctypes.c_ulonglong),
            ("RateControlTolerance", wintypes.DWORD),
            ("RateControlToleranceInterval", wintypes.DWORD),
            ("LimitFlags", wintypes.DWORD),
        ]

    class _JOBOBJECT_ASSOCIATE_COMPLETION_PORT(ctypes.Structure):
        _fields_ = [
            ("CompletionKey", ctypes.c_void_p),
            ("CompletionPort", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateIoCompletionPort.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.CreateIoCompletionPort.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.GetQueuedCompletionStatus.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD,
    ]
    _kernel32.GetQueuedCompletionStatus.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


@dataclass(frozen=True)
class SupervisedResult:
    """What the supervisor observed.  `breached` is the authorisation answer."""

    exit_code: int | None
    breached: bool
    messages: tuple[str, ...]
    elapsed_s: float

    @property
    def stage_failed(self) -> bool:
        """Allocation failure and abnormal exit are both stage failure (§3)."""

        return self.breached or self.exit_code not in (0,)


_MESSAGE_NAMES = {
    MSG_NEW_PROCESS: "NEW_PROCESS",
    MSG_EXIT_PROCESS: "EXIT_PROCESS",
    MSG_ABNORMAL_EXIT_PROCESS: "ABNORMAL_EXIT_PROCESS",
    MSG_PROCESS_MEMORY_LIMIT: "PROCESS_MEMORY_LIMIT",
    MSG_JOB_MEMORY_LIMIT: "JOB_MEMORY_LIMIT",
    MSG_NOTIFICATION_LIMIT: "NOTIFICATION_LIMIT",
}


class MemorySupervisedJob:
    """A job object with a job-wide hard limit and a guaranteed soft notification.

    Both limits are registered before any child is assigned, which is what makes
    the threshold meaningful: a child that allocated during setup would
    otherwise run unsupervised through exactly the window that matters.
    """

    def __init__(
        self,
        *,
        notification_bytes: int = AUTHORISATION_CEILING_BYTES,
        hard_limit_bytes: int = HARD_LIMIT_BYTES,
    ) -> None:
        if not _IS_WINDOWS:
            raise SupervisorUnavailable(f"unsupported platform: {sys.platform}")
        if notification_bytes >= hard_limit_bytes:
            raise ValueError(
                "the notification threshold must sit below the hard limit; "
                "otherwise the backstop fires first and the guaranteed "
                "notification never arrives"
            )

        self.notification_bytes = notification_bytes
        self.hard_limit_bytes = hard_limit_bytes

        self._job = _kernel32.CreateJobObjectW(None, None)
        if not self._job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        self._port = _kernel32.CreateIoCompletionPort(
            wintypes.HANDLE(-1), None, None, 1
        )
        if not self._port:
            raise OSError(ctypes.get_last_error(), "CreateIoCompletionPort failed")

        self._associate_port()
        self._set_hard_limit()
        self._set_notification_limit()

    def _set(self, info_class: int, structure) -> None:
        if not _kernel32.SetInformationJobObject(
            wintypes.HANDLE(self._job),
            info_class,
            ctypes.byref(structure),
            ctypes.sizeof(structure),
        ):
            raise OSError(
                ctypes.get_last_error(),
                f"SetInformationJobObject({info_class}) failed",
            )

    def _associate_port(self) -> None:
        assoc = _JOBOBJECT_ASSOCIATE_COMPLETION_PORT(
            ctypes.c_void_p(0), wintypes.HANDLE(self._port)
        )
        self._set(_JobObjectAssociateCompletionPortInformation, assoc)

    def _set_hard_limit(self) -> None:
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
            | _JOB_OBJECT_LIMIT_JOB_MEMORY
        )
        limits.JobMemoryLimit = self.hard_limit_bytes
        # Breakaway is denied by construction, as in `sandbox_process`.
        assert not limits.BasicLimitInformation.LimitFlags & (
            _JOB_OBJECT_LIMIT_BREAKAWAY_OK | _JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
        )
        self._set(_JobObjectExtendedLimitInformation, limits)

    def _set_notification_limit(self) -> None:
        note = _JOBOBJECT_NOTIFICATION_LIMIT_INFORMATION()
        note.JobMemoryLimit = self.notification_bytes
        note.LimitFlags = _JOB_OBJECT_LIMIT_JOB_MEMORY
        self._set(_JobObjectNotificationLimitInformation, note)

    def assign(self, pid: int) -> None:
        handle = _kernel32.OpenProcess(_PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
        try:
            if not _kernel32.AssignProcessToJobObject(
                wintypes.HANDLE(self._job), wintypes.HANDLE(handle)
            ):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(handle))

    def poll(self, timeout_ms: int = 250) -> str | None:
        """One completion-port message, or `None` on timeout."""

        code = wintypes.DWORD()
        key = ctypes.c_void_p()
        overlapped = ctypes.c_void_p()
        if not _kernel32.GetQueuedCompletionStatus(
            wintypes.HANDLE(self._port),
            ctypes.byref(code),
            ctypes.byref(key),
            ctypes.byref(overlapped),
            timeout_ms,
        ):
            return None
        return _MESSAGE_NAMES.get(code.value, f"UNKNOWN_{code.value}")

    def terminate(self, exit_code: int = TERMINATION_EXIT_CODE) -> None:
        _kernel32.TerminateJobObject(wintypes.HANDLE(self._job), exit_code)

    def close(self) -> None:
        for handle in (self._port, self._job):
            if handle:
                _kernel32.CloseHandle(wintypes.HANDLE(handle))
        self._port = self._job = None

    def __enter__(self) -> "MemorySupervisedJob":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def run_supervised(
    command: list[str],
    *,
    notification_bytes: int = AUTHORISATION_CEILING_BYTES,
    hard_limit_bytes: int = HARD_LIMIT_BYTES,
    timeout_s: float = 3600.0,
) -> SupervisedResult:
    """Run `command` under a job that terminates it at the soft threshold.

    The child is started **suspended** so the limits registered in the
    constructor are already in force when its first instruction runs.
    """

    started = time.monotonic()
    messages: list[str] = []
    breached = False

    with MemorySupervisedJob(
        notification_bytes=notification_bytes, hard_limit_bytes=hard_limit_bytes
    ) as job:
        child = subprocess.Popen(command, creationflags=_CREATE_SUSPENDED)
        try:
            job.assign(child.pid)
            _resume(child.pid)

            deadline = started + timeout_s
            while time.monotonic() < deadline:
                message = job.poll()
                if message is not None:
                    messages.append(message)
                    if message == MSG_NOTIFICATION_LIMIT_NAME:
                        breached = True
                        job.terminate()
                        break
                if child.poll() is not None and message is None:
                    break
        finally:
            if child.poll() is None:
                job.terminate()
            exit_code = child.wait(timeout=30)

    return SupervisedResult(
        exit_code=exit_code,
        breached=breached,
        messages=tuple(messages),
        elapsed_s=time.monotonic() - started,
    )


def _resume(pid: int) -> None:
    """Resume every thread of a suspended child.

    Reuses `sandbox_process`'s helper rather than reimplementing the thread-scan
    dance -- `Popen` closes the initial thread handle, so resuming means walking
    a thread snapshot.  It is imported privately on purpose: that module is on
    the sealed-worker path, and renaming a symbol there for cosmetics is not
    worth the risk.
    """

    from forecast.sandbox_process import _resume_suspended_process

    _resume_suspended_process(pid)
