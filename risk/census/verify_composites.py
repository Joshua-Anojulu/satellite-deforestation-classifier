"""Manifest-derived completeness gate for Specification W's composite archive.

Unlike the retired existence scan, this module starts from the frozen manifest
and schedule, derives every expected artifact, checks exact band schemas and
provenance, fully decodes every band, rejects all-nodata files, and exits nonzero
on any defect.  Unrelated site directories are outside its inventory.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import rasterio

from forecast.download_schedule import COMPOSITE_KINDS, validate_download_schedule
from forecast.specification_w import (
    ARCHIVE_YEARS,
    EXPECTED_TIFFS,
    NEW_TIFFS,
    SITES,
    sha256_file,
)
from risk.config import REFLECTANCE_BANDS

BAND_SCHEMAS = {
    "reflectance": tuple(REFLECTANCE_BANDS),
    "dispersion": tuple(REFLECTANCE_BANDS),
    "clearobs": ("clearobs",),
    "solar_zenith": ("sunZenithAngles",),
}


@dataclass(frozen=True)
class ExpectedArtifact:
    site_id: str
    year: int
    kind: str
    relative_path: str
    newly_scheduled: bool


def expected_inventory(
    manifest: Mapping[str, object], schedule: Mapping[str, object]
) -> tuple[ExpectedArtifact, ...]:
    """Derive the exact 720-TIFF frame inventory and mark the 576 new files."""

    validate_download_schedule(manifest, schedule)
    sites = manifest["sites"]
    if len(sites) != SITES:
        raise ValueError("completeness gate requires the complete 36-site manifest")
    scheduled = {
        (entry["site_id"], int(entry["year"])) for entry in schedule["entries"]
    }
    expected = tuple(
        ExpectedArtifact(
            site_id=site["candidate_id"],
            year=year,
            kind=kind,
            relative_path=f"{site['candidate_id']}/{year}_{kind}.tif",
            newly_scheduled=(site["candidate_id"], year) in scheduled,
        )
        for site in sites
        for year in ARCHIVE_YEARS
        for kind in COMPOSITE_KINDS
    )
    if len(expected) != EXPECTED_TIFFS or sum(
        artifact.newly_scheduled for artifact in expected
    ) != NEW_TIFFS:
        raise AssertionError("manifest-derived inventory is not 720 total / 576 new")
    return expected


def _valid_data_present(source: rasterio.io.DatasetReader) -> bool:
    any_valid = False
    for band in range(1, source.count + 1):
        values = source.read(band)  # full read: catches late-block corruption
        valid = source.read_masks(band) > 0
        if np.issubdtype(values.dtype, np.floating):
            valid &= np.isfinite(values)
        any_valid |= bool(valid.any())
    return any_valid


def _validate_provenance(
    provenance: Mapping[str, object],
    *,
    site: Mapping[str, object],
    year: int,
    newly_scheduled: bool,
    schedule_hash: str,
) -> str | None:
    if provenance.get("site") != site["candidate_id"] or int(provenance.get("year", -1)) != year:
        return "site/year provenance mismatch"
    if list(provenance.get("period", ())) != list(site["periods"][str(year)]):
        return "seasonal-period provenance mismatch"
    graphs = provenance.get("process_graphs")
    if not isinstance(graphs, dict) or set(graphs) != set(COMPOSITE_KINDS):
        return "process-graph provenance mismatch"
    if newly_scheduled:
        if (
            provenance.get("specification") != "Specification W"
            or provenance.get("specification_status") != "AMENDED / EXPLORATORY"
        ):
            return "Specification W provenance missing"
        schedule = provenance.get("schedule")
        if not isinstance(schedule, dict) or schedule.get("sha256") != schedule_hash:
            return "download-schedule provenance mismatch"
    return None


def verify_composites(
    manifest_path: str | Path,
    schedule_path: str | Path,
    root: str | Path,
    *,
    pinned_inventory: str | Path | None = None,
) -> dict[str, object]:
    """Run the completeness gate and return a serializable report."""

    manifest_path = Path(manifest_path).resolve()
    schedule_path = Path(schedule_path).resolve()
    root = Path(root).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    if schedule["manifest"]["sha256"] != sha256_file(manifest_path):
        raise RuntimeError("manifest changed after the download schedule was frozen")
    expected = expected_inventory(manifest, schedule)
    expected_names = {artifact.relative_path for artifact in expected}
    site_ids = {site["candidate_id"] for site in manifest["sites"]}
    observed_names = {
        path.relative_to(root).as_posix()
        for site_id in site_ids
        for path in (root / site_id).glob("*.tif")
        if path.is_file()
    }
    issues: list[dict[str, str]] = []
    for name in sorted(expected_names - observed_names):
        issues.append({"path": name, "code": "MISSING", "detail": "expected TIFF absent"})
    for name in sorted(observed_names - expected_names):
        issues.append({"path": name, "code": "UNEXPECTED", "detail": "unmanifested frame TIFF"})

    sites = {site["candidate_id"]: site for site in manifest["sites"]}
    schedule_hash = sha256_file(schedule_path)
    provenance_cache: dict[tuple[str, int], Mapping[str, object] | None] = {}
    checksums: dict[str, str] = {}
    for artifact in expected:
        path = root / artifact.relative_path
        if not path.is_file():
            continue
        pair = (artifact.site_id, artifact.year)
        if pair not in provenance_cache:
            provenance_path = root / artifact.site_id / f"{artifact.year}_provenance.json"
            try:
                provenance_cache[pair] = json.loads(provenance_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                provenance_cache[pair] = None
                issues.append({
                    "path": provenance_path.relative_to(root).as_posix(),
                    "code": "PROVENANCE",
                    "detail": "missing or invalid provenance JSON",
                })
            if provenance_cache[pair] is not None:
                detail = _validate_provenance(
                    provenance_cache[pair],
                    site=sites[artifact.site_id],
                    year=artifact.year,
                    newly_scheduled=artifact.newly_scheduled,
                    schedule_hash=schedule_hash,
                )
                if detail:
                    issues.append({
                        "path": provenance_path.relative_to(root).as_posix(),
                        "code": "PROVENANCE",
                        "detail": detail,
                    })
        try:
            with rasterio.open(path) as source:
                expected_bands = BAND_SCHEMAS[artifact.kind]
                if source.count != len(expected_bands) or tuple(source.descriptions) != expected_bands:
                    issues.append({
                        "path": artifact.relative_path,
                        "code": "SCHEMA",
                        "detail": (
                            f"expected bands {expected_bands}, got count={source.count} "
                            f"descriptions={source.descriptions}"
                        ),
                    })
                if not _valid_data_present(source):
                    issues.append({
                        "path": artifact.relative_path,
                        "code": "ALL_NODATA",
                        "detail": "full decode found no valid pixel in any band",
                    })
            checksums[artifact.relative_path] = sha256_file(path)
        except Exception as error:
            issues.append({
                "path": artifact.relative_path,
                "code": "CORRUPT",
                "detail": f"{type(error).__name__}: {str(error)[:160]}",
            })

    if pinned_inventory is not None:
        pins = json.loads(Path(pinned_inventory).read_text(encoding="utf-8"))
        if pins != checksums:
            issues.append({
                "path": str(Path(pinned_inventory)),
                "code": "CHECKSUM",
                "detail": "archive differs from the checksum-pinned inventory",
            })
    issue_counts = {
        code: sum(issue["code"] == code for issue in issues)
        for code in ("MISSING", "UNEXPECTED", "PROVENANCE", "SCHEMA", "CORRUPT", "ALL_NODATA", "CHECKSUM")
    }
    complete = not issues and len(checksums) == EXPECTED_TIFFS
    return {
        "specification": "Specification W",
        "expected_tiffs": EXPECTED_TIFFS,
        "expected_new_tiffs": NEW_TIFFS,
        "observed_expected_tiffs": len(checksums),
        "complete": complete,
        "analysis_allowed": complete,
        "partial_archive_is_resumable_but_not_analysable": True,
        "issue_counts": issue_counts,
        "issues": issues,
        "artifact_sha256": dict(sorted(checksums.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("--pinned-inventory", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--inventory-output", type=Path)
    args = parser.parse_args()
    report = verify_composites(
        args.manifest, args.schedule, args.root,
        pinned_inventory=args.pinned_inventory,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.inventory_output and report["complete"]:
        args.inventory_output.parent.mkdir(parents=True, exist_ok=True)
        args.inventory_output.write_text(
            json.dumps(report["artifact_sha256"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    raise SystemExit(0 if report["complete"] else 1)


if __name__ == "__main__":
    main()

