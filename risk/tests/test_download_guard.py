import errno
import json
import os
import shutil
import time
import uuid

import numpy as np
import pytest
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin

import risk.download_timeseries as download_timeseries


class _Cube:
    def download(self, destination, format):
        raise AssertionError("download should not have been called")


def _write_tiff(path, count=1, width=16, height=16, value=1, nodata=None,
                tiled=False):
    data = np.full((count, height, width), value, dtype=np.uint16)
    options = {}
    if tiled:
        options.update(tiled=True, blockxsize=16, blockysize=16)
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=count,
        dtype=data.dtype, nodata=nodata, crs="EPSG:4326",
        transform=from_origin(0, height, 1, 1), **options,
    ) as destination:
        destination.write(data)
    return path


def _truncate_last_tile(path):
    original_size = path.stat().st_size
    with path.open("r+b") as stream:
        stream.truncate(original_size - 256)
    return path


def _write_truncated_tiff(path):
    _write_tiff(path, width=64, height=64, tiled=True)
    return _truncate_last_tile(path)


def _assert_no_temps(destination):
    assert list(destination.parent.glob(f"{destination.name}.*.part")) == []


def test_late_tile_truncation_fails_after_an_early_tile_still_reads(tmp_path):
    path = _write_tiff(tmp_path / "late-tile.tif", width=64, height=64, tiled=True)
    with rasterio.open(path) as source:
        windows = [window for _, window in source.block_windows(1)]
        assert len(windows) > 1

    _truncate_last_tile(path)
    with rasterio.open(path) as source:
        early = source.read(1, window=windows[0])
        assert early.shape == (16, 16)
        with pytest.raises(RasterioIOError):
            source.read(1, window=windows[-1])

    assert download_timeseries._decodes(path, expected_band_count=1) is False


def test_valid_all_nodata_raster_decodes(tmp_path):
    path = _write_tiff(tmp_path / "nodata.tif", value=0, nodata=0)
    assert download_timeseries._decodes(path, expected_band_count=1) is True


def test_legitimately_small_raster_decodes(tmp_path):
    path = _write_tiff(tmp_path / "small.tif", width=1, height=1)
    assert path.stat().st_size < 1_000
    assert download_timeseries._decodes(path, expected_band_count=1) is True


def test_wrong_band_count_is_rejected(tmp_path, monkeypatch):
    path = _write_tiff(tmp_path / "five-band.tif", count=5)
    assert download_timeseries._decodes(path, expected_band_count=6) is False

    destination = tmp_path / "wrong-band-download.tif"
    cube = _Cube()
    monkeypatch.setattr(
        cube, "download", lambda part, format: shutil.copyfile(path, part),
    )
    with pytest.raises(download_timeseries._CorruptDownload):
        download_timeseries._download(
            cube, destination, expected_band_count=6, retries=1,
        )
    assert not destination.exists()
    _assert_no_temps(destination)


def test_wrapped_environmental_error_propagates_without_deleting_final(
        tmp_path, monkeypatch):
    destination = tmp_path / "existing.tif"
    destination.write_bytes(b"existing evidence")
    cube = _Cube()

    def wrapped_permission(*args, **kwargs):
        try:
            raise PermissionError(errno.EACCES, "permission denied")
        except PermissionError as cause:
            raise RasterioIOError("TIFFReadEncodedTile() failed") from cause

    monkeypatch.setattr(download_timeseries.rasterio, "open", wrapped_permission)
    with pytest.raises(RasterioIOError, match="TIFFReadEncodedTile"):
        download_timeseries._download(cube, destination, expected_band_count=1, retries=1)

    assert destination.read_bytes() == b"existing evidence"
    assert not download_timeseries._marker_path(destination).exists()


def test_nonzero_partial_after_download_exception_is_removed(tmp_path, monkeypatch):
    destination = tmp_path / "partial.tif"
    cube = _Cube()

    def download(part, format):
        assert format == "GTiff"
        part.write_bytes(b"nonzero partial download")
        raise RuntimeError("simulated interrupted download")

    monkeypatch.setattr(cube, "download", download)
    with pytest.raises(RuntimeError, match="simulated interrupted"):
        download_timeseries._download(cube, destination, expected_band_count=1, retries=1)

    assert not destination.exists()
    assert not download_timeseries._marker_path(destination).exists()
    _assert_no_temps(destination)


