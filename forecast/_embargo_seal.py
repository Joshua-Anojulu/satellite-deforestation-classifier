"""Seal verification for the post-lift embargo transition.

The previous check accepted any non-empty mapping of 64-character strings, so
``{"all-frozen-artifacts": "a" * 64}`` was admitted without a single artifact
existing.  Hashes prove *integrity*, never *authority*: a self-consistent
manifest listing self-consistent hashes of attacker-chosen files verifies
perfectly.  Authority therefore comes from three things this module requires and
the caller cannot supply implicitly:

1. an allow-list of **approved generating tree SHAs**,
2. a **complete artifact allow-list**, in which an extra artifact is exactly as
   fatal as a missing one, and
3. a **worker-owned seal store** the analysis account cannot write.

Verification recomputes every hash from disk.  The caller is expected to do so
while holding the transition lock, otherwise the result is only a statement
about the instant it was taken.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

SEAL_SCHEMA_VERSION = 1
_REQUIRED_SEAL_KEYS = frozenset(
    {"schema_version", "generating_tree_sha", "result_namespace", "artifacts"}
)


@dataclass(frozen=True)
class SealVerification:
    """The outcome of checking a seal against its trust root."""

    verified: bool
    reason: str
    generating_tree_sha: str | None = None
    artifact_count: int = 0

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.verified


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def verify_seal(
    seal_path: str | Path,
    artifact_root: str | Path,
    *,
    approved_tree_shas: Iterable[str],
    expected_artifacts: Iterable[str],
    seal_store: str | Path,
) -> SealVerification:
    """Verify a seal manifest against its trust root.

    Every failure is reported as an unverified result rather than an exception so
    the caller maps it to ``EMBARGO_NOT_SEALED`` uniformly; nothing here should
    be recoverable by retrying.
    """

    seal_path = Path(seal_path)
    artifact_root = Path(artifact_root)
    seal_store = Path(seal_store)
    approved = {str(value).lower() for value in approved_tree_shas}
    expected = set(expected_artifacts)

    if not approved:
        return SealVerification(False, "no approved tree SHA is configured")
    if not expected:
        return SealVerification(False, "artifact allow-list is empty")

    # (3) The seal must live in the worker-owned store.  A seal the analysis
    # account can rewrite is not a trust root, however well-formed it is.
    if not _is_within(seal_path, seal_store):
        return SealVerification(False, "seal is outside the worker-owned seal store")
    if not seal_path.is_file():
        return SealVerification(False, "seal manifest does not exist")

    try:
        document: Any = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SealVerification(False, "seal manifest is unreadable")
    if not isinstance(document, Mapping) or set(document) != _REQUIRED_SEAL_KEYS:
        return SealVerification(False, "seal schema mismatch")
    if document["schema_version"] != SEAL_SCHEMA_VERSION:
        return SealVerification(False, "seal schema version mismatch")

    # (1) Authority: the tree that produced the artifacts must be approved.
    tree_sha = str(document["generating_tree_sha"]).lower()
    if tree_sha not in approved:
        return SealVerification(False, "generating tree SHA is not approved", tree_sha)

    artifacts = document["artifacts"]
    if not isinstance(artifacts, Mapping) or not artifacts:
        return SealVerification(False, "seal lists no artifacts", tree_sha)

    # (2) Completeness in BOTH directions.  An extra artifact means the sealed
    # set is not the set that was approved, which is as disqualifying as a gap.
    listed = set(artifacts)
    missing = expected - listed
    extra = listed - expected
    if missing:
        return SealVerification(
            False, f"seal omits required artifacts: {sorted(missing)}", tree_sha
        )
    if extra:
        return SealVerification(
            False, f"seal lists unapproved artifacts: {sorted(extra)}", tree_sha
        )

    # Integrity: recompute every hash from disk.  Under the transition lock this
    # is a statement about the artifacts being published; outside it, it is not.
    for name in sorted(listed):
        recorded = str(artifacts[name])
        if len(recorded) != 64:
            return SealVerification(False, f"malformed digest for {name}", tree_sha)
        candidate = artifact_root / name
        if not _is_within(candidate, artifact_root):
            return SealVerification(False, f"artifact escapes its root: {name}", tree_sha)
        if not candidate.is_file():
            return SealVerification(False, f"sealed artifact is missing: {name}", tree_sha)
        try:
            actual = _sha256_file(candidate)
        except OSError:
            return SealVerification(False, f"sealed artifact is unreadable: {name}", tree_sha)
        if actual.lower() != recorded.lower():
            return SealVerification(False, f"sealed artifact does not match: {name}", tree_sha)

    return SealVerification(True, "verified", tree_sha, len(listed))


def build_seal(
    artifact_root: str | Path,
    *,
    generating_tree_sha: str,
    result_namespace: str,
    artifacts: Iterable[str],
) -> dict[str, object]:
    """Build a seal manifest by hashing the named artifacts on disk."""

    artifact_root = Path(artifact_root)
    names = sorted(set(artifacts))
    if not names:
        raise ValueError("a seal must cover at least one artifact")
    digests: dict[str, str] = {}
    for name in names:
        candidate = artifact_root / name
        if not _is_within(candidate, artifact_root):
            raise ValueError(f"artifact escapes its root: {name}")
        if not candidate.is_file():
            raise FileNotFoundError(f"cannot seal missing artifact: {name}")
        digests[name] = _sha256_file(candidate)
    return {
        "schema_version": SEAL_SCHEMA_VERSION,
        "generating_tree_sha": str(generating_tree_sha).lower(),
        "result_namespace": str(result_namespace),
        "artifacts": digests,
    }
