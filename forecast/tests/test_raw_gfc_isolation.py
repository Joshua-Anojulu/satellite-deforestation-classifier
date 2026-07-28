"""Isolation must be verifiable, and "unverifiable" must never read as "safe"."""

from __future__ import annotations

from pathlib import Path

import pytest

from forecast import _raw_gfc_isolation as isolation
from forecast._raw_gfc_isolation import (
    ENFORCED,
    INDETERMINATE_ELEVATED,
    NOT_ENFORCED,
    UNKNOWN,
    IsolationStatus,
    can_read_raw,
    isolation_status,
    require_enforced,
    setup_commands,
)


def _unelevated(monkeypatch):
    monkeypatch.setattr(isolation, "is_elevated", lambda: False)


def _elevated(monkeypatch):
    monkeypatch.setattr(isolation, "is_elevated", lambda: True)


def test_readable_from_unelevated_is_not_enforced(tmp_path, monkeypatch):
    """The failure mode that matters: analysis code can read the outcome layer."""

    _unelevated(monkeypatch)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")

    status = isolation_status(tmp_path)
    assert status.state == NOT_ENFORCED
    assert not status.enforced
    assert "NOT isolated" in status.detail


def test_denied_from_unelevated_is_enforced(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    monkeypatch.setattr(isolation, "can_read_raw", lambda root: False)

    status = isolation_status(tmp_path)
    assert status.state == ENFORCED
    assert status.enforced


def test_elevated_observation_proves_nothing(tmp_path, monkeypatch):
    """An elevated process reads the tiles BY DESIGN under this model.

    Reporting that as enforcement would invert the meaning of the check.
    """

    _elevated(monkeypatch)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")

    status = isolation_status(tmp_path)
    assert status.state == INDETERMINATE_ELEVATED
    assert not status.enforced, "elevated access must never count as enforcement"
    assert "unelevated" in status.detail


def test_unknown_readability_is_not_enforcement(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    monkeypatch.setattr(isolation, "can_read_raw", lambda root: None)

    status = isolation_status(tmp_path)
    assert status.state == UNKNOWN
    assert not status.enforced


def test_missing_root_is_unknown(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    status = isolation_status(tmp_path / "absent")
    assert status.state == UNKNOWN
    assert not status.enforced


def test_require_enforced_raises_when_readable(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")
    with pytest.raises(PermissionError, match="not verifiably enforced"):
        require_enforced(tmp_path)


def test_require_enforced_refuses_an_elevated_caller(tmp_path, monkeypatch):
    """Elevated callers cannot demonstrate the boundary, so they are refused."""

    _elevated(monkeypatch)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")
    with pytest.raises(PermissionError, match="indeterminate_elevated"):
        require_enforced(tmp_path)


def test_require_enforced_passes_when_denied(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    monkeypatch.setattr(isolation, "can_read_raw", lambda root: False)
    require_enforced(tmp_path)


def test_require_enforced_reports_the_remedy(tmp_path, monkeypatch):
    _unelevated(monkeypatch)
    (tmp_path / "lossyear.tif").write_bytes(b"raw")
    with pytest.raises(PermissionError, match="inheritance:r"):
        require_enforced(tmp_path)


def test_setup_uses_no_deny_ace(tmp_path):
    """A deny would outrank the Administrators allow and lock out elevation.

    That is precisely what broke acquisition under the previous model.
    """

    joined = "\n".join(setup_commands(tmp_path))
    assert "/deny" not in joined
    assert "/inheritance:r" in joined
    assert 'grant "Administrators' in joined
    assert 'grant "SYSTEM' in joined


def test_can_read_raw_detects_readable_and_missing(tmp_path):
    assert can_read_raw(tmp_path / "absent") is None
    (tmp_path / "tile.tif").write_bytes(b"x")
    assert can_read_raw(tmp_path) is True


def test_enforced_requires_every_condition():
    """`enforced` is conservative by construction."""

    assert IsolationStatus(ENFORCED, False, True, False, "").enforced
    assert not IsolationStatus(NOT_ENFORCED, False, True, True, "").enforced
    assert not IsolationStatus(INDETERMINATE_ELEVATED, True, True, True, "").enforced
    assert not IsolationStatus(UNKNOWN, False, True, None, "").enforced


def test_live_isolation_denies_the_analysis_account():
    """Live check against the real directory.

    Runs unelevated in the normal test environment, which is exactly the
    context the guarantee is about.  Skipped only when elevated, where the
    observation would be meaningless.
    """

    from risk.config import HANSEN_DIR

    if isolation.is_elevated():
        pytest.skip("test suite is elevated; the boundary is only observable unelevated")

    status = isolation_status(HANSEN_DIR)
    if status.state == UNKNOWN and not Path(HANSEN_DIR).exists():
        pytest.skip("raw GFC root does not exist yet")
    assert status.enforced, status.detail
