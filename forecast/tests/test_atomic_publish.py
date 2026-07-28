"""Publication must commit the masks and the transition record together."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forecast import _atomic_publish as publish
from forecast._atomic_publish import (
    COMMITTED,
    ERROR_UNABLE_TO_MOVE_REPLACEMENT,
    ERROR_UNABLE_TO_MOVE_REPLACEMENT_2,
    ERROR_UNABLE_TO_REMOVE_REPLACED,
    EXPOSED,
    FAILED_CLOSED,
    UNCOMMITTED,
    classify,
    create_placeholder,
    publish_container,
    read_container,
    recover,
    write_container,
)

RECORD = {"event": "gfc_2023_embargo_lift", "timestamp_utc": "2030-01-01T00:00:00+00:00"}
PAYLOAD = {"positive_2023.npy": b"\x00\x01\x02", "handoff.json": b"{}"}


# --- state table semantics -------------------------------------------------

def test_success_is_committed():
    assert classify(None).status == COMMITTED
    assert classify(None).committed


def test_1175_is_uncommitted_and_retries_from_staging():
    outcome = classify(ERROR_UNABLE_TO_REMOVE_REPLACED)
    assert outcome.status == UNCOMMITTED
    assert "staging" in outcome.recovery


def test_1176_recovers_from_staging_never_from_backup():
    """With a non-NULL backup, 1176 leaves the new payload at staging.

    The backup holds the OLD placeholder, so recovering from it would
    republish the wrong content.
    """

    outcome = classify(ERROR_UNABLE_TO_MOVE_REPLACEMENT)
    assert outcome.status == UNCOMMITTED
    assert "retry from intact staging" in outcome.recovery
    assert "never from the backup" in outcome.recovery


def test_1177_is_exposed_and_rolls_forward_never_back():
    """The replacement may already be readable, so reversal is not sound."""

    outcome = classify(ERROR_UNABLE_TO_MOVE_REPLACEMENT_2)
    assert outcome.status == EXPOSED
    assert outcome.exposed
    assert "roll FORWARD" in outcome.recovery
    assert "never roll back" in outcome.recovery
    assert "never quarantine" in outcome.recovery


def test_unknown_error_fails_closed():
    outcome = classify(999_999)
    assert outcome.status == FAILED_CLOSED
    assert "publish nothing" in outcome.recovery


def test_recover_never_downgrades_an_exposed_commit_to_a_rollback():
    action = recover(classify(ERROR_UNABLE_TO_MOVE_REPLACEMENT_2))
    assert "roll FORWARD" in action
    assert "roll back" not in action.replace("never roll back", "")


# --- container -------------------------------------------------------------

def test_container_round_trips_payload_and_record(tmp_path):
    path = write_container(PAYLOAD, RECORD, tmp_path / "c.zip")
    payload, record = read_container(path)
    assert payload == PAYLOAD
    assert record == RECORD


def test_container_bytes_are_deterministic(tmp_path):
    first = write_container(PAYLOAD, RECORD, tmp_path / "a.zip").read_bytes()
    second = write_container(PAYLOAD, RECORD, tmp_path / "b.zip").read_bytes()
    assert first == second, "container must hash reproducibly for the seal"


# --- publication -----------------------------------------------------------

def test_publish_commits_payload_and_record_together(tmp_path):
    staging = write_container(PAYLOAD, RECORD, tmp_path / "staging.zip")
    destination = create_placeholder(tmp_path / "published" / "container.zip")
    backup = tmp_path / "backup.zip"

    outcome = publish_container(staging, destination, backup)

    assert outcome.committed
    payload, record = read_container(destination)
    # One object, so "exactly one of the two published" is unrepresentable.
    assert payload == PAYLOAD
    assert record == RECORD
    assert backup.exists(), "backup must hold the old placeholder"


def test_publish_requires_a_pre_existing_placeholder(tmp_path):
    """The placeholder is how the container inherits the destination ACL."""

    staging = write_container(PAYLOAD, RECORD, tmp_path / "staging.zip")
    with pytest.raises(FileNotFoundError, match="placeholder must pre-exist"):
        publish_container(staging, tmp_path / "absent.zip", tmp_path / "backup.zip")


def test_publish_requires_staging_to_exist(tmp_path):
    destination = create_placeholder(tmp_path / "container.zip")
    with pytest.raises(FileNotFoundError, match="staging container"):
        publish_container(tmp_path / "nope.zip", destination, tmp_path / "backup.zip")


def test_cross_volume_publication_is_refused(tmp_path, monkeypatch):
    """ReplaceFileW requires one volume; the atomicity argument assumes it."""

    staging = write_container(PAYLOAD, RECORD, tmp_path / "staging.zip")
    destination = create_placeholder(tmp_path / "container.zip")
    backup = tmp_path / "backup.zip"

    real = publish._volume_id

    def fake(path: Path):
        return "OTHER" if Path(path) == backup else real(path)

    monkeypatch.setattr(publish, "_volume_id", fake)
    with pytest.raises(ValueError, match="one volume"):
        publish_container(staging, destination, backup)


def test_onedrive_publication_root_is_refused(tmp_path):
    """OneDrive's minifilter sits outside the local-NTFS guarantee."""

    root = tmp_path / "OneDrive" / "published"
    root.mkdir(parents=True)
    with pytest.raises(ValueError, match="OneDrive"):
        publish.assert_local_non_reparse(root)


def test_plain_local_publication_root_is_accepted(tmp_path):
    root = tmp_path / "published"
    root.mkdir()
    publish.assert_local_non_reparse(root)


def test_missing_publication_root_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        publish.assert_local_non_reparse(tmp_path / "absent")
