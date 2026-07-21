"""Decode-verify and checksum the 36 incumbent site-years for the Spec W freeze.

``forecast.download_schedule.build_download_schedule`` trusts the shape of the
``verified_existing_inventory`` it is handed; it does not re-open the files.  This
tool produces that inventory the honest way: it opens every incumbent composite,
asserts the expected band count, fully decodes each band (so a silently truncated
or corrupt tile raises rather than being hashed as-is), and only then records the
whole-file SHA-256.  Optical archive only (2018-2020 reflectance/dispersion/
clear-observation/solar-zenith); no Hansen loss/label raster is read.

The emitted JSON keys are ``"{site_id}/{year}"`` mapping to ``{kind: sha256}`` for
the four composite kinds, exactly the structure the schedule builder validates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

import rasterio

from risk.config import RAW_DIR, REFLECTANCE_BANDS

from .download_schedule import COMPOSITE_KINDS, expected_verified_existing_pairs
from .specification_w import sha256_file

_EXPECTED_BAND_COUNTS = {
    "reflectance": len(REFLECTANCE_BANDS),
    "dispersion": len(REFLECTANCE_BANDS),
    "clearobs": 1,
    "solar_zenith": 1,
}


def build_incumbent_inventory(
    manifest_path: str | Path,
    raw_dir: str | Path = RAW_DIR,
) -> dict[str, dict[str, str]]:
    """Decode-verify the 36 incumbent site-years and return their checksum map."""

    manifest: Mapping[str, object] = json.loads(
        Path(manifest_path).read_text(encoding="utf-8")
    )
    raw_dir = Path(raw_dir)
    inventory: dict[str, dict[str, str]] = {}
    for site_id, year in sorted(expected_verified_existing_pairs(manifest)):
        artifacts: dict[str, str] = {}
        for kind in COMPOSITE_KINDS:
            path = raw_dir / site_id / f"{year}_{kind}.tif"
            if not path.is_file():
                raise FileNotFoundError(f"incumbent composite missing: {path}")
            with rasterio.open(path) as source:
                expected = _EXPECTED_BAND_COUNTS[kind]
                if source.count != expected:
                    raise ValueError(
                        f"{path}: band count {source.count} != expected {expected}"
                    )
                for band in range(1, source.count + 1):
                    source.read(band)  # full decode; raises on truncation/corruption
            artifacts[kind] = sha256_file(path)
        inventory[f"{site_id}/{year}"] = dict(sorted(artifacts.items()))
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Specification W frozen manifest")
    parser.add_argument("output", type=Path, help="incumbent inventory JSON to write")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    inventory = build_incumbent_inventory(args.manifest, args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