def test_corrupt_download_retries_then_publishes_good_file_and_marker(
        tmp_path, monkeypatch):
    corrupt = _write_truncated_tiff(tmp_path / "corrupt-source.tif")
    good = _write_tiff(tmp_path / "good-source.tif")
    destination = tmp_path / "published.tif"
    cube = _Cube()
    sources = iter((corrupt, good))
    attempts = []

    def download(part, format):
        attempts.append(part)
        shutil.copyfile(next(sources), part)

    monkeypatch.setattr(cube, "download", download)
    monkeypatch.setattr(download_timeseries.time, "sleep", lambda seconds: None)
    download_timeseries._download(cube, destination, expected_band_count=1, retries=2)

    assert len(attempts) == 2
    assert attempts[0] != attempts[1]
    assert download_timeseries._decodes(destination, expected_band_count=1) is True
    marker = json.loads(
        download_timeseries._marker_path(destination).read_text(encoding="utf-8")
    )
    stat = destination.stat()
    assert marker == {
        "validator_version": download_timeseries._VALIDATOR_VERSION,
        "expected_band_count": 1,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    _assert_no_temps(destination)


def test_final_corrupt_attempt_leaves_neither_temp_nor_destination(
        tmp_path, monkeypatch):
    corrupt = _write_truncated_tiff(tmp_path / "always-corrupt.tif")
    destination = tmp_path / "never-published.tif"
    cube = _Cube()
    attempts = []

    def download(part, format):
        attempts.append(part)
        shutil.copyfile(corrupt, part)

    monkeypatch.setattr(cube, "download", download)
    monkeypatch.setattr(download_timeseries.time, "sleep", lambda seconds: None)
    with pytest.raises(download_timeseries._CorruptDownload):
        download_timeseries._download(cube, destination, expected_band_count=1, retries=2)

    assert len(attempts) == 2
    assert not destination.exists()
    assert not download_timeseries._marker_path(destination).exists()
    _assert_no_temps(destination)


def test_marker_backed_resume_skips_decode_and_markerless_file_decodes_once(
        tmp_path, monkeypatch):
    destination = _write_tiff(tmp_path / "resume.tif")
    cube = _Cube()
    real_decodes = download_timeseries._decodes
    calls = []

    def counting_decodes(path, expected_band_count):
        calls.append((path, expected_band_count))
        return real_decodes(path, expected_band_count)

    monkeypatch.setattr(download_timeseries, "_decodes", counting_decodes)
    download_timeseries._download(cube, destination, expected_band_count=1, retries=1)
    assert calls == [(destination, 1)]
    assert download_timeseries._marker_path(destination).exists()

    monkeypatch.setattr(
        download_timeseries, "_decodes",
        lambda *args, **kwargs: pytest.fail("matching marker must skip decoding"),
    )
    download_timeseries._download(cube, destination, expected_band_count=1, retries=1)


def test_malformed_and_stale_version_markers_are_cache_misses(tmp_path, monkeypatch):
    malformed = _write_tiff(tmp_path / "malformed.tif")
    stale = _write_tiff(tmp_path / "stale-version.tif")
    download_timeseries._marker_path(malformed).write_text("{broken", encoding="utf-8")
    stale_stat = stale.stat()
    download_timeseries._marker_path(stale).write_text(json.dumps({
        "validator_version": download_timeseries._VALIDATOR_VERSION + 1,
        "expected_band_count": 1,
        "size": stale_stat.st_size,
        "mtime_ns": stale_stat.st_mtime_ns,
    }), encoding="utf-8")
    cube = _Cube()
    real_decodes = download_timeseries._decodes
    calls = []

    def counting_decodes(path, expected_band_count):
        calls.append(path)
        return real_decodes(path, expected_band_count)

    monkeypatch.setattr(download_timeseries, "_decodes", counting_decodes)
    download_timeseries._download(cube, malformed, expected_band_count=1, retries=1)
    download_timeseries._download(cube, stale, expected_band_count=1, retries=1)

    assert calls == [malformed, stale]
    for destination in (malformed, stale):
        marker = json.loads(
            download_timeseries._marker_path(destination).read_text(encoding="utf-8")
        )
        assert marker["validator_version"] == download_timeseries._VALIDATOR_VERSION


def test_leftover_temp_cannot_collide_with_a_fresh_unique_attempt(tmp_path, monkeypatch):
    good = _write_tiff(tmp_path / "collision-source.tif")
    destination = tmp_path / "collision.tif"
    old_temp = destination.with_name(
        f"{destination.name}.999999.{uuid.uuid4().hex}.part"
    )
    old_temp.write_bytes(b"stale partial")
    old_time = time.time() - download_timeseries._ORPHAN_TEMP_MIN_AGE_SECONDS - 1
    os.utime(old_temp, (old_time, old_time))
    cube = _Cube()
    attempts = []

    def download(part, format):
        attempts.append(part)
        shutil.copyfile(good, part)

    monkeypatch.setattr(download_timeseries, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(cube, "download", download)
    download_timeseries._download(cube, destination, expected_band_count=1, retries=1)

    assert attempts[0] != old_temp
    assert not old_temp.exists()
    assert download_timeseries._decodes(destination, expected_band_count=1) is True


def test_live_foreign_data_and_marker_temps_survive_orphan_sweep(tmp_path):
    destination = _write_tiff(tmp_path / "live-owner.tif")
    download_timeseries._write_marker(destination, expected_band_count=1)
    live_temps = [
        destination.with_name(
            f"{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
        ),
        destination.with_name(
            f"{destination.name}.ok.{os.getpid()}.{uuid.uuid4().hex}.part"
        ),
    ]
    old_time = time.time() - download_timeseries._ORPHAN_TEMP_MIN_AGE_SECONDS - 1
    for temp in live_temps:
        temp.write_bytes(b"active foreign work")
        os.utime(temp, (old_time, old_time))

    download_timeseries._download(_Cube(), destination, expected_band_count=1, retries=1)

    assert all(temp.exists() for temp in live_temps)


def test_unclassified_rasterio_error_propagates_without_deleting_final(
        tmp_path, monkeypatch):
    destination = tmp_path / "unclassified.tif"
    destination.write_bytes(b"existing final")

    def unclassified(*args, **kwargs):
        raise RasterioIOError("mysterious GDAL condition")

    monkeypatch.setattr(download_timeseries.rasterio, "open", unclassified)
    with pytest.raises(RasterioIOError, match="mysterious GDAL condition"):
        download_timeseries._download(
            _Cube(), destination, expected_band_count=1, retries=1,
        )

    assert destination.read_bytes() == b"existing final"
    assert not download_timeseries._marker_path(destination).exists()
