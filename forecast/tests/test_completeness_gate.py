from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

from forecast.download_schedule import (
    COMPOSITE_KINDS,
    build_download_schedule,
    expected_verified_existing_pairs,
)
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
    """Manifest + schedule with placeholder incumbent hashes.

    Only for tests that never run the gate against real files (the inventory-count
    test and the empty-archive CLI test), so placeholder hashes are never compared.
    """

    primary = _write_primary_artifacts(tmp_path / "source")
    manifest = build_amendment_artifacts(
        primary, tmp_path / "w", new_site_window_start=lambda _: 6
    )["manifest"]
    schedule = tmp_path / "w" / "specification_w_download_schedule.json"
    build_download_schedule(manifest, _inventory(manifest), schedule)
    return manifest, schedule


def _write_tiff(
    path: Path, kind: str, *, nodata_only: bool = False, fill: float | None = None
) -> None:
    descriptions = BAND_SCHEMAS[kind]
    count = len(descriptions)
    if nodata_only:
        values = np.zeros((count, 1, 1), dtype=np.float32)
    elif fill is not None:
        values = np.full((count, 1, 1), fill, dtype=np.float32)
    else:
        values = np.ones((count, 1, 1), dtype=np.float32)
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
            if description is not None:  # a None schema entry means an unnamed band
                destination.set_band_description(band, description)


