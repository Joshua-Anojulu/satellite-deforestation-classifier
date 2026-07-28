"""Acquisition and pinning of the frozen GFC outcome layer.

`HANSEN_DIR` was empty, so the study had no outcome layer at all: labels, the
eligibility mask and every SS8 hazard feature were unbuildable.  This module
acquires it under the pinning discipline the composites already have.

**Pinning anchor (deviation 1, see ANALYSIS-DRIVER-REVIEW-LOG.md).** There is no
independently published MD5 manifest for this release -- the official download
page ships URL listings and no checksums.  `FORECAST-PLAN.md` SS5 freezes
"Pin GFC version+md5 (at download...)", i.e. *record* the md5, which is
satisfiable.  The anchor used is Google Cloud Storage's own per-object metadata,
fetched by ``HEAD`` **before** the bytes are transferred:

* ``x-goog-hash: md5=<base64>`` -- server-computed, equal to the ``ETag`` hex,
* ``x-goog-generation`` -- an immutable object-version identifier,
* ``Content-Length`` -- cross-checked against bytes received.

That detects a truncated or corrupted transfer and silent re-publication under
the same name.  It does **not** detect substitution at source, because the same
host serves the bytes and the hash.  Never describe this archive as
"independently verified"; it is "pinned to the publisher's server-computed md5
and object generation at download".
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .gfc_censor import FROZEN_GFC_RELEASE

BASE_URL = f"https://storage.googleapis.com/earthenginepartners-hansen/{FROZEN_GFC_RELEASE}"
LAYERS = ("treecover2000", "lossyear", "datamask")
TILE_DEGREES = 10

#: R_max (50 px) + 1, per the plan's contagion halo.  Neighbourhood maths run on
#: the haloed array, so a site whose footprint reaches within the halo of a tile
#: boundary needs that neighbouring tile too.
CONTAGION_HALO_PX = 51
#: Pinned GFC grid spacing in degrees (30 m).
GFC_DEGREES_PER_PX = 0.00025


@dataclass(frozen=True)
class TileMetadata:
    """Publisher-side pinning metadata, fetched without transferring the file."""

    layer: str
    tile: str
    url: str
    md5: str
    generation: str
    content_length: int


@dataclass(frozen=True)
class TileRecord:
    """One inventory row: what was fetched, and everything that pins it."""

    layer: str
    tile: str
    url: str
    release: str
    generation: str
    md5: str
    sha256: str
    content_length: int
    width: int
    height: int
    dtype: str
    nodata: float | None
    transform: tuple[float, ...]
    crs: str


def tile_id(lat: float, lon: float) -> str:
    """Name the 10-degree GFC tile containing a point.

    Tiles are named by their TOP-LEFT corner, so ``10S_060W`` spans latitude
    -10..-20 and longitude -60..-50.
    """

    top = math.ceil(lat / TILE_DEGREES) * TILE_DEGREES
    left = math.floor(lon / TILE_DEGREES) * TILE_DEGREES
    ns = "N" if top >= 0 else "S"
    ew = "E" if left >= 0 else "W"
    return f"{abs(top):02d}{ns}_{abs(left):03d}{ew}"


def required_tiles(
    sites: Iterable[Mapping[str, object]],
    *,
    halo_px: int = CONTAGION_HALO_PX,
) -> tuple[str, ...]:
    """Derive the tile set from site footprints EXPANDED BY THE FULL HALO.

    Derived and fail-closed rather than asserted: a hardcoded count would not
    notice a site whose halo reaches across a tile boundary.
    """

    sites = list(sites)
    if not sites:
        raise ValueError("no sites supplied; refusing to derive an empty tile set")
    pad = halo_px * GFC_DEGREES_PER_PX
    tiles: set[str] = set()
    for site in sites:
        try:
            west = float(site["west"])
            east = float(site["east"])
            south = float(site["south"])
            north = float(site["north"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"site is missing a usable footprint: {site!r}") from exc
        if not (west < east and south < north):
            raise ValueError(f"site footprint is empty or inverted: {site!r}")
        for lat in (south - pad, north + pad):
            for lon in (west - pad, east + pad):
                tiles.add(tile_id(lat, lon))
    if not tiles:  # pragma: no cover - unreachable given the guard above
        raise ValueError("tile derivation produced nothing")
    return tuple(sorted(tiles))


def tile_url(layer: str, tile: str, release: str = FROZEN_GFC_RELEASE) -> str:
    if layer not in LAYERS:
        raise ValueError(f"layer {layer!r} is outside the frozen allow-list {LAYERS}")
    return f"{BASE_URL}/Hansen_{release}_{layer}_{tile}.tif"


def expected_downloads(tiles: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Every (layer, tile) pair the archive needs, in canonical order."""

    return tuple((layer, tile) for tile in sorted(tiles) for layer in LAYERS)


