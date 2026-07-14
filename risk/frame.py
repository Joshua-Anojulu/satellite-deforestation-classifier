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
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
from pyproj import Geod
from shapely.geometry import Point
from shapely.ops import unary_union

from .config import (
    DRY_BIOME_NAME,
    FEATURE_YEARS,
    FRAME_CUMULATIVE_LOSS_MIN,
    FRAME_DIR,
    FRAME_MIN_AT_RISK_CELLS,
    AT_RISK_LAND_FRACTION,
    CELL_SIZE_M,
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
    at_risk_cells: int | None = None

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


def _select_basins(path: str | Path, hybas_ids: Sequence[str | int], label: str):
    import geopandas as gpd

    if not hybas_ids:
        raise ValueError(f"Exact HydroBASINS level-3 {label} HYBAS_ID values are required.")
    basins = gpd.read_file(path).to_crs("EPSG:4326")
    id_column = next((name for name in basins.columns if name.upper() == "HYBAS_ID"), None)
    if id_column is None:
        raise ValueError(f"{label} HydroBASINS layer has no HYBAS_ID field.")
    wanted = {str(value) for value in hybas_ids}
    selected = basins[basins[id_column].astype(str).isin(wanted)]
    missing = wanted - set(selected[id_column].astype(str))
    if missing:
        raise ValueError(f"Missing {label} HydroBASINS IDs: {sorted(missing)}")
    return selected


def build_group_geometries(ecoregions_path: str | Path, amazon_basins_path: str | Path,
                           peatland_path: str | Path,
                           amazon_hybas_ids: Sequence[str | int],
                           congo_basins_path: str | Path | None = None,
                           congo_hybas_ids: Sequence[str | int] | None = None) -> dict[str, object]:
    """Construct exactly the four L13.2 polygon intersections.

    Basin IDs are mandatory so the result artifact records which level-3 HydroBASINS
    features constitute each basin rather than guessing from a bounding box.

    CONGO IS BASIN-RESTRICTED, SYMMETRICALLY WITH AMAZON. The original spec restricted the
    Amazon group by basin polygon but defined the Congo group as merely "Afrotropic moist
    broadleaf" -- which spans West Africa, East Africa, Madagascar and the Seychelles. The
    first draw duly returned Ghana (6.25E) and Guinea (-12.25E) boxes in a stratum the paper
    would call "Congo Basin". That asymmetry was a spec bug, not a draw bug.
    """
    import geopandas as gpd

    eco = gpd.read_file(ecoregions_path).to_crs("EPSG:4326")
    selected_basins = _select_basins(amazon_basins_path, amazon_hybas_ids, "Amazon")
    peat = gpd.read_file(peatland_path).to_crs("EPSG:4326")
    if congo_basins_path is None or not congo_hybas_ids:
        raise ValueError("Congo basin path and HYBAS_ID(s) are required (L13.2).")
    congo_basins = _select_basins(congo_basins_path, congo_hybas_ids, "Congo")
    required = {"BIOME_NAME", "REALM", "ECO_NAME"}
    if not required.issubset(eco.columns):
        raise ValueError(f"Ecoregions layer lacks {sorted(required - set(eco.columns))}")

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
        "congo_moist": congo.intersection(unary_union(congo_basins.geometry)),
        "dry_forest": unary_union(list(dry.geometry) + list(chaco.geometry)),
        "sea_peat": indomalayan.intersection(unary_union(peat.geometry)),
    }