def _complete_archive(tmp_path):
    """Build manifest, a full 720-TIFF archive, and a schedule with REAL incumbent
    hashes derived from the created files (so the incumbent cross-check passes)."""

    primary = _write_primary_artifacts(tmp_path / "source")
    manifest_path = build_amendment_artifacts(
        primary, tmp_path / "w", new_site_window_start=lambda _: 6
    )["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = tmp_path / "composites"

    # 1. Create every TIFF first (their hashes do not depend on the schedule).
    for site in manifest["sites"]:
        directory = root / site["candidate_id"]
        directory.mkdir(parents=True, exist_ok=True)
        for year in range(2018, 2023):
            for kind in COMPOSITE_KINDS:
                _write_tiff(directory / f"{year}_{kind}.tif", kind)

    # 2. Derive the 144 incumbent hashes from the actual files, then freeze them
    #    into the schedule (the independent anchor the gate checks against).
    inventory = {
        f"{site_id}/{year}": {
            kind: sha256_file(root / site_id / f"{year}_{kind}.tif")
            for kind in COMPOSITE_KINDS
        }
        for site_id, year in expected_verified_existing_pairs(manifest)
    }
    schedule_path = tmp_path / "w" / "specification_w_download_schedule.json"
    build_download_schedule(manifest_path, inventory, schedule_path)
    schedule_hash = sha256_file(schedule_path)
    scheduled = {
        (entry["site_id"], entry["year"])
        for entry in json.loads(schedule_path.read_text(encoding="utf-8"))["entries"]
    }

    # 3. Provenance (newly-scheduled files also carry the Specification W stamp).
    for site in manifest["sites"]:
        directory = root / site["candidate_id"]
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
    return manifest_path, schedule_path, root


def _pin(tmp_path, report) -> Path:
    pins = tmp_path / "inventory.json"
    pins.write_text(json.dumps(report["artifact_sha256"], sort_keys=True), encoding="utf-8")
    return pins


def _incumbent_site(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return next(
        site["candidate_id"]
        for site in manifest["sites"]
        if site["amendment_role"] == "incumbent"
    )


def test_manifest_inventory_is_720_total_and_576_new(tmp_path):
    manifest_path, schedule_path = _artifacts(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    inventory = expected_inventory(manifest, schedule)
    assert len(inventory) == 720
    assert sum(artifact.newly_scheduled for artifact in inventory) == 576
    assert len({artifact.relative_path for artifact in inventory}) == 720


def test_clearobs_band_is_unnamed_none(tmp_path):
    # Independent oracle (not derived from BAND_SCHEMAS): a real clearobs reads back
    # as a single unnamed band.
    path = tmp_path / "clearobs.tif"
    _write_tiff(path, "clearobs")
    with rasterio.open(path) as source:
        assert source.count == 1
        assert source.descriptions == (None,)


def test_checksum_validation_modes_and_analysis_gate(tmp_path):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)

    unpinned = verify_composites(manifest_path, schedule_path, root)
    assert unpinned["complete"] is True
    assert unpinned["checksum_validation"]["mode"] == "unpinned"
    assert unpinned["checksum_validation"]["verified"] is False
    assert unpinned["analysis_allowed"] is False  # complete, but not verified
    assert unpinned["expected_tiffs"] == 720
    assert unpinned["observed_expected_tiffs"] == 720
    assert len(unpinned["artifact_sha256"]) == 720
    assert all(value == 0 for value in unpinned["issue_counts"].values())

    pins = _pin(tmp_path, unpinned)
    pinned = verify_composites(manifest_path, schedule_path, root, pinned_inventory=pins)
    assert pinned["complete"] is True
    assert pinned["checksum_validation"]["mode"] == "pinned"
    assert pinned["checksum_validation"]["verified"] is True
    assert pinned["checksum_validation"]["pinned_inventory_sha256"] == sha256_file(pins)
    assert pinned["analysis_allowed"] is True
    assert all(value == 0 for value in pinned["issue_counts"].values())


def test_missing_corrupt_all_nodata_schema_provenance_and_unexpected_fail_closed(tmp_path):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first, second, third, fourth, fifth = manifest["sites"][:5]

    # All defects target 2021 (newly-scheduled for every site) so the incumbent
    # cross-check (2018-2020) is not perturbed and each contract stays isolated.
    (root / first["candidate_id"] / "2021_reflectance.tif").unlink()
    (root / second["candidate_id"] / "2021_dispersion.tif").write_bytes(b"corrupt")
    _write_tiff(
        root / third["candidate_id"] / "2021_clearobs.tif", "clearobs", nodata_only=True
    )
    with rasterio.open(root / fourth["candidate_id"] / "2021_solar_zenith.tif", "r+") as dst:
        dst.set_band_description(1, "wrong")
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
    assert report["issue_counts"]["SEMANTIC"] == 0
    assert report["issue_counts"]["CHECKSUM"] == 0


def test_named_clearobs_band_is_a_schema_failure(tmp_path):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = root / manifest["sites"][0]["candidate_id"] / "2021_clearobs.tif"
    with rasterio.open(target, "r+") as destination:
        destination.set_band_description(1, "wrong")
    report = verify_composites(manifest_path, schedule_path, root)
    assert report["issue_counts"]["SCHEMA"] == 1
    assert report["complete"] is False


@pytest.mark.parametrize(
    "fill, detail_fragment",
    [(-1.0, "negative"), (0.5, "non-integer")],
)
def test_semantically_impossible_clearobs_is_a_semantic_failure(tmp_path, fill, detail_fragment):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = root / manifest["sites"][0]["candidate_id"] / "2021_clearobs.tif"
    _write_tiff(target, "clearobs", fill=fill)
    report = verify_composites(manifest_path, schedule_path, root)
    assert report["issue_counts"]["SEMANTIC"] == 1
    semantic = [i for i in report["issues"] if i["code"] == "SEMANTIC"]
    assert detail_fragment in semantic[0]["detail"]
    assert report["complete"] is False


def test_unpinned_incumbent_mutation_fails_against_frozen_schedule_hashes(tmp_path):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    site_id = _incumbent_site(manifest_path)
    target = root / site_id / "2018_clearobs.tif"  # incumbent year, valid new value
    with rasterio.open(target, "r+") as destination:
        destination.write(np.full((1, 1), 5, dtype=np.float32), 1)
    report = verify_composites(manifest_path, schedule_path, root)  # unpinned
    assert report["issue_counts"]["CHECKSUM"] == 1
    checksum_issue = next(i for i in report["issues"] if i["code"] == "CHECKSUM")
    assert "incumbent" in checksum_issue["detail"]
    assert report["complete"] is False


def test_pinned_mutation_of_a_new_tiff_reports_failed_verification(tmp_path):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    bootstrap = verify_composites(manifest_path, schedule_path, root)
    pins = _pin(tmp_path, bootstrap)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = root / manifest["sites"][0]["candidate_id"] / "2021_clearobs.tif"  # new, not incumbent
    with rasterio.open(target, "r+") as destination:
        destination.write(np.full((1, 1), 7, dtype=np.float32), 1)
    report = verify_composites(manifest_path, schedule_path, root, pinned_inventory=pins)
    assert report["checksum_validation"]["mode"] == "pinned"
    assert report["checksum_validation"]["verified"] is False
    assert report["issue_counts"]["CHECKSUM"] == 1
    assert report["complete"] is False
    assert report["analysis_allowed"] is False


def test_inventory_output_is_write_once(tmp_path, monkeypatch):
    manifest_path, schedule_path, root = _complete_archive(tmp_path)
    inventory_out = tmp_path / "frame_inventory.json"
    inventory_out.write_text("SENTINEL", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_composites",
            str(manifest_path),
            str(schedule_path),
            str(root),
            "--inventory-output",
            str(inventory_out),
        ],
    )
    with pytest.raises(SystemExit):
        completeness_main()
    # the pre-existing anchor is untouched
    assert inventory_out.read_text(encoding="utf-8") == "SENTINEL"


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
