"""The post-lift seal must derive authority, not merely internal consistency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from forecast._embargo_seal import SEAL_SCHEMA_VERSION, build_seal, verify_seal

APPROVED_TREE = "0123456789abcdef0123456789abcdef01234567"
NAMESPACE = "specification_w_exploratory"


def _artifacts(root: Path) -> list[str]:
    (root / "manifest.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "schedule.json").write_text('{"b": 2}', encoding="utf-8")
    return ["manifest.json", "schedule.json"]


def _seal_dir(tmp_path: Path) -> Path:
    store = tmp_path / "seal-store"
    store.mkdir()
    return store


def _write_seal(store: Path, document: dict) -> Path:
    path = store / "seal.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _verify(seal_path, root, *, store, names=None, approved=(APPROVED_TREE,)):
    return verify_seal(
        seal_path,
        root,
        approved_tree_shas=approved,
        expected_artifacts=names if names is not None else ["manifest.json", "schedule.json"],
        seal_store=store,
    )


def test_valid_seal_verifies(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    ))

    result = _verify(seal, root, store=store)
    assert result.verified
    assert result.artifact_count == 2
    assert result.generating_tree_sha == APPROVED_TREE


def test_forged_seal_of_sixty_four_character_strings_is_rejected(tmp_path):
    """The exact forgery the previous implementation admitted.

    `run_censoring` used to accept any non-empty mapping whose values were 64
    characters long, so this document passed with no artifact existing at all.
    """

    root = tmp_path / "artifacts"
    root.mkdir()
    _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, {
        "schema_version": SEAL_SCHEMA_VERSION,
        "generating_tree_sha": APPROVED_TREE,
        "result_namespace": NAMESPACE,
        "artifacts": {"all-frozen-artifacts": "a" * 64},
    })

    result = _verify(seal, root, store=store)
    assert not result.verified
    assert "unapproved artifacts" in result.reason or "omits required" in result.reason


def test_unapproved_generating_tree_is_rejected(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, build_seal(
        root, generating_tree_sha="f" * 40, result_namespace=NAMESPACE, artifacts=names
    ))

    result = _verify(seal, root, store=store)
    assert not result.verified
    assert "not approved" in result.reason


def test_extra_artifact_is_as_fatal_as_a_missing_one(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    (root / "extra.json").write_text("{}", encoding="utf-8")
    store = _seal_dir(tmp_path)

    omitted = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE,
        artifacts=["manifest.json"],
    ))
    missing_result = _verify(omitted, root, store=store)
    assert not missing_result.verified
    assert "omits required" in missing_result.reason

    padded = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE,
        artifacts=[*names, "extra.json"],
    ))
    extra_result = _verify(padded, root, store=store)
    assert not extra_result.verified
    assert "unapproved artifacts" in extra_result.reason


def test_mutated_artifact_breaks_the_seal(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    ))

    (root / "manifest.json").write_text('{"a": 999}', encoding="utf-8")
    result = _verify(seal, root, store=store)
    assert not result.verified
    assert "does not match" in result.reason


def test_missing_artifact_on_disk_breaks_the_seal(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    ))

    (root / "schedule.json").unlink()
    result = _verify(seal, root, store=store)
    assert not result.verified
    assert "missing" in result.reason


def test_seal_outside_the_worker_owned_store_is_rejected(tmp_path):
    """A seal the analysis account can rewrite is not a trust root."""

    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    seal = stray / "seal.json"
    seal.write_text(json.dumps(build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    )), encoding="utf-8")

    result = _verify(seal, root, store=store)
    assert not result.verified
    assert "outside the worker-owned seal store" in result.reason


def test_empty_trust_root_is_rejected(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    store = _seal_dir(tmp_path)
    seal = _write_seal(store, build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    ))

    assert not _verify(seal, root, store=store, approved=()).verified
    assert not _verify(seal, root, store=store, names=[]).verified


def test_build_seal_refuses_a_missing_artifact(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    with pytest.raises(FileNotFoundError):
        build_seal(
            root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE,
            artifacts=["nope.json"],
        )


def test_build_seal_records_real_digests(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    names = _artifacts(root)
    document = build_seal(
        root, generating_tree_sha=APPROVED_TREE, result_namespace=NAMESPACE, artifacts=names
    )
    expected = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    assert document["artifacts"]["manifest.json"] == expected
