"""Pinned L13 layer acquisition and hash manifest.

Every layer that decides which boxes are eligible is pinned by version AND by
SHA-256, so a silent upstream change cannot quietly move the sampling frame.
Hash mismatch is a hard failure, never a warning.

The peat layer was originally pinned to Miettinen--Shi--Liew (2016), which turned
out to have no retrievable data artifact; the build correctly refused to swap in a
lookalike. PLAN.md L13.2 was amended (with sign-off) to pin PEATMAP instead --
Xu, Morris, Liu & Holden (2018), Catena -- which is pre-2021, citable, and has a
stable archive URL.
"""

from __future__ import annotations

import argparse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import EXTERNAL_DIR, RESULTS_DIR
from .provenance import base_provenance, sha256_file, write_json


@dataclass(frozen=True)
class Layer:
    name: str
    version: str
    filename: str
    source_url: str
    # Expected SHA-256. None = not yet pinned (recorded on first fetch, then frozen here).
    sha256: str | None = None


DOWNLOADS = (
    Layer("ecoregions", "RESOLVE Ecoregions 2017", "Ecoregions2017.zip",
          "https://storage.googleapis.com/teow2016/Ecoregions2017.zip",
          "be36d6209e443038d02e309f0447c6e7f2a62f5fe60c605ffe90d064952f2a60"),
    Layer("amazon_basin", "HydroBASINS v1.0 level 3 South America",
          "hybas_sa_lev03_v1c.zip",
          "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_sa_lev03_v1c.zip",
          "9eedb5240e9c2c77a55586c8b7b736ff34e067798e4a6d0bc1211549af2fe2aa"),
    Layer("sea_peatland", "PEATMAP (Xu, Morris, Liu & Holden 2018, Catena) -- Asia peat extent",
          "PEATMAP_Asia.zip",
          "https://archive.researchdata.leeds.ac.uk/251/5/Asia.zip",
          "8767e9ba8250770420cc555250f80b79b67410d00ae13ac629f4fe2ae9b8724e"),
    Layer("chirps", "CHIRPS v2.0 global monthly (subset in code to 1991-2020)",
          "chirps-v2.0.monthly.source.nc",
          "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/netcdf/chirps-v2.0.monthly.nc"),
)

# Shapefile inside PEATMAP_Asia.zip. Named explicitly so a repackaged archive fails
# loudly instead of silently selecting a different layer.
#
# MUST be SEA_Peatland (South-East Asia, lat -9.4..33.8), NOT EA_Peatland. Asia.zip holds
# five regional shapefiles and EA_Peatland is EAST Asia (lat 18.3..55.9 -- China, Mongolia,
# Siberia) with ZERO features in the Sumatra/Borneo peat belt. Picking it would have left
# the `sea_peat` stratum empty and the frame draw would have silently returned no peat
# sites rather than failing.
PEATMAP_SHAPEFILE = "Asia/SEA_Peatland.shp"


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    urllib.request.urlretrieve(url, destination)


def _verify(layer: Layer, path: Path) -> str:
    """Hash the fetched file and hard-fail on a mismatch against the pinned digest.

    A silently changed upstream layer would silently move the sampling frame, which is
    exactly the class of drift the pinning exists to prevent -- so this raises rather
    than warns.
    """
    digest = sha256_file(path)
    if layer.sha256 is not None and digest != layer.sha256:
        raise ValueError(
            f"{layer.name}: SHA-256 mismatch. Pinned {layer.sha256}, got {digest}. "
            f"The upstream artifact changed; the frame must not be drawn from it."
        )
    return digest


def acquire(destination: str | Path = EXTERNAL_DIR, peatland: str | Path | None = None,
            include_chirps: bool = False) -> dict[str, object]:
    destination = Path(destination)
    records = {}
    for layer in DOWNLOADS:
        # An explicitly supplied peat file overrides the pinned download (escape hatch
        # for an offline/mirrored copy); it is still hashed and recorded.
        if layer.name == "sea_peatland" and peatland is not None:
            path = Path(peatland)
            records[layer.name] = {
                "status": "provided", "path": str(path), "version": layer.version,
                "sha256": sha256_file(path), "shapefile": PEATMAP_SHAPEFILE,
            }
            continue
        if layer.name == "chirps" and not include_chirps:
            records[layer.name] = {
                "status": "not_downloaded", "reason": "requires --include-chirps (7.70 GB)",
                "version": layer.version, "source_url": layer.source_url,
            }
            continue
        path = destination / layer.filename
        download_file(layer.source_url, path)
        if layer.name == "chirps":
            import xarray as xr

            pinned_path = destination / "chirps-v2.0.monthly.1991-2020.nc"
            if not pinned_path.exists():
                with xr.open_dataset(path) as source:
                    pinned = source.sel(time=slice("1991-01-01", "2020-12-31"))
                    if pinned.sizes.get("time") != 360:
                        raise ValueError(
                            f"Expected 360 CHIRPS months for 1991-2020, got {pinned.sizes.get('time')}"
                        )
                    pinned.to_netcdf(pinned_path)
            records[layer.name] = {
                "status": "downloaded", "path": str(pinned_path), "version": layer.version,
                "source_url": layer.source_url, "sha256": sha256_file(pinned_path),
                "source_download_sha256": sha256_file(path),
            }
            continue
        records[layer.name] = {
            "status": "downloaded", "path": str(path), "version": layer.version,
            "source_url": layer.source_url, "sha256": _verify(layer, path),
        }
        if layer.name == "sea_peatland":
            records[layer.name]["shapefile"] = PEATMAP_SHAPEFILE
    return {**base_provenance(), "layers": records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire/hash the exact L13 external layers.")
    parser.add_argument("--destination", type=Path, default=EXTERNAL_DIR)
    parser.add_argument("--peatland", type=Path)
    parser.add_argument("--include-chirps", action="store_true")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "external_layers.json")
    args = parser.parse_args()
    result = acquire(args.destination, args.peatland, args.include_chirps)
    write_json(args.output, result)
    missing = [name for name, value in result["layers"].items()
               if value["status"] in {"missing", "not_downloaded"}]
    print(f"Layer manifest -> {args.output}; incomplete: {missing}")


if __name__ == "__main__":
    main()
