"""Process isolation for the raw GFC tiles.

`icacls` alone cannot separate the sealed worker from analysis code: child
processes inherit the parent's Windows token, so anything the worker can read
from a directory, another child of the same account can read too.  Denying
write is not the issue -- the outcome layer is the leakage risk, and it is a
*read* the firewall has to prevent.

Real separation therefore needs a second security principal: a dedicated
least-privilege local account that owns the raw tiles, with the interactive
analysis account explicitly denied.  Creating that account requires elevation,
which is why provisioning is a script a human runs once rather than something
this module attempts.

The module's job is to make the isolation *checkable*: it reports, without
guessing, whether isolation is provisioned, and it never lets "not provisioned"
be mistaken for "verified".
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The dedicated principal that owns the raw GFC tiles.
RAW_GFC_ACCOUNT = "satclf-gfc-worker"

#: Reported when the account has not been created yet.  Distinct from "denied"
#: on purpose: an unprovisioned box has NO isolation, and must never read as
#: though it had.
NOT_PROVISIONED = "not_provisioned"
PROVISIONED = "provisioned"


@dataclass(frozen=True)
class IsolationStatus:
    """Whether raw-GFC isolation is actually in force on this machine."""

    state: str
    account_exists: bool
    raw_root_exists: bool
    analysis_can_read: bool | None
    detail: str

    @property
    def enforced(self) -> bool:
        """True only when a mechanism is verifiably denying the analysis account.

        Deliberately conservative: anything unknown is not enforcement.
        """

        return (
            self.state == PROVISIONED
            and self.account_exists
            and self.analysis_can_read is False
        )


def account_exists(name: str = RAW_GFC_ACCOUNT) -> bool:
    """Return whether the dedicated local account exists."""

    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["net", "user", name],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def analysis_account_can_read(raw_root: str | Path) -> bool | None:
    """Probe whether THIS process (the analysis account) can read the tiles.

    Returns ``None`` when the answer cannot be established -- e.g. the root does
    not exist -- so the caller cannot mistake an unknown for a denial.
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
    # An empty but listable directory still means the ACL is not denying us.
    return True


def isolation_status(raw_root: str | Path) -> IsolationStatus:
    """Report the real state of raw-GFC isolation, without guessing."""

    root = Path(raw_root)
    exists = account_exists()
    root_exists = root.exists()
    readable = analysis_account_can_read(root) if root_exists else None

    if not exists:
        return IsolationStatus(
            NOT_PROVISIONED, False, root_exists, readable,
            f"local account {RAW_GFC_ACCOUNT!r} does not exist; raw-GFC reads are "
            "NOT restricted by any OS mechanism",
        )
    if readable is True:
        return IsolationStatus(
            PROVISIONED, True, root_exists, True,
            "account exists but the analysis account can still read the raw tiles; "
            "the deny ACE is missing or ineffective",
        )
    if readable is None:
        return IsolationStatus(
            PROVISIONED, True, root_exists, None,
            "account exists but readability could not be established",
        )
    return IsolationStatus(
        PROVISIONED, True, root_exists, False,
        "analysis account is denied read access to the raw GFC tiles",
    )


def setup_commands(raw_root: str | Path, account: str = RAW_GFC_ACCOUNT) -> list[str]:
    """The exact elevated commands that provision isolation.

    Returned rather than executed: creating a local principal and rewriting a
    DACL needs administrator rights, and silently attempting it would either
    fail confusingly or do something a human did not sanction.
    """

    root = Path(raw_root)
    analysis_user = os.environ.get("USERNAME", "<your-account>")
    return [
        f'New-LocalUser -Name "{account}" -Description "Sealed GFC reader" '
        f'-Password (Read-Host -AsSecureString "Password for {account}") '
        f'-PasswordNeverExpires',
        f'New-Item -ItemType Directory -Force "{root}"',
        # Break inheritance so the interactive account's inherited grants do not
        # survive the deny ACE.
        f'icacls "{root}" /inheritance:r',
        f'icacls "{root}" /grant "{account}:(OI)(CI)F"',
        f'icacls "{root}" /grant "Administrators:(OI)(CI)F"',
        f'icacls "{root}" /deny "{analysis_user}:(OI)(CI)R"',
    ]


def require_enforced(raw_root: str | Path) -> None:
    """Raise unless isolation is verifiably in force.

    Called before any post-lift operation that assumes the outcome layer is
    OS-protected, so the guarantee cannot be assumed on an unprovisioned box.
    """

    status = isolation_status(raw_root)
    if not status.enforced:
        raise PermissionError(
            f"raw-GFC isolation is not enforced ({status.state}): {status.detail}. "
            f"Provision it with: {'; '.join(setup_commands(raw_root))}"
        )
