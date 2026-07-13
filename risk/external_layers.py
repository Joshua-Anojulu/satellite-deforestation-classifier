"""Pinned L13 layer acquisition and hash manifest.

No substitute is silently accepted for the 2016 Miettinen--Shi--Liew peatland
extent.  That source has no stable public data URL in the reviewed spec, so the
CLI requires an explicit local file and records its hash.
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


DOWNLOADS = (
    Layer("ecoregions", "RESOLVE Ecoregions 2017", "Ecoregions2017.zip",
          "https://storage.googleapis.com/teow2016/Ecoregions2017.zip"),
    Layer("amazon_basin", "HydroBASINS v1.0 level 3 South America",
          "hybas_sa_lev03_v1c.zip",
          "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_sa_lev03_v1c.zip"),
    Layer("chirps", "CHIRPS v2.0 global monthly (subset in code to 1991-2020)",
          "chirps-v2.0.monthly.source.nc",
          "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/netcdf/chirps-v2.0.monthly.nc"),
)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    urllib.request.urlretrieve(url, destination)


def acquire(destination: str | Path = EXTERNAL_DIR, peatland: str | Path | None = None,
            include_chirps: bool = False) -> dict[str, object]:
    destination = Path(destination)
    records = {}
    for layer in DOWNLOADS:
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
            "source_url": layer.source_url, "sha256": sha256_file(path),
        }
    if peatland is None:
        records["sea_peatland"] = {
            "status": "missing",
            "version": "Miettinen, Shi & Liew (2016), 2015 extent",
            "reason": "PLAN.md pins the publication but supplies no stable data-file URL; substitution forbidden.",
        }
    else:
        path = Path(peatland)
        records["sea_peatland"] = {
            "status": "provided", "path": str(path),
            "version": "Miettinen, Shi & Liew (2016), 2015 extent",
            "sha256": sha256_file(path),
        }
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
