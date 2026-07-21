"""Frozen, additive configuration and artifacts for Specification W.

``risk.config`` remains the 12-site v11 primary configuration.  Nothing in this
module mutates it: W has a separate K, manifest, folds, RNG coordinate, audit
namespace, and result namespace.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

from risk.config import FRAME_GROUP_ORDER, FRAME_MIN_SEPARATION_KM, SEED
from risk.frame import Candidate, select_round_robin
from risk.seasons import driest_four_month_window

from .prelift_sandbox import require_pre_lift_role

SPECIFICATION_NAME = "Specification W"
SPECIFICATION_STATUS = "AMENDED / EXPLORATORY"
SPECIFICATION_CODE = 1
K = 9
K_MAX = 9
SITES = 4 * K
NEW_SITES = SITES - 12
ARCHIVE_YEARS = (2018, 2019, 2020, 2021, 2022)
MODEL_HISTORY_YEARS = 3
DOWNLOAD_SITE_YEARS = 20 * K - 36
TIFFS_PER_SITE_YEAR = 4
EXPECTED_TIFFS = SITES * len(ARCHIVE_YEARS) * TIFFS_PER_SITE_YEAR
NEW_TIFFS = DOWNLOAD_SITE_YEARS * TIFFS_PER_SITE_YEAR
INNER_CONTAGION_FITS = SITES * (SITES - 1)
AUDIT_BUDGET_PER_BIOME = 180
RESULT_NAMESPACE = "specification_w_exploratory"
MIN_COMPONENTS_PER_SITE = 5
MIN_EVALUABLE_SITES = 3
MIN_COMPONENTS_PER_REGION = 30

assert K == K_MAX == 9
assert (SITES, NEW_SITES, DOWNLOAD_SITE_YEARS) == (36, 24, 144)
assert (EXPECTED_TIFFS, NEW_TIFFS, INNER_CONTAGION_FITS) == (720, 576, 1260)


@dataclass(frozen=True)
class RejectedDraw:
    group: str
    draw_rank: int
    candidate_id: str
    binding_distance_km: float
    collided_with: str


@dataclass(frozen=True)
class ReplayResult:
    retained: tuple[Candidate, ...]
    retained_positions: Mapping[str, int]
    draw_ranks: Mapping[str, int]
    rejected: tuple[RejectedDraw, ...]


def replay_select_round_robin(
    ordered: Mapping[str, Sequence[Candidate]],
    *,
    sites_per_group: int = K,
) -> ReplayResult:
    """Replay the registered cross-stratum sequential-inhibition algorithm."""

    if sites_per_group <= 0:
        raise ValueError("sites_per_group must be positive")
    if set(ordered) != set(FRAME_GROUP_ORDER):
        raise ValueError("ordered draw must contain the four frozen strata exactly")
    rejected: list[RejectedDraw] = []
    def record_rejection(
        group: str, draw_rank: int, candidate: Candidate,
        distance: float, collided_with: Candidate,
    ) -> None:
        rejected.append(RejectedDraw(
            group=group,
            draw_rank=draw_rank,
            candidate_id=candidate.candidate_id,
            binding_distance_km=distance,
            collided_with=collided_with.candidate_id,
        ))

    retained, _ = select_round_robin(
        ordered, sites_per_group=sites_per_group, rejection_recorder=record_rejection
    )
    retained_positions: dict[str, int] = {}
    draw_ranks: dict[str, int] = {}
    rank_by_id = {
        candidate.candidate_id: index + 1
        for group in FRAME_GROUP_ORDER
        for index, candidate in enumerate(ordered[group])
    }
    per_group = Counter()
    for candidate in retained:
        per_group[candidate.group] += 1
        retained_positions[candidate.candidate_id] = per_group[candidate.group]
        draw_ranks[candidate.candidate_id] = rank_by_id[candidate.candidate_id]
    if len(retained) != 4 * sites_per_group or any(
        per_group[group] != sites_per_group for group in FRAME_GROUP_ORDER
    ):
        raise AssertionError("round-robin replay did not produce a balanced frame")
    return ReplayResult(tuple(retained), retained_positions, draw_ranks, tuple(rejected))


def _candidate_from_csv(record: Mapping[str, str]) -> Candidate:
    def optional_float(name: str) -> float | None:
        value = record.get(name, "")
        return None if value in (None, "") else float(value)

    at_risk = record.get("at_risk_cells", "")
    return Candidate(
        candidate_id=record["candidate_id"],
        group=record["group"],
        lon=float(record["lon"]),
        lat=float(record["lat"]),
        west=float(record["west"]),
        south=float(record["south"]),
        east=float(record["east"]),
        north=float(record["north"]),
        valid_land_share=optional_float("valid_land_share"),
        eligible_forest_share=optional_float("eligible_forest_share"),
        cumulative_loss_share=optional_float("cumulative_loss_share"),
        recent_loss_share=optional_float("recent_loss_share"),
        at_risk_cells=None if at_risk in (None, "") else int(float(at_risk)),
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_and_verify_ordered_draw(
    primary_manifest: Mapping[str, object],
) -> dict[str, list[Candidate]]:
    """Verify both frozen frame hashes and the one-to-one rank/candidate join."""

    source_records: dict[str, Mapping[str, str]] = {}
    candidate_record = primary_manifest["candidate_frame"]
    order_record = primary_manifest["ordered_draw"]
    if not isinstance(candidate_record, Mapping) or not isinstance(order_record, Mapping):
        raise ValueError("primary frame artifact records are malformed")
    for name, record in (("candidate_frame", candidate_record), ("ordered_draw", order_record)):
        actual = sha256_file(record["path"])
        if actual != record["sha256"]:
            raise RuntimeError(f"{name} hash mismatch: {actual} != {record['sha256']}")
    with Path(candidate_record["path"]).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            candidate_id = row["candidate_id"]
            if candidate_id in source_records:
                raise ValueError(f"duplicate candidate id: {candidate_id}")
            source_records[candidate_id] = row
    ordered = {group: [] for group in FRAME_GROUP_ORDER}
    seen: set[str] = set()
    ranks = {group: [] for group in FRAME_GROUP_ORDER}
    with Path(order_record["path"]).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            group = row["group"]
            candidate_id = row["candidate_id"]
            if group not in ordered or candidate_id not in source_records:
                raise ValueError("ordered draw does not join one-to-one to candidate_frame")
            if candidate_id in seen:
                raise ValueError(f"candidate appears more than once in ordered draw: {candidate_id}")
            candidate = _candidate_from_csv(source_records[candidate_id])
            if candidate.group != group:
                raise ValueError(f"group mismatch for {candidate_id}")
            seen.add(candidate_id)
            ranks[group].append(int(row["rank"]))
            ordered[group].append(candidate)
    if seen != set(source_records):
        raise ValueError("ordered draw and candidate_frame are not a one-to-one join")
    for group, values in ranks.items():
        if values != list(range(1, len(values) + 1)):
            raise ValueError(f"non-contiguous ranks in {group}")
    return ordered


def archive_period(year: int, start_month: int) -> tuple[str, str]:
    """W's archive window, separate from the primary <=2020 feature guard."""

    import calendar

    if year not in ARCHIVE_YEARS or not 1 <= start_month <= 12:
        raise ValueError((year, start_month))
    end_month = ((start_month - 1 + 3) % 12) + 1
    start_year = year - 1 if end_month < start_month else year
    start = date(start_year, start_month, 1)
    end = date(year, end_month, calendar.monthrange(year, end_month)[1])
    if end.year > 2022:
        raise AssertionError("Specification W archive period crossed 2022")
    return start.isoformat(), end.isoformat()