def candidate_universe(group_geometries: Mapping[str, object]) -> list[Candidate]:
    """Lattice centres falling inside each group polygon (L13.2 centre-membership rule).

    The naive form -- 308,374 lattice points x 4 groups of unioned multipolygons, tested
    one `covers()` call at a time -- is ~1.2M exact point-in-polygon tests against very
    large geometries and does not finish. This is purely an implementation optimization:
    a numpy bounding-box prefilter (which cannot change the answer, since a point outside
    the bbox is outside the polygon) followed by shapely `prepared` geometries for the
    exact test. Same lattice, same polygons, same membership rule, same candidates --
    only the constant factor changes. Order is preserved (group-major, then lattice order)
    so the seeded draw is unaffected.
    """
    from shapely.prepared import prep

    centres = np.array(list(lattice_centres()), dtype=np.float64)
    lons, lats = centres[:, 0], centres[:, 1]

    candidates: list[Candidate] = []
    for group in FRAME_GROUP_ORDER:
        geometry = group_geometries[group]
        if geometry.is_empty:
            continue
        west, south, east, north = geometry.bounds
        in_bbox = np.flatnonzero(
            (lons >= west) & (lons <= east) & (lats >= south) & (lats <= north)
        )
        ready = prep(geometry)
        for index in in_bbox:
            lon, lat = float(lons[index]), float(lats[index])
            if ready.covers(Point(lon, lat)):
                candidates.append(_candidate(group, lon, lat))
    return candidates


def count_at_risk_cells(data: FrameHansenWindow, inside: np.ndarray) -> int:
    """Count L5 at-risk cells in a box: cells whose eligible forest >= 25% of their valid land.

    Uses ONLY <=2020 information (treecover2000, datamask, and the firewalled prior-loss
    boolean). It counts AT-RISK cells, never POSITIVE cells -- gating eligibility on future
    positives would be outcome-informed site selection and would breach the L13.1 firewall.
    """
    land = inside & (data.datamask == 1)
    eligible = land & (data.treecover2000 >= 30) & ~data.prior_loss_2001_2020
    # Hansen is ~30 m; a 640 m analysis cell is ~21x21 native pixels.
    block = max(1, round(CELL_SIZE_M / 30.0))
    rows, cols = data.datamask.shape
    n_rows, n_cols = rows // block, cols // block
    if n_rows == 0 or n_cols == 0:
        return 0
    trim_land = land[:n_rows * block, :n_cols * block]
    trim_elig = eligible[:n_rows * block, :n_cols * block]
    land_per_cell = trim_land.reshape(n_rows, block, n_cols, block).sum(axis=(1, 3))
    elig_per_cell = trim_elig.reshape(n_rows, block, n_cols, block).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(land_per_cell > 0, elig_per_cell / land_per_cell, 0.0)
    return int(((land_per_cell > 0) & (share >= AT_RISK_LAND_FRACTION)).sum())


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
    # AMENDMENT-1: the binding box-level criterion is now a minimum AT-RISK CELL count,
    # not an eligible-forest share. Counts AT-RISK cells (a <=2020 quantity), NEVER positive
    # cells -- gating on positives would be outcome-informed selection and would breach the
    # L13.1 temporal firewall. forest_share is still RECORDED (the original >=50% rule is a
    # prespecified sensitivity) but no longer gates inclusion.
    at_risk_cells = count_at_risk_cells(data, inside)
    if not (
        valid_share >= FRAME_VALID_LAND_MIN
        and at_risk_cells >= FRAME_MIN_AT_RISK_CELLS
        and cumulative_share >= FRAME_CUMULATIVE_LOSS_MIN
        and recent_share >= FRAME_RECENT_LOSS_MIN
    ):
        return None
    return Candidate(
        **{**asdict(candidate), "valid_land_share": valid_share,
           "eligible_forest_share": forest_share,
           "cumulative_loss_share": cumulative_share,
           "recent_loss_share": recent_share,
           "at_risk_cells": at_risk_cells}
    )


