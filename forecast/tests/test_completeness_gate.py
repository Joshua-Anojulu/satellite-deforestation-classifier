from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

from forecast.download_schedule import COMPOSITE_KINDS, build_download_schedule
from forecast.specification_w import build_amendment_artifacts, sha256_file
from forecast.tests.test_download_schedule import _inventory
from forecast.tests.test_specification_w import _write_primary_artifacts
from risk.census.verify_composites import (
    BAND_SCHEMAS,
    expected_inventory,
    main as completeness_main,
    verify_composites,
)


def _artifacts(tmp_path):
    primary = _write_primary_artifacts(tmp_path / "source")
    manifest = build_amendment_artifacts(
        primary, tmp_path / "w", new_site_window_start=lambda _: 6
    )["manifest"]
    schedule = tmp_path / "w" / "specification_w_download_schedule.json"
    build_download_schedule(manifest, _inventory(manifest), schedule)
    return manifest, schedule


def _write_tiff(path: Path, kind: str, *, nodata_only: bool = False) -> None:
    descriptions = BAND_SCHEMAS[kind]
    count = len(descriptions)
    values = np.zeros((count, 1, 1), dtype=np.float32) if nodata_only else np.ones(
        (count, 1, 1), dtype=np.float32
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=1,
        height=1,
        count=count,
        dtype="float32",
        nodata=0,
        crs="EPSG:4326",
        transform=Affine(1, 0, 0, 0, -1, 1),
    ) as destination:
        destination.write(values)
        for band, description in enumerate(descriptions, start=1):
            destination.set_band_description(band, description)


def _write_complete_archive(manifest_path: Path, schedule_path: Path, root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    scheduled = {(entry["site_id"], entry["year"]) for entry in schedule["entries"]}
    schedule_hash = sha256_file(schedule_path)
    for site in manifest["sites"]:
        directory = root / site["candidate_id"]
        directory.mkdir(parents=True, exist_ok=True)
        for year in range(2018, 2023):
            provenance = {
                "site": site["candidate_id"],
                "year": year,
                "period": site["periods"][str(year)],
                "process_graphs": {kind: {} for kind in COMPOSITE_KINDS},
            }
            if (site["candidate_id"], year) in scheduled:
                provenance.update({
                    "specification": "Specification W",
                    "specification_status": "AMENDED / EXPLORATORY",
                    "schedule": {"sha256": schedule_hash},
                })
            (directory / f"{year}_provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            for kind in COMPOSITE_KINDS:
                _write_tiff(directory / f"{year}_{kind}.tif", kind)


def test_manifest_inventory_is_720_total_and_576_new(tmp_path):
    manifest_path, schedule_path = _artifacts(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    inventory = expected_inventory(manifest, schedule)
    assert len(inventory) == 720
    assert sum(artifact.newly_scheduled for artifact in inventory) == 576
    assert len({artifact.relative_path for artifact in inventory}) == 720


def test_complete_archive_passes_and_pins_every_checksum(tmp_path):
    manifest_path, schedule_path = _artifacts(tmp_path)
    root = tmp_path / "composites"
    _write_complete_archive(manifest_path, schedule_path, root)
    report = verify_composites(manifest_path, schedule_path, root)
    assert report["complete"] is True
    assert report["analysis_allowed"] is True
    assert report["expected_tiffs"] == 720
    assert report["expected_new_tiffs"] == 576
    assert report["observed_expected_tiffs"] == 720
    assert len(report["artifact_sha256"]) == 720
    assert all(value == 0 for value in report["issue_counts"].values())


def test_missing_corrupt_all_nodata_schema_provenance_and_unexpected_fail_closed(tmp_path):
    manifest_path, schedule_path = _artifacts(tmp_path)
    root = tmp_path / "composites"
    _write_complete_archive(manifest_path, schedule_path, root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first, second, third, fourth, fifth = manifest["sites"][:5]

    (root / first["candidate_id"] / "2018_reflectance.tif").unlink()
    (root / second["candidate_id"] / "2018_dispersion.tif").write_bytes(b"corrupt")
    _write_tiff(
        root / third["candidate_id"] / "2018_clearobs.tif", "clearobs", nodata_only=True
    )
    schema_path = root / fourth["candidate_id"] / "2018_solar_zenith.tif"
    with rasterio.open(schema_path, "r+") as destination:
        destination.set_band_description(1, "wrong")
    provenance_path = root / fifth["candidate_id"] / "2021_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["period"] = ["1900-01-01", "1900-01-02"]
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    _write_tiff(root / first["candidate_id"] / "2023_reflectance.tif", "reflectance")

    report = verify_composites(manifest_path, schedule_path, root)
    assert report["complete"] is False
    assert report["analysis_allowed"] is False
    assert report["partial_archive_is_resumable_but_not_analysable"] is True
    assert report["issue_counts"]["MISSING"] == 1
    assert report["issue_counts"]["UNEXPECTED"] == 1
    assert report["issue_counts"]["CORRUPT"] == 1
    assert report["issue_counts"]["ALL_NODATA"] == 1
    assert report["issue_counts"]["SCHEMA"] == 1
    assert report["issue_counts"]["PROVENANCE"] == 1


def test_checksum_pinned_archive_rejects_later_mutation(tmp_path):
    manifest_path, schedule_path = _artifacts(tmp_path)
    root = tmp_path / "composites"
    _write_complete_archive(manifest_path, schedule_path, root)
    first = verify_composites(manifest_path, schedule_path, root)
    pins = tmp_path / "inventory.json"
    pins.write_text(json.dumps(first["artifact_sha256"], sort_keys=True), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = root / manifest["sites"][0]["candidate_id"] / "2018_clearobs.tif"
    with rasterio.open(changed, "r+") as destination:
        destination.write(np.full((1, 1), 2, dtype=np.float32), 1)
    report = verify_composites(
        manifest_path, schedule_path, root, pinned_inventory=pins
    )
    assert report["complete"] is False
    assert report["issue_counts"]["CHECKSUM"] == 1


def test_cli_exits_nonzero_for_an_incomplete_archive(tmp_path, monkeypatch):
    manifest_path, schedule_path = _artifacts(tmp_path)
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_composites",
            str(manifest_path),
            str(schedule_path),
            str(tmp_path / "empty-archive"),
            "--report",
            str(report_path),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        completeness_main()
    assert stopped.value.code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["complete"] is False
    assert report["issue_counts"]["MISSING"] == 720
