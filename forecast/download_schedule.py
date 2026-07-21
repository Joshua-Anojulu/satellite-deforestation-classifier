"""Immutable, forecast-specific download schedule for Specification W."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from .prelift_sandbox import require_pre_lift_role
from .specification_w import (
    ARCHIVE_YEARS,
    DOWNLOAD_SITE_YEARS,
    FRAME_GROUP_ORDER,
    K,
    SITES,
    TIFFS_PER_SITE_YEAR,
    sha256_file,
)

COMPOSITE_KINDS = ("reflectance", "dispersion", "clearobs", "solar_zenith")


def _pair_key(site_id: str, year: int) -> str:
    return f"{site_id}/{year}"


def expected_verified_existing_pairs(
    manifest: Mapping[str, object],
) -> set[tuple[str, int]]:
    """The 36 incumbent site-years already held by 12-site v11."""

    return {
        (site["candidate_id"], year)
        for site in manifest["sites"]
        if site["amendment_role"] == "incumbent"
        for year in (2018, 2019, 2020)
    }


def _validate_existing_inventory(
    manifest: Mapping[str, object],
    inventory: Mapping[str, Mapping[str, str]],
) -> None:
    expected = {
        _pair_key(site_id, year)
        for site_id, year in expected_verified_existing_pairs(manifest)
    }
    if set(inventory) != expected:
        raise ValueError("verified existing inventory must contain exactly 12 x 3 site-years")
    for pair, artifacts in inventory.items():
        if set(artifacts) != set(COMPOSITE_KINDS):
            raise ValueError(f"existing inventory schema mismatch for {pair}")
        if any(len(str(digest)) != 64 for digest in artifacts.values()):
            raise ValueError(f"existing inventory checksum mismatch for {pair}")


def build_download_schedule(
    manifest_path: str | Path,
    verified_existing_inventory: Mapping[str, Mapping[str, str]],
    output_path: str | Path,
) -> dict[str, object]:
    """Subtract the checksum-verified incumbent archive and freeze 144 pairs."""

    manifest_path = Path(manifest_path).resolve()
    output_path = Path(output_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("specification") != "Specification W" or manifest.get("K") != K:
        raise ValueError("schedule requires the frozen Specification W manifest")
    sites = manifest["sites"]
    if len(sites) != SITES:
        raise ValueError("Specification W manifest site count changed")
    _validate_existing_inventory(manifest, verified_existing_inventory)
    existing_pairs = expected_verified_existing_pairs(manifest)
    by_position_group = {
        (int(site["retained_position"]), site["group"]): site for site in sites
    }
    if len(by_position_group) != SITES:
        raise ValueError("manifest retained-position/group keys are not unique")

    entries = []
    for position in range(1, K + 1):
        for year in ARCHIVE_YEARS:
            for group in FRAME_GROUP_ORDER:
                site = by_position_group[(position, group)]
                pair = (site["candidate_id"], year)
                if pair in existing_pairs:
                    continue
                period = site["periods"].get(str(year))
                if not isinstance(period, list) or len(period) != 2:
                    raise ValueError(f"missing frozen period for {pair}")
                entries.append({
                    "site_id": site["candidate_id"],
                    "group": group,
                    "retained_position": position,
                    "amendment_role": site["amendment_role"],
                    "year": year,
                    "period": period,
                })
    if len(entries) != DOWNLOAD_SITE_YEARS or len({
        (entry["site_id"], entry["year"]) for entry in entries
    }) != DOWNLOAD_SITE_YEARS:
        raise AssertionError("forecast download schedule is not the frozen 144 pairs")
    document = {
        "schema_version": 1,
        "specification": "Specification W",
        "status": "AMENDED / EXPLORATORY",
        "immutable": True,
        "manifest": {"path": str(manifest_path), "sha256": sha256_file(manifest_path)},
        "K": K,
        "archive_years": list(ARCHIVE_YEARS),
        "rolling_model_history_years": 3,
        "verified_existing_site_years": len(existing_pairs),
        "verified_existing_tiffs": len(existing_pairs) * TIFFS_PER_SITE_YEAR,
        "scheduled_site_years": len(entries),
        "scheduled_tiffs": len(entries) * TIFFS_PER_SITE_YEAR,
        "verified_existing_inventory": {
            pair: dict(sorted(artifacts.items()))
            for pair, artifacts in sorted(verified_existing_inventory.items())
        },
        "entries": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    digest = sha256_file(output_path)
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{digest}  {output_path.name}\n", encoding="ascii"
    )
    return document


def validate_download_schedule(
    manifest: Mapping[str, object], schedule: Mapping[str, object]
) -> None:
    """Fail closed unless the schedule is exactly the frozen missing-pair set."""

    if (
        schedule.get("specification") != "Specification W"
        or schedule.get("immutable") is not True
        or schedule.get("K") != K
        or schedule.get("scheduled_site_years") != DOWNLOAD_SITE_YEARS
        or schedule.get("scheduled_tiffs") != DOWNLOAD_SITE_YEARS * TIFFS_PER_SITE_YEAR
    ):
        raise ValueError("forecast schedule header mismatch")
    _validate_existing_inventory(manifest, schedule["verified_existing_inventory"])
    sites = {site["candidate_id"]: site for site in manifest["sites"]}
    all_pairs = {(site_id, year) for site_id in sites for year in ARCHIVE_YEARS}
    expected = all_pairs - expected_verified_existing_pairs(manifest)
    observed = set()
    for entry in schedule["entries"]:
        site_id, year = entry["site_id"], int(entry["year"])
        if site_id not in sites:
            raise ValueError(f"unknown scheduled site: {site_id}")
        site = sites[site_id]
        if (
            entry["group"] != site["group"]
            or int(entry["retained_position"]) != int(site["retained_position"])
            or entry["amendment_role"] != site["amendment_role"]
            or list(entry["period"]) != list(site["periods"][str(year)])
        ):
            raise ValueError(f"scheduled provenance mismatch: {site_id}/{year}")
        if year not in ARCHIVE_YEARS or int(str(entry["period"][1])[:4]) > 2022:
            raise AssertionError("schedule crossed the frozen 2022 archive boundary")
        pair = (site_id, year)
        if pair in observed:
            raise ValueError(f"duplicate scheduled pair: {site_id}/{year}")
        observed.add(pair)
    if observed != expected:
        raise ValueError("schedule is not the exact manifest-derived missing-pair set")


def main() -> None:
    require_pre_lift_role("freezing")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("verified_existing_inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.verified_existing_inventory.read_text(encoding="utf-8"))
    build_download_schedule(args.manifest, inventory, args.output)


if __name__ == "__main__":
    main()