def build_fold_table(site_ids: Sequence[str]) -> list[dict[str, object]]:
    """Freeze W fold/unit indices in ascending held-out-site order."""

    canonical = sorted(site_ids)
    if len(canonical) != SITES or len(set(canonical)) != SITES:
        raise ValueError(f"Specification W requires exactly {SITES} unique sites")
    return [
        {
            "site_id": site_id,
            "fold_index": fold,
            "unit_indices": {
                "code_0": 0,
                **{f"code_{code}": fold for code in range(1, 6)},
                "code_6": {
                    "temporal_attention_unet": 2 * fold,
                    "channel_stacked_unet": 2 * fold + 1,
                },
            },
        }
        for fold, site_id in enumerate(canonical)
    ]


def primary_seed_sequence(analysis_code: int, unit_index: int, replicate: int) -> np.random.SeedSequence:
    """The unchanged v11 key, exposed only for collision verification."""

    return np.random.SeedSequence(
        SEED, spawn_key=(int(analysis_code), int(unit_index), int(replicate))
    )


def specification_w_seed_sequence(
    analysis_code: int, unit_index: int, replicate: int
) -> np.random.SeedSequence:
    """W's frozen four-coordinate RNG namespace."""

    return np.random.SeedSequence(
        SEED,
        spawn_key=(SPECIFICATION_CODE, int(analysis_code), int(unit_index), int(replicate)),
    )


