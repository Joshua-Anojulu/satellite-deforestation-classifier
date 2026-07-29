"""Acquisition and pinning of the static drivers that must be downloaded.

Two sources need fetching; the rest (HydroBASINS, Ecoregions, CHIRPS) are
already pinned in ``results/external_layers.json`` and are re-checksummed rather
than re-downloaded.

* **roads** -- Geofabrik dated OSM extracts, one snapshot per origin.  The
  regions are *derived* from the site footprints by polygon intersection
  against Geofabrik's published index, choosing the most specific region that
  covers each box, so the download is as small as the source allows and a site
  that drifts across a border cannot be silently missed.
* **terrain** -- CGIAR-CSI SRTM v4.1, 5 degree tiles, one static vintage.

**Neither source offers a publisher checksum, and this was measured rather than
assumed.**  Geofabrik publishes no ``.md5`` sidecar for *dated* archives (only
for ``-latest``), and SRTM's ``ETag`` is not a plain md5 -- a preflight over all
28 tiles returned zero usable digests.  So every file here is pinned by URL,
``Content-Length`` and the sha256 computed on receipt: that detects a truncated
or corrupted transfer, and says nothing about the source.

This is **weaker than the GFC archive**, which at least carries the publisher's
own md5 and object generation.  ``RemoteFile.md5`` stays empty rather than being
fabricated, and the inventory records how many files actually had a publisher
digest, so the difference is visible instead of implied.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .gfc_archive import CONTAGION_HALO_PX, GFC_DEGREES_PER_PX
from .static_layers import ORIGINS

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
SRTM_BASE_URL = "https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF"
SRTM_TILE_DEGREES = 5
SRTM_VERSION = "SRTM v4.1 (CGIAR-CSI, 2008 release)"


@dataclass(frozen=True)
class RemoteFile:
    """One file to fetch, with whatever the publisher will tell us about it."""

    kind: str          # "roads" | "terrain"
    key: str           # region id + origin, or srtm tile id
    url: str
    origin: int | None
    content_length: int
    #: Publisher-computed md5 where the source offers one; empty when it does
    #: not.  Never fabricated, so a weaker anchor stays visibly weaker.
    md5: str = ""


# --- roads ------------------------------------------------------------------

def load_geofabrik_index(path_or_url: str | Path = GEOFABRIK_INDEX_URL, *, opener=None):
    """Load Geofabrik's region index (GeoJSON of 555 regions with pbf URLs)."""

    if isinstance(path_or_url, Path) or not str(path_or_url).startswith("http"):
        return json.loads(Path(path_or_url).read_text(encoding="utf-8"))
    opener = opener or urllib.request.urlopen
    with opener(str(path_or_url)) as response:
        return json.loads(response.read().decode("utf-8"))


def _site_box(site: Mapping[str, object], pad: float):
    from shapely.geometry import box

    return box(
        float(site["west"]) - pad, float(site["south"]) - pad,
        float(site["east"]) + pad, float(site["north"]) + pad,
    )