def _decode_goog_md5(header_value: str) -> str:
    """Extract the hex md5 from a ``x-goog-hash`` header value."""

    for part in header_value.split(","):
        part = part.strip()
        if part.startswith("md5="):
            return base64.b64decode(part[4:]).hex()
    raise ValueError(f"no md5 in x-goog-hash header: {header_value!r}")


def head_tile(layer: str, tile: str, *, opener=urllib.request.urlopen) -> TileMetadata:
    """Fetch the publisher's pinning metadata WITHOUT transferring the tile."""

    url = tile_url(layer, tile)
    request = urllib.request.Request(url, method="HEAD")
    with opener(request) as response:
        headers = response.headers
        hashes = headers.get_all("x-goog-hash") or []
        md5 = ""
        for value in hashes:
            try:
                md5 = _decode_goog_md5(value)
                break
            except ValueError:
                continue
        if not md5:
            raise ValueError(f"publisher served no md5 for {url}")
        generation = headers.get("x-goog-generation")
        if not generation:
            raise ValueError(f"publisher served no object generation for {url}")
        length = int(headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError(f"publisher served no content length for {url}")
    return TileMetadata(layer, tile, url, md5, str(generation), length)


def download_tile(
    metadata: TileMetadata,
    destination: Path,
    *,
    opener=urllib.request.urlopen,
    chunk_bytes: int = 4 * 1024 * 1024,
) -> str:
    """Download one tile, verifying it against the pre-fetched metadata.

    Writes to a temporary sibling and renames only after both the md5 and the
    byte count match, so a partial transfer can never be mistaken for a
    complete tile -- the exact silent-truncation weakness documented for the
    composite downloader.
    """

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    received = 0
    try:
        with opener(metadata.url) as response, partial.open("wb") as sink:
            while True:
                chunk = response.read(chunk_bytes)
                if not chunk:
                    break
                md5.update(chunk)
                sha256.update(chunk)
                received += len(chunk)
                sink.write(chunk)
        if received != metadata.content_length:
            raise ValueError(
                f"length mismatch for {metadata.url}: "
                f"expected {metadata.content_length}, received {received}"
            )
        if md5.hexdigest() != metadata.md5:
            raise ValueError(
                f"md5 mismatch for {metadata.url}: "
                f"expected {metadata.md5}, computed {md5.hexdigest()}"
            )
        partial.replace(destination)
    finally:
        if partial.exists():
            partial.unlink()
    return sha256.hexdigest()


def describe_raster(path: Path) -> dict[str, object]:
    """Read the structural facts the inventory records."""

    import rasterio

    with rasterio.open(path) as source:
        return {
            "width": int(source.width),
            "height": int(source.height),
            "dtype": str(source.dtypes[0]),
            "nodata": None if source.nodata is None else float(source.nodata),
            "transform": tuple(float(value) for value in tuple(source.transform)[:6]),
            "crs": source.crs.to_string() if source.crs else "",
        }


def build_inventory(records: Sequence[TileRecord]) -> dict[str, object]:
    """Assemble the write-once inventory document."""

    if not records:
        raise ValueError("refusing to build an empty GFC inventory")
    payload = {
        f"{record.layer}/{record.tile}": asdict(record)
        for record in sorted(records, key=lambda item: (item.layer, item.tile))
    }
    if len(payload) != len(records):
        raise ValueError("duplicate (layer, tile) in inventory")
    return {
        "schema_version": 1,
        "release": FROZEN_GFC_RELEASE,
        "pinning_anchor": (
            "publisher server-computed md5 + object generation at download; "
            "NOT an independent third-party manifest (none exists for this release)"
        ),
        "tile_count": len({record.tile for record in records}),
        "file_count": len(records),
        "tiles": payload,
    }


def write_inventory_once(path: str | Path, inventory: Mapping[str, object]) -> Path:
    """Write the inventory exclusively; an existing inventory is never rewritten."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as sink:
        sink.write(json.dumps(inventory, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path


def acquire(
    sites: Sequence[Mapping[str, object]],
    root: str | Path,
    *,
    halo_px: int = CONTAGION_HALO_PX,
    log=print,
) -> list[TileRecord]:
    """Preflight every URL, then download only what is missing or unverified.

    The preflight runs first so a broken or moved tile is discovered before
    ~11 GB is transferred, rather than partway through.
    """

    root = Path(root)
    tiles = required_tiles(sites, halo_px=halo_px)
    pairs = expected_downloads(tiles)
    log(f"derived {len(tiles)} tiles -> {len(pairs)} files (halo {halo_px} px)")

    log("preflight: fetching publisher metadata for every file...")
    metadata = [head_tile(layer, tile) for layer, tile in pairs]
    total = sum(item.content_length for item in metadata)
    log(f"preflight ok: {len(metadata)}/{len(pairs)} resolved, {total / 1e9:.2f} GB")

    records: list[TileRecord] = []
    for index, meta in enumerate(metadata, 1):
        name = f"Hansen_{FROZEN_GFC_RELEASE}_{meta.layer}_{meta.tile}.tif"
        target = root / name
        if target.is_file() and target.stat().st_size == meta.content_length:
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
            log(f"[{index}/{len(metadata)}] have {name}")
        else:
            log(f"[{index}/{len(metadata)}] fetching {name} ({meta.content_length / 1e6:.0f} MB)")
            sha256 = download_tile(meta, target)
        structure = describe_raster(target)
        records.append(TileRecord(
            layer=meta.layer, tile=meta.tile, url=meta.url, release=FROZEN_GFC_RELEASE,
            generation=meta.generation, md5=meta.md5, sha256=sha256,
            content_length=meta.content_length, **structure,  # type: ignore[arg-type]
        ))
    return records


def main() -> None:
    """CLI entry point.

    Must run with write access to the raw-GFC directory, which the interactive
    analysis account is denied by design (see forecast/_raw_gfc_isolation.py).
    Run it elevated or as the worker account.
    """

    import argparse

    from risk.config import HANSEN_DIR

    parser = argparse.ArgumentParser(description="Acquire and pin the frozen GFC archive.")
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).with_name("artifacts") / "specification_w_manifest.json")
    parser.add_argument("--root", type=Path, default=Path(HANSEN_DIR))
    parser.add_argument("--inventory", type=Path,
                        default=Path(__file__).with_name("artifacts") / "gfc_archive_inventory.json")
    parser.add_argument("--report", type=Path,
                        default=Path(__file__).with_name("artifacts") / "gfc_archive_verify_report.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = acquire(manifest["sites"], args.root)

    inventory = build_inventory(records)
    if args.inventory.exists():
        existing = json.loads(args.inventory.read_text(encoding="utf-8"))
        if existing != inventory:
            raise SystemExit(
                f"refusing to overwrite the write-once inventory at {args.inventory}; "
                "the archive no longer matches what was pinned"
            )
        print(f"inventory unchanged: {args.inventory}")
    else:
        write_inventory_once(args.inventory, inventory)
        print(f"wrote write-once inventory: {args.inventory}")

    report = verify_archive(args.root, inventory)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"wrote verification report: {args.report}")
    print(f"complete={report['complete']} analysis_allowed={report['analysis_allowed']} "
          f"issues={report['issue_counts']}")
    if not report["analysis_allowed"]:
        raise SystemExit("GFC archive did not certify")


def verify_archive(root: str | Path, inventory: Mapping[str, object]) -> dict[str, object]:
    """Gate the archive: complete, pinned, and matching the recorded digests."""

    root = Path(root)
    issues: list[dict[str, str]] = []
    counts = {"MISSING": 0, "CHECKSUM": 0, "LENGTH": 0, "UNEXPECTED": 0}
    tiles = inventory["tiles"]
    assert isinstance(tiles, Mapping)

    expected_names = set()
    for key, record in tiles.items():
        layer, tile = key.split("/", 1)
        name = f"Hansen_{inventory['release']}_{layer}_{tile}.tif"
        expected_names.add(name)
        candidate = root / name
        if not candidate.is_file():
            counts["MISSING"] += 1
            issues.append({"code": "MISSING", "detail": name})
            continue
        size = candidate.stat().st_size
        if size != record["content_length"]:
            counts["LENGTH"] += 1
            issues.append({"code": "LENGTH", "detail": f"{name}: {size}"})
            continue
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != record["sha256"]:
            counts["CHECKSUM"] += 1
            issues.append({"code": "CHECKSUM", "detail": name})

    for present in root.glob("Hansen_*.tif"):
        if present.name not in expected_names:
            counts["UNEXPECTED"] += 1
            issues.append({"code": "UNEXPECTED", "detail": present.name})

    complete = not issues
    return {
        "release": inventory["release"],
        "expected_files": inventory["file_count"],
        "observed_files": len(expected_names) - counts["MISSING"],
        "issue_counts": counts,
        "issues": issues,
        "complete": complete,
        "analysis_allowed": complete,
    }


if __name__ == "__main__":
    main()
