"""L13 pre-2021 candidate frame, eligibility screen, and ordered site draw.

The site-selection path receives only boolean prior/recent loss masks from
``risk.hansen.read_frame_hansen``.  It cannot inspect the 2021--2024 outcome.
Candidate and order files are serialized and hashed before the download command
will accept them.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
from pyproj import Geod
from shapely.geometry import Point
from shapely.ops import unary_union

from .config import (
    DRY_BIOME_NAME,
    FRAME_CUMULATIVE_LOSS_MIN,
    FRAME_DIR,
    FRAME_ELIGIBLE_FOREST_MIN,
    FRAME_GROUP_ORDER,
    FRAME_MIN_SEPARATION_KM,
    FRAME_RECENT_LOSS_MIN,
    FRAME_SITES_PER_GROUP,
    FRAME_VALID_LAND_MIN,
    LATTICE_BOX_SIZE,
    LATTICE_ORIGIN,
    LATTICE_STEP,
    LEGACY_SITES,
    EXPECTED_LEGACY_WINDOWS,
    MAX_FRAME_LATITUDE,
    MOIST_BIOME_NAME,
    SEED,
)
from .hansen import FrameHansenWindow, pixel_center_mask, read_frame_hansen
from .provenance import base_provenance, sha256_file, write_json
from .seasons import chirps_point_climatology, driest_four_month_window, feature_period

GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    group: str
    lon: float
    lat: float
    west: float
    south: float
    east: float
    north: float
    valid_land_share: float | None = None
    eligible_forest_share: float | None = None
    cumulative_loss_share: float | None = None
    recent_loss_share: float | None = None

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north


def lattice_centres() -> Iterable[tuple[float, float]]:
    lon0, lat0 = LATTICE_ORIGIN
    lon_step, lat_step = LATTICE_STEP
    n_lon = int(round(360.0 / lon_step)) + 1
    n_lat = int(np.floor((2 * MAX_FRAME_LATITUDE) / lat_step)) + 1
    for row in range(n_lat):
        lat = lat0 - row * lat_step
        if lat < -MAX_FRAME_LATITUDE - 1e-12:
            break
        for col in range(n_lon):
            lon = lon0 + col * lon_step
            if lon > 180.0 + 1e-12:
                break
            yield round(lon, 10), round(lat, 10)


def _candidate(group: str, lon: float, lat: float) -> Candidate:
    width, height = LATTICE_BOX_SIZE
    group_code = FRAME_GROUP_ORDER.index(group)
    identifier = f"F{group_code + 1}_{lat:+08.3f}_{lon:+09.3f}".replace("+", "P").replace("-", "M")
    return Candidate(
        candidate_id=identifier, group=group, lon=lon, lat=lat,
        west=lon - width / 2, south=lat - height / 2,
        east=lon + width / 2, north=lat + height / 2,
    )


def build_group_geometries(ecoregions_path: str | Path, amazon_basins_path: str | Path,
                           peatland_path: str | Path,
                           amazon_hybas_ids: Sequence[str | int]) -> dict[str, object]:
    """Construct exactly the four L13.2 polygon intersections.

    Amazon feature IDs are mandatory so the result artifact records which
    level-3 HydroBASINS features constitute the basin rather than guessing from
    a bounding box.
    """
    import geopandas as gpd

    if not amazon_hybas_ids:
        raise ValueError("Exact HydroBASINS level-3 Amazon HYBAS_ID values are required.")
    eco = gpd.read_file(ecoregions_path).to_crs("EPSG:4326")
    basins = gpd.read_file(amazon_basins_path).to_crs("EPSG:4326")
    peat = gpd.read_file(peatland_path).to_crs("EPSG:4326")
    required = {"BIOME_NAME", "REALM", "ECO_NAME"}
    if not required.issubset(eco.columns):
        raise ValueError(f"Ecoregions layer lacks {sorted(required - set(eco.columns))}")
    id_column = next((name for name in basins.columns if name.upper() == "HYBAS_ID"), None)
    if id_column is None:
        raise ValueError("HydroBASINS layer has no HYBAS_ID field.")
    wanted_ids = {str(value) for value in amazon_hybas_ids}
    selected_basins = basins[basins[id_column].astype(str).isin(wanted_ids)]
    found = set(selected_basins[id_column].astype(str))
    if found != wanted_ids:
        raise ValueError(f"Missing Amazon HydroBASINS IDs: {sorted(wanted_ids - found)}")

    moist = eco[eco["BIOME_NAME"] == MOIST_BIOME_NAME]
    amazon_eco = unary_union(moist[moist["REALM"] == "Neotropic"].geometry)
    congo = unary_union(moist[moist["REALM"] == "Afrotropic"].geometry)
    indomalayan = unary_union(moist[moist["REALM"] == "Indomalayan"].geometry)
    dry = eco[(eco["BIOME_NAME"] == DRY_BIOME_NAME) & (eco["REALM"] == "Neotropic")]
    # RESOLVE contains Dry Chaco and Humid Chaco rather than one feature named
    # literally "Gran Chaco"; include every Chaco ecoregion as the explicit add-on.
    chaco = eco[eco["ECO_NAME"].str.contains("Chaco", case=False, na=False)]
    return {
        "amazon_moist": amazon_eco.intersection(unary_union(selected_basins.geometry)),
        "congo_moist": congo,
        "dry_forest": unary_union(list(dry.geometry) + list(chaco.geometry)),
        "sea_peat": indomalayan.intersection(unary_union(peat.geometry)),
    }


def candidate_universe(group_geometries: Mapping[str, object]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for lon, lat in lattice_centres():
        point = Point(lon, lat)
        for group in FRAME_GROUP_ORDER:
            if group_geometries[group].covers(point):
                candidates.append(_candidate(group, lon, lat))
    return candidates


def screen_candidate(candidate: Candidate,
                     reader: Callable[[tuple[float, float, float, float]], FrameHansenWindow]
                     = read_frame_hansen) -> Candidate | None:
    data = reader(candidate.bounds)
    inside = pixel_center_mask(data.transform, data.datamask.shape, candidate.bounds)
    denominator = int((inside & (data.datamask == 1)).sum())
    total = int(inside.sum())
    if total == 0:
        return None
    valid_share = denominator / total
    if denominator == 0:
        return None
    forest_universe = inside & (data.datamask == 1) & (data.treecover2000 >= 30)
    # L13.3 defines both activity shares over valid land, not over U or the
    # remaining-forest subset.
    prior = inside & (data.datamask == 1) & data.prior_loss_2001_2020
    recent = inside & (data.datamask == 1) & data.recent_loss_2016_2020
    eligible = forest_universe & ~data.prior_loss_2001_2020
    forest_share = float(eligible.sum()) / denominator
    cumulative_share = float(prior.sum()) / denominator
    recent_share = float(recent.sum()) / denominator
    if not (
        valid_share >= FRAME_VALID_LAND_MIN
        and forest_share >= FRAME_ELIGIBLE_FOREST_MIN
        and cumulative_share >= FRAME_CUMULATIVE_LOSS_MIN
        and recent_share >= FRAME_RECENT_LOSS_MIN
    ):
        return None
    return Candidate(
        **{**asdict(candidate), "valid_land_share": valid_share,
           "eligible_forest_share": forest_share,
           "cumulative_loss_share": cumulative_share,
           "recent_loss_share": recent_share}
    )


def screen_universe(candidates: Iterable[Candidate],
                    reader: Callable[[tuple[float, float, float, float]], FrameHansenWindow]
                    = read_frame_hansen) -> list[Candidate]:
    eligible = []
    for index, candidate in enumerate(candidates, 1):
        screened = screen_candidate(candidate, reader)
        if screened is not None:
            eligible.append(screened)
        if index % 100 == 0:
            print(f"screened {index:,} candidates; eligible {len(eligible):,}", flush=True)
    return eligible


def distance_km(first: Candidate, second: Candidate) -> float:
    _, _, metres = GEOD.inv(first.lon, first.lat, second.lon, second.lat)
    return float(metres / 1000.0)


def ordered_permutations(candidates: Sequence[Candidate]) -> dict[str, list[Candidate]]:
    rng = np.random.default_rng(SEED)
    result: dict[str, list[Candidate]] = {}
    for group in FRAME_GROUP_ORDER:
        group_candidates = [item for item in candidates if item.group == group]
        order = rng.permutation(len(group_candidates))
        result[group] = [group_candidates[int(i)] for i in order]
    return result


def select_round_robin(ordered: Mapping[str, Sequence[Candidate]]) -> tuple[list[Candidate], dict[str, set[int]]]:
    """Three locked rounds, with cross-stratum 50-km sequential inhibition."""
    retained: list[Candidate] = []
    cursors = {group: 0 for group in FRAME_GROUP_ORDER}
    consumed = {group: set() for group in FRAME_GROUP_ORDER}
    for _round in range(FRAME_SITES_PER_GROUP):
        for group in FRAME_GROUP_ORDER:
            choices = ordered[group]
            while cursors[group] < len(choices):
                index = cursors[group]
                cursors[group] += 1
                consumed[group].add(index)
                candidate = choices[index]
                if all(distance_km(candidate, previous) >= FRAME_MIN_SEPARATION_KM
                       for previous in retained):
                    retained.append(candidate)
                    break
            else:
                raise RuntimeError(f"No separated site remains in {group} during round {_round + 1}.")
    return retained, consumed


def replacement_from_queue(group: str, ordered: Mapping[str, Sequence[Candidate]],
                           consumed: Mapping[str, set[int]], retained: Sequence[Candidate]
                           ) -> tuple[Candidate, int]:
    for index, candidate in enumerate(ordered[group]):
        if index in consumed[group]:
            continue
        if all(distance_km(candidate, previous) >= FRAME_MIN_SEPARATION_KM
               for previous in retained):
            return candidate, index
    raise RuntimeError(f"Replacement queue exhausted for {group}.")


def _write_candidates(path: Path, candidates: Sequence[Candidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(candidates[0]).keys()) if candidates else list(Candidate.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in sorted(candidates, key=lambda value: (value.group, value.lat, value.lon)):
            writer.writerow(asdict(item))


def _write_order(path: Path, ordered: Mapping[str, Sequence[Candidate]],
                 selected: Sequence[Candidate], consumed: Mapping[str, set[int]]) -> None:
    selected_ids = {item.candidate_id for item in selected}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = ("group", "rank", "candidate_id", "lon", "lat", "selected", "consumed_at_draw")
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for group in FRAME_GROUP_ORDER:
            for index, item in enumerate(ordered[group]):
                writer.writerow({
                    "group": group, "rank": index + 1, "candidate_id": item.candidate_id,
                    "lon": item.lon, "lat": item.lat,
                    "selected": int(item.candidate_id in selected_ids),
                    "consumed_at_draw": int(index in consumed[group]),
                })


def write_and_hash_frame(candidates: Sequence[Candidate], output_dir: str | Path = FRAME_DIR,
                         layer_manifest: Mapping[str, object] | None = None) -> dict[str, object]:
    output_dir = Path(output_dir)
    candidate_path = output_dir / "candidate_frame.csv"
    order_path = output_dir / "ordered_draw.csv"
    selected_path = output_dir / "selected_sites.json"
    _write_candidates(candidate_path, candidates)
    ordered = ordered_permutations(candidates)
    selected, consumed = select_round_robin(ordered)
    _write_order(order_path, ordered, selected, consumed)
    payload = {
        **base_provenance(),
        "candidate_frame": {"path": str(candidate_path), "sha256": sha256_file(candidate_path)},
        "ordered_draw": {"path": str(order_path), "sha256": sha256_file(order_path)},
        "candidate_counts": {group: sum(item.group == group for item in candidates)
                             for group in FRAME_GROUP_ORDER},
        "selected": [asdict(item) for item in selected],
        "external_layers": dict(layer_manifest or {}),
        "seed": SEED, "minimum_separation_km": FRAME_MIN_SEPARATION_KM,
    }
    write_json(selected_path, payload)
    payload["selected_sites_path"] = str(selected_path)
    return payload


def finalize_analysis_sites(frame_payload: Mapping[str, object], chirps_netcdf: str | Path,
                            output: str | Path = FRAME_DIR / "analysis_sites.json",
                            reader: Callable[[tuple[float, float, float, float]], FrameHansenWindow]
                            = read_frame_hansen) -> dict[str, object]:
    """Screen legacy boxes, enforce clean-cohort priority, and freeze L1 windows."""
    for key in ("candidate_frame", "ordered_draw"):
        record = frame_payload[key]
        if sha256_file(record["path"]) != record["sha256"]:
            raise RuntimeError(f"{key} changed after the pre-download hash was recorded.")
    selected = [Candidate(**item) for item in frame_payload["selected"]]
    legacy_survivors: list[Candidate] = []
    legacy_failures: list[str] = []
    for name, definition in LEGACY_SITES.items():
        bbox = definition["bbox"]
        lon = (bbox["west"] + bbox["east"]) / 2
        lat = (bbox["south"] + bbox["north"]) / 2
        candidate = Candidate(
            candidate_id=name, group=definition["group"], lon=lon, lat=lat,
            west=bbox["west"], south=bbox["south"], east=bbox["east"], north=bbox["north"],
        )
        screened = screen_candidate(candidate, reader)
        if screened is None:
            legacy_failures.append(name)
        elif any(distance_km(screened, clean) < FRAME_MIN_SEPARATION_KM for clean in selected):
            # L13.4 gives the clean random frame box priority.
            legacy_failures.append(f"{name}:within_50km_of_frame")
        else:
            legacy_survivors.append(screened)

    sites = []
    legacy_window_checks = {}
    for cohort, items in (("frame", selected), ("legacy", legacy_survivors)):
        for item in items:
            monthly = chirps_point_climatology(chirps_netcdf, item.lon, item.lat)
            start_month = driest_four_month_window(monthly)
            sites.append({
                **asdict(item), "cohort": cohort, "window_start_month": start_month,
                "periods": {str(year): feature_period(year, start_month)
                            for year in (2016, 2017, 2018, 2019, 2020)},
            })
            if cohort == "legacy":
                expected = EXPECTED_LEGACY_WINDOWS[item.candidate_id]
                algorithm_end = ((start_month - 1 + 3) % 12) + 1
                legacy_window_checks[item.candidate_id] = {
                    "expected_start_month": expected[0], "expected_end_month": expected[1],
                    "algorithm_start_month": start_month, "algorithm_end_month": algorithm_end,
                    "matches_expected_table": (start_month, algorithm_end) == expected,
                    "rule_on_disagreement": "algorithm_wins",
                }
    payload = {
        **base_provenance(),
        "candidate_frame": frame_payload["candidate_frame"],
        "ordered_draw": frame_payload["ordered_draw"],
        "external_layers": frame_payload.get("external_layers", {}),
        "chirps": {"path": str(chirps_netcdf), "sha256": sha256_file(chirps_netcdf),
                   "version": "CHIRPS v2.0 monthly", "climatology": "1991-2020"},
        "sites": sites, "legacy_failures": legacy_failures,
        "legacy_window_expected_value_checks": legacy_window_checks,
    }
    write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, screen, draw, and hash the L13 site frame.")
    parser.add_argument("--ecoregions", type=Path, required=True)
    parser.add_argument("--hydrobasins", type=Path, required=True)
    parser.add_argument("--peatland", type=Path, required=True)
    parser.add_argument("--ecoregions-source", type=Path,
                        help="Original downloaded archive to hash (defaults to --ecoregions)")
    parser.add_argument("--hydrobasins-source", type=Path,
                        help="Original downloaded archive to hash (defaults to --hydrobasins)")
    parser.add_argument("--peatland-source", type=Path,
                        help="Original downloaded artifact to hash (defaults to --peatland)")
    parser.add_argument("--amazon-hybas-id", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, default=FRAME_DIR)
    args = parser.parse_args()
    geometries = build_group_geometries(
        args.ecoregions, args.hydrobasins, args.peatland, args.amazon_hybas_id
    )
    candidates = candidate_universe(geometries)
    print(f"Polygon-filtered lattice candidates: {len(candidates):,}")
    eligible = screen_universe(candidates)
    manifest = {
        "ecoregions": {"path": str(args.ecoregions_source or args.ecoregions),
                       "sha256": sha256_file(args.ecoregions_source or args.ecoregions),
                       "version": "RESOLVE Ecoregions 2017"},
        "hydrobasins": {"path": str(args.hydrobasins_source or args.hydrobasins),
                        "sha256": sha256_file(args.hydrobasins_source or args.hydrobasins),
                        "version": "HydroBASINS v1.0 level 3",
                        "amazon_hybas_ids": args.amazon_hybas_id},
        "peatland": {"path": str(args.peatland_source or args.peatland),
                     "sha256": sha256_file(args.peatland_source or args.peatland),
                     "version": "Miettinen, Shi & Liew (2016), 2015 extent"},
    }
    result = write_and_hash_frame(eligible, args.output_dir, manifest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
