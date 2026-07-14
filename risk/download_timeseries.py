"""Build and execute the locked SCL-masked 2016--2020 openEO graphs.

Tile cloud cover is only a permissive metadata prefilter.  The real mask is the
union of the eight locked SCL classes, dilated once with a 5x5 square at native
20 m SCL resolution before temporal reduction.  SWIR is bilinearly resampled;
the categorical mask is nearest-neighbour resampled.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import requests

from .config import (
    BUFFER_M,
    FEATURE_YEARS,
    FRAME_GROUP_ORDER,
    FRAME_REQUIRED,
    MAX_CLOUD_COVER,
    RAW_DIR,
    REFLECTANCE_BANDS,
    SCL_DILATION_KERNEL,
    SCL_MASKED_CLASSES,
    SWIR_BANDS,
    VISIBLE_NIR_BANDS,
    assert_feature_years,
)
from .provenance import backend_provenance, base_provenance, sha256_file, write_json

BACKEND_URL = "https://openeo.dataspace.copernicus.eu"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def buffered_bbox(bbox: Mapping[str, float], metres: float = BUFFER_M) -> dict[str, float]:
    """Extend all four sides geodesically by exactly 4 km."""
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    lon_mid = (bbox["west"] + bbox["east"]) / 2
    lat_mid = (bbox["south"] + bbox["north"]) / 2
    west, _, _ = geod.fwd(bbox["west"], lat_mid, 270, metres)
    east, _, _ = geod.fwd(bbox["east"], lat_mid, 90, metres)
    _, south, _ = geod.fwd(lon_mid, bbox["south"], 180, metres)
    _, north, _ = geod.fwd(lon_mid, bbox["north"], 0, metres)
    return {"west": west, "south": south, "east": east, "north": north}


def _invalid_scl(process_value: Any) -> Any:
    invalid = process_value == SCL_MASKED_CLASSES[0]
    for class_id in SCL_MASKED_CLASSES[1:]:
        invalid = invalid.or_(process_value == class_id)
    return invalid


def build_cubes(connection: Any, bbox: Mapping[str, float], period: tuple[str, str]
                ) -> dict[str, Any]:
    """Return composite/count/dispersion/solar cubes sharing one locked source graph."""
    load = dict(
        collection_id="SENTINEL2_L2A", spatial_extent=dict(bbox),
        temporal_extent=list(period), max_cloud_cover=MAX_CLOUD_COVER,
    )
    scl = connection.load_collection(bands=["SCL"], **load)
    invalid = scl.apply(_invalid_scl).reduce_dimension("bands", "max")
    dilated = invalid.apply_kernel(
        kernel=np.ones((SCL_DILATION_KERNEL, SCL_DILATION_KERNEL), dtype=int).tolist(),
        factor=1, border=0, replace_invalid=0,
    ).apply(lambda value: value > 0)

    visible_nir = connection.load_collection(bands=list(VISIBLE_NIR_BANDS), **load)
    swir = connection.load_collection(bands=list(SWIR_BANDS), **load)
    swir_10m = swir.resample_cube_spatial(visible_nir, method="bilinear")
    reflectance = visible_nir.merge_cubes(swir_10m)
    mask_10m = dilated.resample_cube_spatial(visible_nir, method="near")
    masked = reflectance.mask(mask_10m)

    clear = dilated.apply(lambda value: value.not_())
    # SIGN GUARD. The CDSE backend sums boolean True as -1, so a raw sum of the "clear"
    # mask returns NEGATIVE counts (measured: -16..-8 where the true counts are 8..16).
    # Unguarded, EVERY site would have failed the L2 clear-observation gate (>= 8), the
    # cohort would have dropped below the floor of 14, and the study would have been
    # declared unviable -- on a sign error. The magnitudes were plausible and correctly
    # ORDERED, so only "a count cannot be negative" caught it.
    # abs() is correct under BOTH encodings (True=+1 and True=-1), so this cannot silently
    # break if the backend changes.
    clear_count = clear.reduce_dimension("t", "sum").apply(lambda value: value.absolute())
    composite = masked.reduce_dimension("t", "median")
    dispersion = masked.reduce_dimension("t", "sd")

    solar = connection.load_collection(bands=["sunZenithAngles"], **load)
    solar_mask = dilated.resample_cube_spatial(solar, method="near")
    solar_median = solar.mask(solar_mask).reduce_dimension("t", "median")
    return {
        "reflectance": composite,
        "clearobs": clear_count,
        "dispersion": dispersion,
        "solar_zenith": solar_median,
    }


def process_graphs(cubes: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    return {name: cube.flat_graph() for name, cube in cubes.items()}


def verify_frame_hashes(manifest: Mapping[str, Any]) -> None:
    for key in ("candidate_frame", "ordered_draw"):
        record = manifest[key]
        actual = sha256_file(record["path"])
        if actual != record["sha256"]:
            raise RuntimeError(f"{key} hash mismatch: {actual} != {record['sha256']}")


def validate_pre_download_manifest(manifest: Mapping[str, Any]) -> None:
    verify_frame_hashes(manifest)
    frame_sites = [site for site in manifest["sites"] if site["cohort"] == "frame"]
    counts = Counter(site["group"] for site in frame_sites)
    if len(frame_sites) != FRAME_REQUIRED or any(counts[group] != 3 for group in FRAME_GROUP_ORDER):
        raise RuntimeError("Pre-download manifest does not contain the locked 3x4 frame cohort.")
    for site in manifest["sites"]:
        if set(site["periods"]) != {str(year) for year in FEATURE_YEARS}:
            raise RuntimeError(f"{site['candidate_id']} lacks one of the five feature periods.")
        for year, period in site["periods"].items():
            if int(year) > 2020 or int(period[1][:4]) > 2020:
                raise AssertionError(f"Post-2020 imagery reached download manifest: {site['candidate_id']} {period}")


def query_acquisition_metadata(bbox: Mapping[str, float], period: tuple[str, str]) -> dict[str, Any]:
    """Query actual qualifying product dates for the acquisition-geometry sensitivity."""
    west, south, east, north = (bbox[k] for k in ("west", "south", "east", "north"))
    polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    start, end = period
    cloud = (
        "Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and "
        f"att/OData.CSC.DoubleAttribute/Value le {MAX_CLOUD_COVER})"
    )
    filters = (
        "Collection/Name eq 'SENTINEL-2' and "
        "contains(Name,'MSIL2A') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon}') and "
        f"ContentDate/Start ge {start}T00:00:00.000Z and ContentDate/Start le {end}T23:59:59.999Z "
        f"and {cloud}"
    )
    response = requests.get(
        CATALOGUE_URL,
        params={"$filter": filters, "$select": "Id,Name,ContentDate", "$top": 1000},
        timeout=60,
    )
    response.raise_for_status()
    products = response.json().get("value", [])
    datetimes = sorted(datetime.fromisoformat(item["ContentDate"]["Start"].replace("Z", "+00:00"))
                       for item in products)
    if not datetimes:
        return {"product_count": 0, "median_acquisition_datetime": None, "median_doy": None}
    timestamps = np.array([value.timestamp() for value in datetimes], dtype=np.float64)
    median = datetime.fromtimestamp(float(np.median(timestamps)), tz=datetimes[0].tzinfo)
    return {
        "product_count": len(products),
        "median_acquisition_datetime": median.isoformat(),
        "median_doy": median.timetuple().tm_yday,
        "product_ids": [item["Id"] for item in products],
    }


def _download(cube: Any, destination: Path, retries: int = 4) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"skip (exists): {destination}")
        return
    for attempt in range(1, retries + 1):
        try:
            cube.download(destination, format="GTiff")
            return
        except Exception:
            if destination.exists() and destination.stat().st_size == 0:
                destination.unlink()
            if attempt == retries:
                raise
            time.sleep(15 * attempt)


def download_manifest(manifest_path: str | Path, only_site: str | None = None,
                      dry_run: bool = False) -> None:
    import openeo

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    validate_pre_download_manifest(manifest)
    connection = openeo.connect(BACKEND_URL)
    if not dry_run:
        connection.authenticate_oidc()
    years = assert_feature_years(FEATURE_YEARS)
    for site in manifest["sites"]:
        if only_site and site["candidate_id"] != only_site:
            continue
        bbox = buffered_bbox({key: site[key] for key in ("west", "south", "east", "north")})
        for year in years:
            period = tuple(site["periods"][str(year)])
            cubes = build_cubes(connection, bbox, period)
            graphs = process_graphs(cubes)
            directory = RAW_DIR / site["candidate_id"]
            provenance = {
                **base_provenance(), "backend": backend_provenance(connection),
                "site": site["candidate_id"], "cohort": site["cohort"], "year": year,
                "feature_year_assertion": "<=2020", "period": period, "buffered_bbox": bbox,
                "max_cloud_cover": MAX_CLOUD_COVER,
                "scl_masked_classes": list(SCL_MASKED_CLASSES),
                "scl_dilation": {"shape": "square", "native_resolution_m": 20,
                                  "kernel": [SCL_DILATION_KERNEL, SCL_DILATION_KERNEL]},
                "process_graphs": graphs,
            }
            if not dry_run:
                provenance["acquisition_metadata"] = query_acquisition_metadata(bbox, period)
            write_json(directory / f"{year}_provenance.json", provenance)
            if dry_run:
                print(f"validated graph: {site['candidate_id']} {year}")
                continue
            for name, cube in cubes.items():
                _download(cube, directory / f"{year}_{name}.tif")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the 100 locked risk-study composites.")
    parser.add_argument("manifest", type=Path, help="analysis_sites.json produced before download")
    parser.add_argument("--site", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Validate/write graphs without downloads")
    args = parser.parse_args()
    download_manifest(args.manifest, args.site, args.dry_run)


if __name__ == "__main__":
    main()