def specification_w_rng(
    analysis_code: int, unit_index: int, replicate: int
) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(
        specification_w_seed_sequence(analysis_code, unit_index, replicate)
    ))


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def build_amendment_artifacts(
    primary_manifest_path: str | Path,
    output_dir: str | Path,
    *,
    new_site_window_start: Callable[[Candidate], int],
) -> dict[str, Path]:
    """Build W's deterministic manifest, skip log, folds, RNG map, and seal."""

    primary_manifest_path = Path(primary_manifest_path).resolve()
    output_dir = Path(output_dir).resolve()
    primary = json.loads(primary_manifest_path.read_text(encoding="utf-8"))
    ordered = load_and_verify_ordered_draw(primary)
    replay = replay_select_round_robin(ordered)
    incumbent_sites = {
        site["candidate_id"]: site
        for site in primary["sites"]
        if site.get("cohort") == "frame"
    }
    expected_incumbents = {
        site.candidate_id for site in replay.retained
        if replay.retained_positions[site.candidate_id] <= 3
    }
    if set(incumbent_sites) != expected_incumbents:
        raise RuntimeError("K=9 replay does not preserve the complete 12-site v11 frame")

    sites: list[dict[str, object]] = []
    for candidate in replay.retained:
        position = replay.retained_positions[candidate.candidate_id]
        incumbent = incumbent_sites.get(candidate.candidate_id)
        start_month = (
            int(incumbent["window_start_month"])
            if incumbent is not None
            else int(new_site_window_start(candidate))
        )
        sites.append({
            **asdict(candidate),
            "cohort": "frame",
            "specification": SPECIFICATION_NAME,
            "amendment_role": "incumbent" if position <= 3 else "addition",
            "draw_rank": replay.draw_ranks[candidate.candidate_id],
            "retained_position": position,
            "selection_algorithm": "cross-stratum sequential inhibition",
            "minimum_separation_km": FRAME_MIN_SEPARATION_KM,
            "window_start_month": start_month,
            "periods": {
                str(year): list(archive_period(year, start_month)) for year in ARCHIVE_YEARS
            },
        })

    skip_path = output_dir / "specification_w_selection_skips.json"
    fold_path = output_dir / "specification_w_fold_table.json"
    rng_path = output_dir / "specification_w_rng_map.json"
    manifest_path = output_dir / "specification_w_manifest.json"
    skips = [asdict(item) for item in replay.rejected]
    skip_hash = _write_json(skip_path, {
        "specification": SPECIFICATION_NAME,
        "minimum_separation_km": FRAME_MIN_SEPARATION_KM,
        "rejected_draws": skips,
    })
    folds = build_fold_table([site["candidate_id"] for site in sites])
    fold_hash = _write_json(fold_path, {
        "specification": SPECIFICATION_NAME,
        "ordering": "ascending held-out site_id",
        "folds": folds,
    })
    rng_hash = _write_json(rng_path, {
        "specification": SPECIFICATION_NAME,
        "entropy": SEED,
        "bit_generator": "PCG64",
        "seed_sequence_spawn_key": [
            SPECIFICATION_CODE, "analysis_code", "unit_index", "replicate",
        ],
        "analysis_codes": {
            "0": "detector-audit survey sampling",
            "1": "headline block bootstrap at 30 m",
            "2": "headline block bootstrap at 90 m",
            "3": "gap-diagnostic bootstrap",
            "4": "deep-model gate bootstrap",
            "5": "variogram-range estimation",
            "6": "model weight init / training shuffles",
        },
        "fold_table_sha256": fold_hash,
    })
    manifest = {
        "schema_version": 1,
        "specification": SPECIFICATION_NAME,
        "status": SPECIFICATION_STATUS,
        "primary_specification": "12-site v11",
        "K": K,
        "K_max": K_MAX,
        "site_count": SITES,
        "archive_years": list(ARCHIVE_YEARS),
        "rolling_model_history_years": MODEL_HISTORY_YEARS,
        "audit_budget_per_biome": AUDIT_BUDGET_PER_BIOME,
        "result_namespace": RESULT_NAMESPACE,
        "source_artifacts": {
            "primary_manifest": {
                "path": str(primary_manifest_path),
                "sha256": sha256_file(primary_manifest_path),
            },
            "candidate_frame": primary["candidate_frame"],
            "ordered_draw": primary["ordered_draw"],
        },
        "derived_artifacts": {
            "selection_skips": {"file": skip_path.name, "sha256": skip_hash},
            "fold_table": {"file": fold_path.name, "sha256": fold_hash},
            "rng_map": {"file": rng_path.name, "sha256": rng_hash},
        },
        "unchanged_gates": {
            "evaluable_site_min_components": MIN_COMPONENTS_PER_SITE,
            "regional_min_evaluable_sites": MIN_EVALUABLE_SITES,
            "regional_min_components": MIN_COMPONENTS_PER_REGION,
            "sar_pilot_sites": 3,
        },
        "sites": sites,
    }
    manifest_hash = _write_json(manifest_path, manifest)
    hash_path = manifest_path.with_suffix(manifest_path.suffix + ".sha256")
    hash_path.write_text(f"{manifest_hash}  {manifest_path.name}\n", encoding="ascii")
    seal_path = output_dir / "specification_w_seal.json"
    _write_json(seal_path, {
        "specification": SPECIFICATION_NAME,
        "artifacts": {
            manifest_path.name: manifest_hash,
            skip_path.name: skip_hash,
            fold_path.name: fold_hash,
            rng_path.name: rng_hash,
        },
    })
    return {
        "manifest": manifest_path,
        "manifest_hash": hash_path,
        "selection_skips": skip_path,
        "fold_table": fold_path,
        "rng_map": rng_path,
        "seal": seal_path,
    }


def main() -> None:
    require_pre_lift_role("freezing")
    parser = argparse.ArgumentParser(description="Build frozen Specification W artifacts.")
    parser.add_argument("primary_manifest", type=Path)
    parser.add_argument("chirps", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    import xarray as xr

    # The source file is multi-gigabyte; reuse one dataset handle for all 24 new
    # sites while preserving the exact CHIRPS 1991--2020 point-climatology rule.
    with xr.open_dataset(args.chirps) as dataset:
        variable_name = "precip" if "precip" in dataset.data_vars else next(iter(dataset.data_vars))
        climatology_source = dataset[variable_name].sel(time=slice("1991-01-01", "2020-12-31"))
        if climatology_source.sizes.get("time") != 360:
            raise ValueError("CHIRPS subset must contain exactly 360 months")

        def start_month(candidate: Candidate) -> int:
            point = climatology_source.sel(
                longitude=candidate.lon, latitude=candidate.lat, method="nearest"
            )
            values = point.groupby("time.month").sum("time", skipna=False).values
            return driest_four_month_window(values)

        build_amendment_artifacts(
            args.primary_manifest, args.output_dir, new_site_window_start=start_month
        )


if __name__ == "__main__":
    main()