def screen_universe(candidates: Iterable[Candidate],
                    reader: Callable[[tuple[float, float, float, float]], FrameHansenWindow]
                    = read_frame_hansen,
                    workers: int = 16,
                    checkpoint: Path | None = None,
                    checkpoint_every: int = 200) -> list[Candidate]:
    """Screen every candidate against L13.3, resumably.

    Each candidate needs a windowed Hansen read. Hansen GeoTIFFs are STRIPED
    (block_shapes == (1, 40000)), so a 0.25-degree window still decompresses ~900
    full-width LZW strips per band and costs ~30 s of thread time; 16k candidates is
    ~10 h. Threading hides the latency but cannot remove that waste, and a tile-major
    rewrite was tried, measured, found NOT faster on real tiles, and found to disagree
    with this function's statistics -- so it was discarded rather than shipped.

    What actually makes a 10-hour sweep practical is RESUMABILITY: results are appended to
    a JSONL checkpoint, so an interrupted run restarts from where it stopped instead of
    from zero.

    Threading and resumption change throughput only. Results are returned in the ORIGINAL
    candidate order, because the seeded permutation and the deterministic round-robin draw
    depend on it.
    """
    from concurrent.futures import ThreadPoolExecutor

    ordered = list(candidates)
    results: list[Candidate | None] = [None] * len(ordered)
    position = {candidate.candidate_id: index for index, candidate in enumerate(ordered)}
    completed: set[str] = set()

    if checkpoint and checkpoint.exists():
        errored: set[str] = set()
        for line in checkpoint.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            identifier = record["candidate_id"]
            index = position.get(identifier)
            if index is None:
                continue
            # A read ERROR is NOT a screening verdict. Treating a transient RasterioIOError
            # as "ineligible" would silently delete boxes from the sampling frame -- exactly
            # the quiet bias this whole design exists to prevent. Errored candidates are
            # therefore NOT marked complete, so a resume re-attempts them.
            if record.get("error"):
                errored.add(identifier)
                continue
            completed.add(identifier)
            if record.get("eligible"):
                results[index] = Candidate(**record["candidate"])
        print(f"resumed from checkpoint: {len(completed):,} screened, "
              f"{sum(1 for r in results if r is not None):,} eligible, "
              f"{len(errored):,} to retry after read errors", flush=True)

    todo = [(i, c) for i, c in enumerate(ordered) if c.candidate_id not in completed]
    if not todo:
        return [item for item in results if item is not None]

    def work(pair: tuple[int, Candidate]) -> tuple[int, Candidate, Candidate | None, bool]:
        index, candidate = pair
        # Retry transient network failures before giving up. An unretried read error would
        # be recorded as a screening verdict and silently drop the box from the frame.
        last: Exception | None = None
        for attempt in range(3):
            try:
                return index, candidate, screen_candidate(candidate, reader), False
            except Exception as exc:
                last = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        print(f"  {candidate.candidate_id} ERRORED after 3 tries: "
              f"{type(last).__name__}: {last}", flush=True)
        return index, candidate, None, True

    done = 0
    pending: list[str] = []
    handle = open(checkpoint, "a") if checkpoint else None
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, candidate, screened, errored_flag in pool.map(work, todo):
                results[index] = screened
                done += 1
                if handle:
                    pending.append(json.dumps({
                        "candidate_id": candidate.candidate_id,
                        "eligible": screened is not None,
                        "error": errored_flag,
                        "candidate": asdict(screened) if screened is not None else None,
                    }))
                    if len(pending) >= checkpoint_every:
                        handle.write("\n".join(pending) + "\n")
                        handle.flush()
                        pending.clear()
                if done % 250 == 0:
                    found = sum(1 for item in results if item is not None)
                    print(f"screened {len(completed) + done:,}/{len(ordered):,}; "
                          f"eligible {found:,}", flush=True)
        if handle and pending:
            handle.write("\n".join(pending) + "\n")
            handle.flush()
    finally:
        if handle:
            handle.close()

    return [item for item in results if item is not None]


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
                            for year in FEATURE_YEARS},
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
                     "version": "PEATMAP (Xu, Morris, Liu & Holden 2018, Catena) -- Asia peat extent"},
    }
    result = write_and_hash_frame(eligible, args.output_dir, manifest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
