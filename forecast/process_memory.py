"""Commit-charge measurement for the §3 entry gate.

Implements §3.1 of `OSM-NORMALISATION-PLAN.md`.

**The gate is on commit charge, never on working set** (round-6 #6).  Working set
counts *resident* pages, so when Windows begins paging the process out the number
**falls** -- a swapping run would have looked healthier, not worse, and sampling
it cannot detect the failure it was meant to prevent.  Enforcement is on
`PrivateUsage` from `PROCESS_MEMORY_COUNTERS_EX`.  Working set is still recorded,
because §10.2's journal wants it, but it is never a gate.

**Read through `ctypes`, which adds no dependency** -- `psutil` is absent from
this environment and §3.1 froze the method rather than the library.

**The probe validates itself against a deliberate allocation.**  A measurement
function that silently returned a constant would make every gate row pass, so
:func:`validate_probe` allocates and touches a known amount and asserts the
reading moves with it.  Measured here: a 600 MB allocation moved `PrivateUsage`
from 10.4 MB to 611.6 MB.

**Every signature is declared.**  `GetCurrentProcess` returns a pseudo-handle of
`-1`, and without an explicit `restype` `ctypes` truncates it to a 32-bit `int`
on 64-bit Windows -- `GetProcessMemoryInfo` then fails with
`ERROR_INVALID_HANDLE` (6).  That is not a hypothetical: it is what the first run
of this code did.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

#: The deliberate allocation §3.1 validates the probe against.
PROBE_VALIDATION_BYTES = 600 * 1024 * 1024

_IS_WINDOWS = sys.platform == "win32"


class ProcessMemoryUnavailable(Exception):
    """The commit-charge probe could not run.

    Raised rather than returning a placeholder: a gate fed a fabricated
    measurement would authorise a corpus run on no evidence.
    """


if _IS_WINDOWS:  # pragma: no branch - the project targets Windows

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)

    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
        wintypes.DWORD,
    ]
    _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


@dataclass(frozen=True)
class MemorySample:
    """One reading.  Only `commit_bytes` is ever compared to a ceiling."""

    commit_bytes: int
    working_set_bytes: int
    peak_working_set_bytes: int

    @property
    def commit_gb(self) -> float:
        return self.commit_bytes / 1024**3


def process_memory() -> MemorySample:
    """Read this process's commit charge and working set."""

    if not _IS_WINDOWS:
        raise ProcessMemoryUnavailable(f"unsupported platform: {sys.platform}")

    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    if not _psapi.GetProcessMemoryInfo(
        _kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ProcessMemoryUnavailable(
            f"GetProcessMemoryInfo failed with {ctypes.get_last_error()}"
        )
    return MemorySample(
        commit_bytes=counters.PrivateUsage,
        working_set_bytes=counters.WorkingSetSize,
        peak_working_set_bytes=counters.PeakWorkingSetSize,
    )


def validate_probe(allocation_bytes: int = PROBE_VALIDATION_BYTES) -> int:
    """Prove the probe tracks allocation, and return the observed delta.

    §3.1 requires this before a gate run: a probe that returned a constant would
    make every memory row pass without measuring anything.  The buffer is
    *touched*, not merely allocated, because commit charge is what is being
    measured and an untouched reservation is a weaker test.
    """

    before = process_memory().commit_bytes
    buffer = bytearray(allocation_bytes)
    for offset in range(0, len(buffer), 4096):
        buffer[offset] = 1
    delta = process_memory().commit_bytes - before
    del buffer

    if delta < allocation_bytes // 2:
        raise ProcessMemoryUnavailable(
            f"probe did not track a {allocation_bytes} byte allocation "
            f"(delta {delta}); it is not measuring allocation"
        )
    return delta
