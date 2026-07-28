"""Process isolation for the raw GFC tiles.

The security goal is narrow and unchanged: **code running as the ordinary
analysis user must not be able to read raw ``lossyear``.**  Denying *write* was
never the point; the outcome layer leaks by being read.

**Mechanism: elevation, not account identity (deviation 2).**  The original
design used a dedicated least-privilege account owning the tiles, with the
interactive account denied.  That is a sound design and it is unusable on this
machine: launching any process as a second local account failed six different
ways on Windows 11 Home, and it blocks *analysis* time as well as acquisition,
because the sealed worker must read the tiles too.

So the boundary is the UAC split token instead.  The directory grants
``Administrators`` and ``SYSTEM`` and nothing else -- in particular it carries no
entry for the interactive user, so an **unelevated** process has no access at
all, while an **elevated** one reaches it through ``Administrators``.  Analysis
code runs unelevated; the sealed worker and the downloader are launched
elevated, deliberately.

This is still an OS mechanism rather than a convention, but it is weaker in one
specific way that must never be glossed: **any** elevated process can read the
tiles, not just the sealed worker.  The prior design distinguished principals;
this one distinguishes privilege levels.

A deny ACE is deliberately NOT used.  An explicit deny outranks the
``Administrators`` allow, so it locks out elevated access as well -- which is
exactly what broke acquisition.  Absence of a grant is what denies the
unelevated user here.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path

#: Reported when the tiles are readable by an unelevated process -- i.e. no
#: isolation at all.  Never let this read as "safe".
NOT_ENFORCED = "not_enforced"
ENFORCED = "enforced"
#: The check ran from an elevated process, which can read the tiles BY DESIGN,
#: so it cannot say anything about the unelevated case.  Distinct from enforced.
INDETERMINATE_ELEVATED = "indeterminate_elevated"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class IsolationStatus:
    """Whether raw-GFC isolation is actually in force."""

    state: str
    elevated: bool
    raw_root_exists: bool
    can_read: bool | None
    detail: str

    @property
    def enforced(self) -> bool:
        """True only when an UNELEVATED process was verifiably denied.

        Conservative by construction: an elevated observation proves nothing
        about the boundary, and unknown never counts as denied.
        """

        return self.state == ENFORCED


def is_elevated() -> bool:
    """Whether this process holds an elevated (administrator) token."""

    if os.name != "nt":
        return os.geteuid() == 0  # pragma: no cover - posix convenience
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # pragma: no cover - defensive
        return False


def can_read_raw(raw_root: str | Path) -> bool | None:
    """Probe whether THIS process can read the tiles.

    Returns ``None`` when the answer cannot be established, so an unknown is
    never mistaken for a denial.
    """

    root = Path(raw_root)
    if not root.exists():
        return None
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return False
    except OSError:
        return None
    for entry in entries:
        if entry.is_file():
            try:
                with entry.open("rb") as stream:
                    stream.read(1)
            except PermissionError:
                return False
            except OSError:
                return None
            return True
    # A listable directory means the ACL is not shutting us out, even if empty.
    return True


def isolation_status(raw_root: str | Path) -> IsolationStatus:
    """Report the real state of raw-GFC isolation, without guessing."""

    root = Path(raw_root)
    elevated = is_elevated()
    root_exists = root.exists()
    readable = can_read_raw(root) if root_exists else None

    if not root_exists:
        return IsolationStatus(
            UNKNOWN, elevated, False, None,
            f"raw GFC root does not exist: {root}",
        )
    if elevated:
        return IsolationStatus(
            INDETERMINATE_ELEVATED, True, True, readable,
            "this process is ELEVATED and may read the tiles by design; the "
            "boundary can only be verified from an unelevated process",
        )
    if readable is True:
        return IsolationStatus(
            NOT_ENFORCED, False, True, True,
            "an unelevated process can read the raw tiles; the directory still "
            "grants the interactive user and is NOT isolated",
        )
    if readable is None:
        return IsolationStatus(
            UNKNOWN, False, True, None,
            "readability could not be established",
        )
    return IsolationStatus(
        ENFORCED, False, True, False,
        "an unelevated process is denied read access to the raw GFC tiles",
    )


def setup_commands(raw_root: str | Path) -> list[str]:
    """The elevated commands that establish elevation-based isolation.

    Note the absence of any deny ACE: an explicit deny outranks the
    ``Administrators`` allow and would lock out elevated access too.
    """

    root = Path(raw_root)
    return [
        f'New-Item -ItemType Directory -Force "{root}"',
        # Drop inherited grants to the interactive user; absence of a grant is
        # what denies them.
        f'icacls "{root}" /inheritance:r',
        f'icacls "{root}" /grant "Administrators:(OI)(CI)F"',
        f'icacls "{root}" /grant "SYSTEM:(OI)(CI)F"',
    ]


def require_enforced(raw_root: str | Path) -> None:
    """Raise unless isolation is verifiably in force.

    Called before operations that assume the outcome layer is OS-protected.
    An elevated caller is refused too: it cannot demonstrate the boundary, and
    accepting it would let the guarantee be assumed rather than shown.
    """

    status = isolation_status(raw_root)
    if not status.enforced:
        raise PermissionError(
            f"raw-GFC isolation is not verifiably enforced ({status.state}): "
            f"{status.detail}. Establish it with: {'; '.join(setup_commands(raw_root))}"
        )
