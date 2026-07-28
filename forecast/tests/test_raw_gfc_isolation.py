"""Isolation must be verifiable, and "unprovisioned" must never read as "safe"."""

from __future__ import annotations

from pathlib import Path

import pytest

from forecast import _raw_gfc_isolation as isolation
from forecast._raw_gfc_isolation import (
    NOT_PROVISIONED,
    PROVISIONED,
    RAW_GFC_ACCOUNT,
    IsolationStatus,
    analysis_account_can_read,
    isolation_status,
    require_enforced,
    setup_commands,
)


def test_unprovisioned_is_never_reported_as_enforced(tmp_path, monkeypatch):
    """The failure mode that matters: no account means no isolation at all."""

    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: False)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")

    status = isolation_status(tmp_path)
    assert status.state == NOT_PROVISIONED
    assert not status.enforced
    assert "NOT restricted" in status.detail


def test_readable_tiles_are_not_enforcement_even_with_the_account(tmp_path, monkeypatch):
    """An account without an effective deny ACE is theatre, not a mechanism."""

    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: True)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")

    status = isolation_status(tmp_path)
    assert status.state == PROVISIONED
    assert status.analysis_can_read is True
    assert not status.enforced
    assert "can still read" in status.detail


def test_unknown_readability_is_not_enforcement(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: True)
    monkeypatch.setattr(isolation, "analysis_account_can_read", lambda root: None)

    status = isolation_status(tmp_path)
    assert status.analysis_can_read is None
    assert not status.enforced, "unknown must never count as denied"


def test_denied_reads_are_enforcement(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: True)
    monkeypatch.setattr(isolation, "analysis_account_can_read", lambda root: False)

    status = isolation_status(tmp_path)
    assert status.enforced
    assert "denied" in status.detail


def test_require_enforced_raises_when_unprovisioned(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: False)
    with pytest.raises(PermissionError, match="not enforced"):
        require_enforced(tmp_path)


def test_require_enforced_reports_the_remedy(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: False)
    with pytest.raises(PermissionError, match="New-LocalUser"):
        require_enforced(tmp_path)


def test_require_enforced_passes_when_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, "account_exists", lambda name=RAW_GFC_ACCOUNT: True)
    monkeypatch.setattr(isolation, "analysis_account_can_read", lambda root: False)
    require_enforced(tmp_path)


def test_missing_root_is_unknown_not_readable(tmp_path):
    assert analysis_account_can_read(tmp_path / "absent") is None


def test_readable_root_is_detected(tmp_path):
    (tmp_path / "tile.tif").write_bytes(b"x")
    assert analysis_account_can_read(tmp_path) is True


def test_setup_commands_break_inheritance_before_denying(tmp_path):
    """Inherited grants would otherwise survive the deny ACE."""

    commands = setup_commands(tmp_path)
    joined = "\n".join(commands)
    assert "New-LocalUser" in joined
    assert "/inheritance:r" in joined
    assert f'grant "{RAW_GFC_ACCOUNT}' in joined
    assert "/deny" in joined
    inheritance_at = next(i for i, c in enumerate(commands) if "/inheritance:r" in c)
    deny_at = next(i for i, c in enumerate(commands) if "/deny" in c)
    assert inheritance_at < deny_at


def test_enforced_requires_every_condition():
    """`enforced` is conservative by construction."""

    assert not IsolationStatus(PROVISIONED, True, True, True, "").enforced
    assert not IsolationStatus(PROVISIONED, True, True, None, "").enforced
    assert not IsolationStatus(NOT_PROVISIONED, False, True, False, "").enforced
    assert IsolationStatus(PROVISIONED, True, True, False, "").enforced


@pytest.mark.skipif(
    not isolation.account_exists(),
    reason=(
        f"local account {RAW_GFC_ACCOUNT!r} is not provisioned; run the elevated "
        "setup script to enable the live both-directions integration test"
    ),
)
def test_live_isolation_denies_the_analysis_account(tmp_path):
    """Live check, active only once the account exists.

    Skipped-not-passed on an unprovisioned box; `require_enforced` is what
    prevents that skip from being mistaken for a guarantee at runtime.
    """

    from risk.config import HANSEN_DIR

    status = isolation_status(HANSEN_DIR)
    assert status.enforced, status.detail