def required_osm_regions(
    sites: Sequence[Mapping[str, object]],
    index: Mapping[str, object],
    *,
    halo_px: int = CONTAGION_HALO_PX,
) -> tuple[str, ...]:
    """Derive the smallest set of Geofabrik regions covering every haloed box.

    For each site the **most specific** covering region is chosen -- a Brazilian
    state extract rather than all of Brazil -- which is both smaller and more
    precise.  A site is only satisfied by a region that fully contains it; if
    none does, every region that *intersects* it is taken, so a box straddling a
    border is covered rather than dropped.
    """

    from shapely.geometry import shape

    if not sites:
        raise ValueError("no sites supplied; refusing to derive an empty region set")
    pad = halo_px * GFC_DEGREES_PER_PX

    regions = []
    for feature in index["features"]:
        properties = feature["properties"]
        if "pbf" not in properties.get("urls", {}):
            continue
        geometry = shape(feature["geometry"])
        regions.append((properties["id"], properties["urls"]["pbf"], geometry, geometry.area))

    from shapely.ops import unary_union

    chosen: set[str] = set()
    for site in sites:
        box_geom = _site_box(site, pad)

        # Option A: the smallest single region that fully contains the box.
        containing = [r for r in regions if r[2].contains(box_geom)]
        single = min(containing, key=lambda r: r[3]) if containing else None

        # Option B: a union of small regions covering it.  A box straddling a
        # border is contained by no country but is covered by two -- and taking
        # both is far cheaper than the continent extract that would otherwise
        # be the smallest "containing" region.  Greedy by descending share of
        # the box covered, so the most relevant region is taken first.
        overlapping = [r for r in regions if r[2].intersects(box_geom)]
        if not overlapping:
            raise ValueError(f"no Geofabrik region covers site {site.get('candidate_id')!r}")
        overlapping.sort(key=lambda r: r[2].intersection(box_geom).area, reverse=True)
        cover: list = []
        for region in overlapping:
            if single is not None and region[0] == single[0]:
                continue  # judge the union on its own merits
            cover.append(region)
            if unary_union([r[2] for r in cover]).contains(box_geom):
                break
        else:
            cover = []  # no union covers it; fall back to the single region

        # Prefer whichever is cheaper to download, approximated by total area.
        if cover and (single is None or sum(r[3] for r in cover) < single[3]):
            chosen.update(r[0] for r in cover)
        elif single is not None:
            chosen.add(single[0])
        else:
            raise ValueError(f"no Geofabrik region covers site {site.get('candidate_id')!r}")
    return tuple(sorted(chosen))


def resolve_available_regions(
    regions: Sequence[str],
    index: Mapping[str, object],
    origins: Sequence[int] = ORIGINS,
    *,
    exists,
) -> dict[str, str]:
    """Substitute a parent extract wherever a region lacks dated archives.

    Geofabrik began publishing some sub-regions late -- ``kalimantan`` and
    ``sumatra`` have no dated archive before 2022 -- so the most specific region
    is not always fetchable at every origin.

    The substitution is applied **uniformly across all origins**, not per origin.
    A region available in 2022 but not 2020 would otherwise mean the roads layer
    came from a different extract in test than in training, and differences in
    extract boundaries could show up as a feature that tracks the year.  Same
    reasoning as the frozen schema intersection: the source must not vary with
    the origin.

    Returns ``{region_id: pbf_url}`` for the resolved set.
    """

    properties = {
        feature["properties"]["id"]: feature["properties"]
        for feature in index["features"]
        if "pbf" in feature["properties"].get("urls", {})
    }
    resolved: dict[str, str] = {}
    for region in regions:
        candidate = region
        while candidate is not None:
            record = properties.get(candidate)
            if record is None:
                raise ValueError(f"region {candidate!r} is absent from the Geofabrik index")
            url = record["urls"]["pbf"]
            if all(exists(osm_snapshot_url(url, origin)) for origin in origins):
                resolved[candidate] = url
                break
            candidate = record.get("parent")
        else:
            raise ValueError(
                f"no ancestor of {region!r} has dated archives at every origin "
                f"{tuple(origins)}; refusing to vary the roads source by origin"
            )
    return resolved


def osm_snapshot_url(pbf_url: str, origin: int) -> str:
    """Rewrite a ``-latest.osm.pbf`` URL to the 1 January of T archive.

    1 January of T, not T+1: the issue date is 31 December T, and Geofabrik
    publishes no year-end snapshot (see static_layers.StaticLayer.snapshot_for).
    """

    suffix = "-latest.osm.pbf"
    if not pbf_url.endswith(suffix):
        raise ValueError(f"unexpected Geofabrik pbf url: {pbf_url}")
    return f"{pbf_url[:-len(suffix)]}-{origin % 100:02d}0101.osm.pbf"


# --- terrain ----------------------------------------------------------------

def srtm_tile_id(lat: float, lon: float) -> str:
    """Name the CGIAR SRTM v4.1 5-degree tile containing a point.

    Columns run west to east from -180, rows north to south from +60.
    """

    col = int(math.floor((lon + 180) / SRTM_TILE_DEGREES)) + 1
    row = int(math.floor((60 - lat) / SRTM_TILE_DEGREES)) + 1
    return f"srtm_{col:02d}_{row:02d}"


def srtm_tile_url(tile: str) -> str:
    return f"{SRTM_BASE_URL}/{tile}.zip"


