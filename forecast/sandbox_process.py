"""Small process-containment primitives shared by the forecast sandboxes.

Child output is deliberately reduced to byte counts.  The captured bytes are
never returned, rendered, logged, or written outside the caller's temporary
directory.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class SealedProcessResult:
    """The non-data-bearing part of a sealed child-process transcript."""

    returncode: int
    stdout_bytes: int
    stderr_bytes: int
    timed_out: bool


class _WindowsJob:
    """A kill-on-close Windows Job Object containing exactly one child tree."""

    def __init__(self) -> None:
        self._handle: int | None = None
        if os.name != "nt":
            return

        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        # Kill the complete child tree when the supervisor closes the handle, and
        # terminate rather than invoke Windows' unhandled-exception UI.
        #
        # Breakaway is denied by CONSTRUCTION: neither JOB_OBJECT_LIMIT_BREAKAWAY_OK
        # (0x00000800) nor JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK (0x00001000) is set,
        # so no descendant can leave the job.  Asserted below so a future edit that
        # adds either flag fails loudly rather than silently opening an escape.
        limits.BasicLimitInformation.LimitFlags = 0x00002000 | 0x00000400
        assert not limits.BasicLimitInformation.LimitFlags & (0x00000800 | 0x00001000), (
            "Job Object must never permit breakaway"
        )
        if not kernel32.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise OSError(error, "SetInformationJobObject failed")
        self._handle = int(handle)

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if self._handle is None:
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        if not kernel32.AssignProcessToJobObject(
            wintypes.HANDLE(self._handle), wintypes.HANDLE(process._handle)  # type: ignore[attr-defined]
        ):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def terminate(self, exit_code: int = 124) -> None:
        if self._handle is None:
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject(wintypes.HANDLE(self._handle), exit_code)

    def close(self) -> None:
        if self._handle is None:
            return
        import ctypes
        from ctypes import wintypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(
            wintypes.HANDLE(self._handle)
        )
        self._handle = None


def _resume_suspended_process(pid: int) -> None:
    """Resume a process created with CREATE_SUSPENDED.

    The child is created suspended so it cannot run — and therefore cannot spawn
    an uncontained grandchild — before it has been assigned to the Job Object.
    ``subprocess.Popen`` closes the initial thread handle it receives from
    ``CreateProcess``, so the thread is re-opened from a Toolhelp snapshot.  A
    freshly created suspended process has exactly one thread, which makes the
    lookup deterministic.
    """

    if os.name != "nt":
        return

    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPTHREAD = 0x00000004
    THREAD_SUSPEND_RESUME = 0x0002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", ctypes.c_long),
            ("tpDeltaPri", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    resumed = 0
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(THREADENTRY32)
        found = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32OwnerProcessID == pid:
                thread = kernel32.OpenThread(
                    THREAD_SUSPEND_RESUME, False, entry.th32ThreadID
                )
                if not thread:
                    raise OSError(ctypes.get_last_error(), "OpenThread failed")
                try:
                    if kernel32.ResumeThread(wintypes.HANDLE(thread)) == 0xFFFFFFFF:
                        raise OSError(ctypes.get_last_error(), "ResumeThread failed")
                    resumed += 1
                finally:
                    kernel32.CloseHandle(wintypes.HANDLE(thread))
            found = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    if resumed == 0:
        raise OSError(f"No resumable thread found for suspended child pid {pid}")


def _disable_unix_core_dumps() -> None:
    if os.name == "nt":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_sealed_process(
    command: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str],
    timeout_seconds: float,
) -> SealedProcessResult:
    """Run a child with sealed streams and kill-tree containment."""

    creationflags = 0
    if os.name == "nt":
        # CREATE_SUSPENDED is what closes the escape race: the child must not be
        # runnable until it is inside the Job Object, or it could spawn an
        # uncontained grandchild in the window between Popen and assign().
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        )
    job = _WindowsJob()
    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    stdout = b""
    stderr = b""
    try:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
            preexec_fn=_disable_unix_core_dumps if os.name != "nt" else None,
        )
        try:
            # Order is load-bearing: assign the suspended child to the job FIRST,
            # only then let it run.  Resuming before assignment would reopen the
            # grandchild-escape window that CREATE_SUSPENDED exists to close.
            job.assign(process)
            _resume_suspended_process(process.pid)
        except BaseException:
            process.kill()
            process.wait()
            raise
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                job.terminate()
            else:
                try:
                    os.killpg(process.pid, 9)
                except ProcessLookupError:
                    pass
            stdout, stderr = process.communicate()
        return SealedProcessResult(
            returncode=int(process.returncode),
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
            timed_out=timed_out,
        )
    finally:
        # Byte strings are intentionally not exposed; overwrite the references
        # before the Job handle is released.
        stdout = b""
        stderr = b""
        if process is not None and process.poll() is None:
            if os.name == "nt":
                job.terminate()
            else:
                process.kill()
            process.wait()
        job.close()

