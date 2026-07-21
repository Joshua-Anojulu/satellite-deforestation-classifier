from __future__ import annotations

import json

import pytest

from forecast.download_schedule import (
    COMPOSITE_KINDS,
    build_download_schedule,
    expected_verified_existing_pairs,
    validate_download_schedule,
)
from forecast.specification_w import sha256_file
from forecast.tests.test_specification_w import _write_primary_artifacts
from forecast.specification_w import build_amendment_artifacts
import risk.download_timeseries as downloader


def _manifest(tmp_path):
    primary = _write_primary_artifacts(tmp_path / "source")
    artifacts = build_amendment_artifacts(
        primary, tmp_path / "w", new_site_window_start=lambda _: 6
    )
    return artifacts["manifest"]


def _inventory(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        f"{site_id}/{year}": {kind: kind[0] * 64 for kind in COMPOSITE_KINDS}
        for site_id, year in expected_verified_existing_pairs(manifest)
    }


def test_schedule_is_exactly_144_missing_pairs_and_576_new_tiffs(tmp_path):
    manifest_path = _manifest(tmp_path)
    schedule_path = tmp_path / "w" / "specification_w_download_schedule.json"
    schedule = build_download_schedule(
        manifest_path, _inventory(manifest_path), schedule_path
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_download_schedule(manifest, schedule)

    assert schedule["verified_existing_site_years"] == 36
    assert schedule["verified_existing_tiffs"] == 144
    assert schedule["scheduled_site_years"] == 144
    assert schedule["scheduled_tiffs"] == 576
    assert len(schedule["entries"]) == 144
    assert len({(entry["site_id"], entry["year"]) for entry in schedule["entries"]}) == 144
    incumbent_entries = [
        entry for entry in schedule["entries"] if entry["amendment_role"] == "incumbent"
    ]
    addition_entries = [
        entry for entry in schedule["entries"] if entry["amendment_role"] == "addition"
    ]
    assert len(incumbent_entries) == 24
    assert {entry["year"] for entry in incumbent_entries} == {2021, 2022}
    assert len(addition_entries) == 120
    assert {entry["year"] for entry in addition_entries} == set(range(2018, 2023))
    sidecar = schedule_path.with_suffix(schedule_path.suffix + ".sha256")
    assert sidecar.read_text(encoding="ascii") == (
        f"{sha256_file(schedule_path)}  {schedule_path.name}\n"
    )


def test_schedule_rejects_unverified_or_extra_existing_pairs(tmp_path):
    manifest_path = _manifest(tmp_path)
    inventory = _inventory(manifest_path)
    inventory.pop(next(iter(inventory)))
    with pytest.raises(ValueError, match="exactly 12 x 3"):
        build_download_schedule(manifest_path, inventory, tmp_path / "schedule.json")


def test_schedule_validation_rejects_partial_archive_as_analysable(tmp_path):
    manifest_path = _manifest(tmp_path)
    schedule_path = tmp_path / "schedule.json"
    schedule = build_download_schedule(
        manifest_path, _inventory(manifest_path), schedule_path
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schedule["entries"].pop()
    with pytest.raises(ValueError, match="exact manifest-derived missing-pair"):
        validate_download_schedule(manifest, schedule)


def test_forecast_downloader_dry_run_visits_schedule_only(tmp_path, monkeypatch):
    manifest_path = _manifest(tmp_path)
    schedule_path = tmp_path / "schedule.json"
    schedule = build_download_schedule(
        manifest_path, _inventory(manifest_path), schedule_path
    )
    calls = []

    class Connection:
        pass

    monkeypatch.setattr("openeo.connect", lambda url: Connection())
    monkeypatch.setattr(downloader, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(downloader, "base_provenance", lambda: {})
    monkeypatch.setattr(downloader, "backend_provenance", lambda connection: {})
    monkeypatch.setattr(downloader, "buffered_bbox", lambda bbox: dict(bbox))

    def build_cubes(connection, bbox, period):
        calls.append((bbox, period))
        return {kind: object() for kind in COMPOSITE_KINDS}

    monkeypatch.setattr(downloader, "build_cubes", build_cubes)
    monkeypatch.setattr(
        downloader, "process_graphs", lambda cubes: {name: {} for name in cubes}
    )
    downloader.download_forecast_schedule(
        manifest_path, schedule_path, dry_run=True
    )
    assert len(calls) == schedule["scheduled_site_years"] == 144
    provenance = list((tmp_path / "raw").glob("*/????_provenance.json"))
    assert len(provenance) == 144