def required_srtm_tiles(
    sites: Sequence[Mapping[str, object]],
    *,
    halo_px: int = CONTAGION_HALO_PX,
) -> tuple[str, ...]:
    """Derive the SRTM tiles covering every haloed site box, fail-closed."""

    if not sites:
        raise ValueError("no sites supplied; refusing to derive an empty tile set")
    pad = halo_px * GFC_DEGREES_PER_PX
    tiles: set[str] = set()
    for site in sites:
        for lat in (float(site["south"]) - pad, float(site["north"]) + pad):
            for lon in (float(site["west"]) - pad, float(site["east"]) + pad):
                tiles.add(srtm_tile_id(lat, lon))
    return tuple(sorted(tiles))


# --- shared fetch -----------------------------------------------------------

def _md5_from_etag(etag: str | None) -> str:
    """A plain 32-hex ETag is the object's md5; anything else is not."""

    if not etag:
        return ""
    cleaned = etag.strip().strip('"')
    if len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned.lower()):
        return cleaned.lower()
    return ""


def head_remote(kind: str, key: str, url: str, origin: int | None = None,
                *, opener=urllib.request.urlopen) -> RemoteFile:
    """Fetch what the publisher will state about a file, without downloading it."""

    request = urllib.request.Request(url, method="HEAD")
    with opener(request) as response:
        headers = response.headers
        length = int(headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError(f"publisher served no content length for {url}")
        md5 = _md5_from_etag(headers.get("ETag"))
    return RemoteFile(kind, key, url, origin, length, md5)


def download_remote(remote: RemoteFile, destination: Path,
                    *, opener=urllib.request.urlopen,
                    chunk_bytes: int = 4 * 1024 * 1024) -> str:
    """Download, verifying length and (where offered) the publisher's md5.

    Writes to a ``.partial`` sibling and renames only after every available
    check passes, so a truncated transfer never lands at the final path.
    """

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    received = 0

    # Resume a partial transfer rather than restarting it.  These files run to
    # ~1 GB and the process is routinely interrupted, so discarding a
    # part-downloaded file each time makes progress unreliable.  The existing
    # bytes are hashed first to seed the digests, so verification still covers
    # the whole file.
    resume_from = 0
    if partial.exists():
        existing = partial.stat().st_size
        if 0 < existing < remote.content_length:
            with partial.open("rb") as stream:
                for chunk in iter(lambda: stream.read(chunk_bytes), b""):
                    md5.update(chunk)
                    sha256.update(chunk)
            resume_from = existing
            received = existing
        else:
            # Empty, or somehow >= the expected length: start over.
            partial.unlink()

    request = urllib.request.Request(remote.url)
    if resume_from:
        request.add_header("Range", f"bytes={resume_from}-")

    try:
        with opener(request) as response:
            # A server that ignores Range replies 200 with the WHOLE file; the
            # seeded digests would then be wrong, so reset and take it fresh.
            if resume_from and getattr(response, "status", 200) != 206:
                md5 = hashlib.md5()
                sha256 = hashlib.sha256()
                received = 0
                resume_from = 0
            mode = "ab" if resume_from else "wb"
            with partial.open(mode) as sink:
                while True:
                    chunk = response.read(chunk_bytes)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha256.update(chunk)
                    received += len(chunk)
                    sink.write(chunk)
        if received != remote.content_length:
            raise ValueError(
                f"length mismatch for {remote.url}: "
                f"expected {remote.content_length}, received {received}"
            )
        if remote.md5 and md5.hexdigest() != remote.md5:
            raise ValueError(
                f"md5 mismatch for {remote.url}: "
                f"expected {remote.md5}, computed {md5.hexdigest()}"
            )
    except ValueError:
        # Verification failed, so the bytes on disk are wrong: discard them.
        # Distinct from a transport error below, where they are merely
        # incomplete and worth resuming.
        if partial.exists():
            partial.unlink()
        raise
    partial.replace(destination)
    return sha256.hexdigest()


def build_inventory(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Assemble the write-once static-archive inventory."""

    if not records:
        raise ValueError("refusing to build an empty static inventory")
    payload = {f"{r['kind']}/{r['key']}": dict(r) for r in records}
    if len(payload) != len(records):
        raise ValueError("duplicate (kind, key) in static inventory")
    publisher_checked = sum(1 for r in records if r.get("md5"))
    return {
        "schema_version": 1,
        "origins": list(ORIGINS),
        "srtm_version": SRTM_VERSION,
        "pinning_anchor": (
            "URL + content length + sha256 on receipt only. NEITHER source "
            "offers a publisher checksum: Geofabrik publishes no .md5 sidecar "
            "for dated archives, and SRTM's ETag is not a plain md5 (measured: "
            "0 of 28 tiles returned a usable digest). This detects a truncated "
            "or corrupted transfer and nothing about the source, so it is "
            "WEAKER than the GFC archive, which carries the publisher's own md5 "
            "and object generation. NOT an independent third-party manifest."
        ),
        "files_with_publisher_md5": publisher_checked,
        "file_count": len(records),
        "files": payload,
    }


def write_inventory_once(path: str | Path, inventory: Mapping[str, object]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as sink:
        sink.write(json.dumps(inventory, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path


def _url_exists(url: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")):
            return True
    except Exception:
        return False


def acquire(
    sites: Sequence[Mapping[str, object]],
    root: str | Path,
    *,
    index: Mapping[str, object] | None = None,
    origins: Sequence[int] = ORIGINS,
    log=print,
) -> list[dict[str, object]]:
    """Preflight every URL, then download what is missing or unverified.

    Unlike the GFC archive these are PREDICTORS, not the outcome layer, so they
    live outside the elevation-locked raw-GFC directory and need no privileged
    context.
    """

    root = Path(root)
    index = index if index is not None else load_geofabrik_index()

    regions = required_osm_regions(sites, index)
    log(f"derived {len(regions)} OSM regions from site footprints")
    resolved = resolve_available_regions(regions, index, origins, exists=_url_exists)
    substituted = set(regions) - set(resolved)
    if substituted:
        log(f"substituted {sorted(substituted)} -> {sorted(set(resolved) - set(regions))} "
            "(no dated archive at every origin)")

    tiles = required_srtm_tiles(sites)
    log(f"derived {len(tiles)} SRTM tiles")

    log("preflight: fetching publisher metadata for every file...")
    remotes: list[RemoteFile] = []
    for region, url in sorted(resolved.items()):
        for origin in origins:
            remotes.append(head_remote(
                "roads", f"{region}@{origin}", osm_snapshot_url(url, origin), origin
            ))
    for tile in tiles:
        remotes.append(head_remote("terrain", tile, srtm_tile_url(tile)))
    total = sum(r.content_length for r in remotes)
    with_md5 = sum(1 for r in remotes if r.md5)
    log(f"preflight ok: {len(remotes)} files, {total / 1e9:.2f} GB, "
        f"{with_md5} with a publisher md5")

    records: list[dict[str, object]] = []
    for index_of, remote in enumerate(remotes, 1):
        subdir = "osm" if remote.kind == "roads" else "srtm"
        suffix = ".osm.pbf" if remote.kind == "roads" else ".zip"
        name = remote.url.rsplit("/", 1)[-1] if remote.kind == "roads" else f"{remote.key}{suffix}"
        target = root / subdir / name
        if target.is_file() and target.stat().st_size == remote.content_length:
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
            log(f"[{index_of}/{len(remotes)}] have {name}")
        else:
            log(f"[{index_of}/{len(remotes)}] fetching {name} "
                f"({remote.content_length / 1e6:.0f} MB)")
            sha256 = download_remote(remote, target)
        record = asdict(remote)
        record["sha256"] = sha256
        record["path"] = str(target.relative_to(root)).replace("\\", "/")
        records.append(record)
    return records


def main() -> None:
    """CLI entry point.  Needs no elevation: these are predictors, not labels."""

    import argparse

    from risk.config import DATA_ROOT

    parser = argparse.ArgumentParser(description="Acquire and pin the static drivers.")
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).with_name("artifacts") / "specification_w_manifest.json")
    parser.add_argument("--root", type=Path, default=Path(DATA_ROOT) / "external" / "static")
    parser.add_argument("--inventory", type=Path,
                        default=Path(__file__).with_name("artifacts") / "static_archive_inventory.json")
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
    print(f"files={inventory['file_count']} "
          f"with_publisher_md5={inventory['files_with_publisher_md5']}")


if __name__ == "__main__":
    main()
