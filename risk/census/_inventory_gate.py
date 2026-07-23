"""Checksum/inventory integrity helpers for the Specification W completeness gate.

Kept separate from ``verify_composites`` so the gate module stays focused on
inventory derivation and per-file decoding while this module owns the three
checksum concerns: cross-checking incumbents against the schedule's frozen
hashes, comparing the whole archive against a pinned inventory, and writing a
new inventory write-once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from forecast.download_schedule import COMPOSITE_KINDS, expected_verified_existing_pairs
from forecast.specification_w import sha256_file

_INCUMBENT_DETAIL = "incumbent artifact differs from the schedule's frozen checksum"
_PINNED_DETAIL = "archive differs from the checksum-pinned inventory"


def incumbent_checksum_issues(
    manifest: Mapping[str, object],
    schedule: Mapping[str, object],
    checksums: Mapping[str, str],
) -> list[dict[str, str]]:
    """Compare each of the 144 incumbent checksums with the schedule's frozen inventory.

    The schedule froze these hashes when it was created, so this catches a mutated
    incumbent that would otherwise be silently re-pinned.  A missing incumbent file
    is left to the MISSING check (it is absent from ``checksums``); only present
    files that disagree with the frozen hash are flagged, using the existing
    ``CHECKSUM`` code with an incumbent-specific detail.
    """

    frozen = schedule["verified_existing_inventory"]
    issues: list[dict[str, str]] = []
    for site_id, year in sorted(expected_verified_existing_pairs(manifest)):
        pinned = frozen.get(f"{site_id}/{year}", {})
        for kind in COMPOSITE_KINDS:
            relative_path = f"{site_id}/{year}_{kind}.tif"
            observed = checksums.get(relative_path)
            if observed is None:
                continue
            if observed != pinned.get(kind):
                issues.append({
                    "path": relative_path,
                    "code": "CHECKSUM",
                    "detail": _INCUMBENT_DETAIL,
                })
    return issues


def checksum_validation(
    checksums: Mapping[str, str],
    pinned_inventory: str | Path | None,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Compare the archive against a pinned inventory when one is supplied.

    Returns ``(issues, metadata)`` where ``metadata`` records whether a pinned
    comparison actually ran, so a report cannot claim verification it did not
    perform.  Without a pinned inventory the run is a bootstrap: no comparison,
    ``verified`` is False.
    """

    if pinned_inventory is None:
        return [], {"mode": "unpinned", "pinned_inventory_sha256": None, "verified": False}
    path = Path(pinned_inventory)
    pins = json.loads(path.read_text(encoding="utf-8"))
    verified = pins == dict(checksums)
    issues: list[dict[str, str]] = []
    if not verified:
        issues.append({"path": str(path), "code": "CHECKSUM", "detail": _PINNED_DETAIL})
    metadata = {
        "mode": "pinned",
        "pinned_inventory_sha256": sha256_file(path),
        "verified": verified,
    }
    return issues, metadata


def write_inventory_exclusive(path: str | Path, checksums: Mapping[str, str]) -> None:
    """Write the pinned inventory write-once; never overwrite an existing anchor."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(sorted(checksums.items())), indent=2, sort_keys=True) + "\n")
