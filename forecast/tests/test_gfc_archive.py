"""Acquisition must be derived, pinned, and fail closed."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest

from forecast.gfc_archive import (
    CONTAGION_HALO_PX,
    GFC_DEGREES_PER_PX,
    LAYERS,
    TileMetadata,
    TileRecord,
    build_inventory,
    download_tile,
    expected_downloads,
    head_tile,
    required_tiles,
    tile_id,
    tile_url,
    verify_archive,
    write_inventory_once,
)
from forecast.gfc_censor import FROZEN_GFC_RELEASE


# --- tile naming -----------------------------------------------------------

def test_tiles_are_named_by_their_top_left_corner():
    # 10S_060W spans latitude -10..-20 and longitude -60..-50.
    assert tile_id(-10.5, -59.5) == "10S_060W"
    assert tile_id(-19.9, -50.1) == "10S_060W"
    assert tile_id(0.5, 0.5) == "10N_000E"
    assert tile_id(-0.5, 10.5) == "00N_010E"


def test_northern_and_eastern_hemispheres_are_named_correctly():
    assert tile_id(5.0, 105.0) == "10N_100E"
    assert tile_id(-2.0, 22.0) == "00N_020E"


# --- derivation ------------------------------------------------------------

def _site(west, south, east, north):
    return {"west": west, "south": south, "east": east, "north": north}


def test_tile_set_is_derived_from_footprints():
    sites = [_site(-60.5, -10.5, -60.2, -10.2)]
    assert required_tiles(sites) == ("10S_070W",)


def test_halo_pulls_in_the_neighbouring_tile():
    """A footprint within the halo of a boundary needs the tile across it.

    This is why the inventory is derived rather than asserted.
    """

    pad = CONTAGION_HALO_PX * GFC_DEGREES_PER_PX  # ~0.01275 deg
    # East edge stops just SHORT of -60, so the footprint alone stays in one
    # tile but its halo reaches across the boundary.
    sites = [_site(-60.5, -10.5, -60.0 - pad / 2, -10.2)]
    tiles = required_tiles(sites)
    assert "10S_070W" in tiles
    assert "10S_060W" in tiles, "halo must pull in the tile across the boundary"


def test_zero_halo_would_have_missed_it():
    """Non-vacuity control: without the halo the neighbour is not derived."""

    pad = CONTAGION_HALO_PX * GFC_DEGREES_PER_PX
    sites = [_site(-60.5, -10.5, -60.0 - pad / 2, -10.2)]
    assert required_tiles(sites, halo_px=0) == ("10S_070W",)
    assert required_tiles(sites) == ("10S_060W", "10S_070W")


def test_empty_or_inverted_footprints_fail_closed():
    with pytest.raises(ValueError, match="no sites"):
        required_tiles([])
    with pytest.raises(ValueError, match="empty or inverted"):
        required_tiles([_site(1.0, 1.0, 0.0, 2.0)])
    with pytest.raises(ValueError, match="missing a usable footprint"):
        required_tiles([{"west": 0.0}])


def test_expected_downloads_covers_every_layer_per_tile():
    pairs = expected_downloads(["10S_060W", "00N_010E"])
    assert len(pairs) == 2 * len(LAYERS)
    assert ("lossyear", "10S_060W") in pairs


def test_url_layer_allow_list():
    assert tile_url("lossyear", "10S_060W").endswith(
        f"Hansen_{FROZEN_GFC_RELEASE}_lossyear_10S_060W.tif"
    )
    with pytest.raises(ValueError, match="frozen allow-list"):
        tile_url("treecover2050", "10S_060W")


# --- publisher metadata ----------------------------------------------------

class _FakeHeaders(dict):
    def __init__(self, mapping, goog_hashes):
        super().__init__(mapping)
        self._goog = goog_hashes

    def get_all(self, key):
        return self._goog if key == "x-goog-hash" else None


class _FakeResponse:
    def __init__(self, headers=None, body=b""):
        self.headers = headers
        self._body = io.BytesIO(body)

    def read(self, size=-1):
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _headers_for(body: bytes, *, generation="123", md5=None):
    digest = md5 or hashlib.md5(body).digest()
    encoded = base64.b64encode(digest).decode()
    return _FakeHeaders(
        {"Content-Length": str(len(body)), "x-goog-generation": generation},
        [f"crc32c=AAAAAA==", f"md5={encoded}"],
    )


def test_head_decodes_the_base64_md5():
    body = b"tile bytes"
    meta = head_tile(
        "lossyear", "10S_060W",
        opener=lambda request: _FakeResponse(_headers_for(body)),
    )
    assert meta.md5 == hashlib.md5(body).hexdigest()
    assert meta.generation == "123"
    assert meta.content_length == len(body)


def test_head_fails_closed_without_an_md5():
    headers = _FakeHeaders(
        {"Content-Length": "5", "x-goog-generation": "1"}, ["crc32c=AAAAAA=="]
    )
    with pytest.raises(ValueError, match="no md5"):
        head_tile("lossyear", "10S_060W", opener=lambda r: _FakeResponse(headers))


def test_head_fails_closed_without_a_generation():
    body = b"x"
    headers = _headers_for(body, generation="")
    with pytest.raises(ValueError, match="object generation"):
        head_tile("lossyear", "10S_060W", opener=lambda r: _FakeResponse(headers))


# --- download --------------------------------------------------------------

def _meta(body: bytes, **overrides) -> TileMetadata:
    fields = {
        "layer": "lossyear",
        "tile": "10S_060W",
        "url": "https://example/tile.tif",
        "md5": hashlib.md5(body).hexdigest(),
        "generation": "1",
        "content_length": len(body),
    }
    fields.update(overrides)
    return TileMetadata(**fields)


def test_download_verifies_and_returns_sha256(tmp_path):
    body = b"a complete tile"
    target = tmp_path / "tile.tif"
    digest = download_tile(
        _meta(body), target, opener=lambda url: _FakeResponse(body=body)
    )
    assert target.read_bytes() == body
    assert digest == hashlib.sha256(body).hexdigest()


def test_truncated_transfer_never_lands(tmp_path):
    """The documented silent-truncation weakness, closed."""

    body = b"a complete tile"
    target = tmp_path / "tile.tif"
    truncated = body[:5]
    with pytest.raises(ValueError, match="length mismatch"):
        download_tile(
            _meta(body), target, opener=lambda url: _FakeResponse(body=truncated)
        )
    assert not target.exists(), "a partial tile must never appear at the final path"
    assert not target.with_name(target.name + ".partial").exists()


def test_corrupted_transfer_never_lands(tmp_path):
    body = b"a complete tile"
    corrupt = b"b complete tile"  # same length, different bytes
    target = tmp_path / "tile.tif"
    with pytest.raises(ValueError, match="md5 mismatch"):
        download_tile(
            _meta(body), target, opener=lambda url: _FakeResponse(body=corrupt)
        )
    assert not target.exists()


# --- inventory and gate ----------------------------------------------------

def _record(layer, tile, path: Path) -> TileRecord:
    body = path.read_bytes()
    return TileRecord(
        layer=layer, tile=tile, url=tile_url(layer, tile), release=FROZEN_GFC_RELEASE,
        generation="1", md5=hashlib.md5(body).hexdigest(),
        sha256=hashlib.sha256(body).hexdigest(), content_length=len(body),
        width=1, height=1, dtype="uint8", nodata=None,
        transform=(1.0, 0.0, 0.0, 0.0, -1.0, 0.0), crs="EPSG:4326",
    )


def _archive(tmp_path: Path):
    root = tmp_path / "hansen"
    root.mkdir()
    records = []
    for layer in LAYERS:
        name = f"Hansen_{FROZEN_GFC_RELEASE}_{layer}_10S_060W.tif"
        path = root / name
        path.write_bytes(f"{layer} bytes".encode())
        records.append(_record(layer, "10S_060W", path))
    return root, records


def test_inventory_is_write_once(tmp_path):
    root, records = _archive(tmp_path)
    inventory = build_inventory(records)
    path = write_inventory_once(tmp_path / "inv.json", inventory)
    assert json.loads(path.read_text())["file_count"] == 3
    with pytest.raises(FileExistsError):
        write_inventory_once(path, inventory)


def test_inventory_refuses_to_be_empty():
    with pytest.raises(ValueError, match="empty GFC inventory"):
        build_inventory([])


def test_inventory_names_its_weaker_anchor(tmp_path):
    """The guarantee must be legible in the artifact, not just the log."""

    _, records = _archive(tmp_path)
    anchor = build_inventory(records)["pinning_anchor"]
    assert "NOT an independent" in anchor


def test_complete_archive_passes_the_gate(tmp_path):
    root, records = _archive(tmp_path)
    report = verify_archive(root, build_inventory(records))
    assert report["complete"] and report["analysis_allowed"]
    assert sum(report["issue_counts"].values()) == 0


def test_missing_tile_blocks_analysis(tmp_path):
    root, records = _archive(tmp_path)
    inventory = build_inventory(records)
    next(root.glob("*lossyear*")).unlink()
    report = verify_archive(root, inventory)
    assert not report["analysis_allowed"]
    assert report["issue_counts"]["MISSING"] == 1


def test_mutated_tile_blocks_analysis(tmp_path):
    root, records = _archive(tmp_path)
    inventory = build_inventory(records)
    target = next(root.glob("*datamask*"))
    target.write_bytes(b"datamask byteX")  # same length, different content
    report = verify_archive(root, inventory)
    assert not report["analysis_allowed"]
    assert report["issue_counts"]["CHECKSUM"] == 1


def test_unexpected_tile_blocks_analysis(tmp_path):
    root, records = _archive(tmp_path)
    inventory = build_inventory(records)
    (root / f"Hansen_{FROZEN_GFC_RELEASE}_lossyear_00N_000E.tif").write_bytes(b"stray")
    report = verify_archive(root, inventory)
    assert not report["analysis_allowed"]
    assert report["issue_counts"]["UNEXPECTED"] == 1
