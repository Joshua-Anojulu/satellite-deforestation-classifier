from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from forecast.specification_w import (
    ARCHIVE_YEARS,
    DOWNLOAD_SITE_YEARS,
    EXPECTED_TIFFS,
    FRAME_GROUP_ORDER,
    INNER_CONTAGION_FITS,
    K,
    NEW_TIFFS,
    SITES,
    build_amendment_artifacts,
    build_fold_table,
    primary_seed_sequence,
    replay_select_round_robin,
    specification_w_seed_sequence,
)
from risk.frame import Candidate, select_round_robin


DRAW_COORDINATES = {
    "amazon_moist": [
        ("F1_P000.180_M0063.250", -63.25, 0.18),
        ("F1_M009.940_M0075.750", -75.75, -9.94),
        ("F1_M009.060_M0069.500", -69.50, -9.06),
        ("F1_M010.820_M0063.000", -63.00, -10.82),
        ("F1_P001.060_M0070.000", -70.00, 1.06),
        ("F1_M004.660_M0077.750", -77.75, -4.66),
        ("F1_M008.620_M0061.500", -61.50, -8.62),
        ("F1_M003.780_M0074.750", -74.75, -3.78),
        ("F1_M002.900_M0053.750", -53.75, -2.90),
        ("F1_M011.480_M0073.250", -73.25, -11.48),
    ],
    "congo_moist": [
        ("F2_P003.040_P0021.250", 21.25, 3.04),
        ("F2_M002.900_P0024.000", 24.00, -2.90),
        ("F2_P002.600_P0028.250", 28.25, 2.60),
        ("F2_P002.380_P0022.250", 22.25, 2.38),
        ("F2_P001.500_P0028.500", 28.50, 1.50),
        ("F2_M003.340_P0024.250", 24.25, -3.34),
        ("F2_M000.480_P0020.250", 20.25, -0.48),
        ("F2_M002.900_P0018.500", 18.50, -2.90),
        ("F2_M001.360_P0026.000", 26.00, -1.36),
        ("F2_M003.560_P0026.500", 26.50, -3.56),
    ],
    "dry_forest": [
        ("F3_M015.220_M0057.500", -57.50, -15.22),
        ("F3_M020.720_M0058.500", -58.50, -20.72),
        ("F3_P018.220_M0071.250", -71.25, 18.22),
        ("F3_M013.240_M0042.750", -42.75, -13.24),
        ("F3_M005.540_M0044.000", -44.00, -5.54),
        ("F3_M023.140_M0057.250", -57.25, -23.14),
        ("F3_M022.040_M0063.500", -63.50, -22.04),
        ("F3_M011.040_M0041.250", -41.25, -11.04),
        ("F3_M006.640_M0038.000", -38.00, -6.64),
        ("F3_M022.920_M0059.250", -59.25, -22.92),
    ],
    "sea_peat": [
        ("F4_M002.900_P0105.500", 105.50, -2.90),
        ("F4_M002.460_P0111.500", 111.50, -2.46),
        ("F4_P004.140_P0114.250", 114.25, 4.14),
        ("F4_M001.580_P0114.500", 114.50, -1.58),
        ("F4_M001.800_P0104.250", 104.25, -1.80),
        ("F4_M001.360_P0103.750", 103.75, -1.36),
        ("F4_M000.480_P0102.750", 102.75, -0.48),
        ("F4_M003.120_P0105.500", 105.50, -3.12),
        ("F4_P003.920_P0101.000", 101.00, 3.92),
        ("F4_M000.260_P0109.500", 109.50, -0.26),
    ],
}


def _ordered_candidates() -> dict[str, list[Candidate]]:
    return {
        group: [
            Candidate(
                candidate_id=site_id,
                group=group,
                lon=lon,
                lat=lat,
                west=lon - 0.125,
                south=lat - 0.11,
                east=lon + 0.125,
                north=lat + 0.11,
            )
            for site_id, lon, lat in rows
        ]
        for group, rows in DRAW_COORDINATES.items()
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_primary_artifacts(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    ordered = _ordered_candidates()
    candidates = root / "candidate_frame.csv"
    draw = root / "ordered_draw.csv"
    fields = list(asdict(next(iter(ordered.values()))[0]))
    with candidates.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for group in FRAME_GROUP_ORDER:
            for candidate in ordered[group]:
                writer.writerow(asdict(candidate))
    with draw.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("group", "rank", "candidate_id", "lon", "lat", "selected", "consumed_at_draw"),
            lineterminator="\n",
        )
        writer.writeheader()
        primary_selected, primary_consumed = select_round_robin(ordered)
        selected_ids = {site.candidate_id for site in primary_selected}
        for group in FRAME_GROUP_ORDER:
            for index, candidate in enumerate(ordered[group]):
                writer.writerow({
                    "group": group,
                    "rank": index + 1,
                    "candidate_id": candidate.candidate_id,
                    "lon": candidate.lon,
                    "lat": candidate.lat,
                    "selected": int(candidate.candidate_id in selected_ids),
                    "consumed_at_draw": int(index in primary_consumed[group]),
                })
    sites = []
    for candidate in primary_selected:
        sites.append({**asdict(candidate), "cohort": "frame", "window_start_month": 6})
    manifest = root / "analysis_sites.json"
    manifest.write_text(json.dumps({
        "candidate_frame": {"path": str(candidates), "sha256": _sha(candidates)},
        "ordered_draw": {"path": str(draw), "sha256": _sha(draw)},
        "sites": sites,
    }, indent=2), encoding="utf-8")
    return manifest


def _fingerprint(sequence: np.random.SeedSequence) -> tuple[int, ...]:
    return tuple(int(value) for value in sequence.generate_state(4, dtype=np.uint32))


def test_k9_replays_registered_select_round_robin_with_sea_peat_skip():
    result = replay_select_round_robin(_ordered_candidates())
    ranks = {
        group: [
            result.draw_ranks[site.candidate_id]
            for site in result.retained if site.group == group
        ]
        for group in FRAME_GROUP_ORDER
    }
    assert ranks["amazon_moist"] == list(range(1, 10))
    assert ranks["congo_moist"] == list(range(1, 10))
    assert ranks["dry_forest"] == list(range(1, 10))
    assert ranks["sea_peat"] == [1, 2, 3, 4, 5, 6, 7, 9, 10]
    assert len(result.rejected) == 1
    rejection = result.rejected[0]
    assert rejection.candidate_id == "F4_M003.120_P0105.500"
    assert rejection.draw_rank == 8
    assert rejection.collided_with == "F4_M002.900_P0105.500"
    assert rejection.binding_distance_km == pytest.approx(24.33, abs=0.2)


def test_primary_three_round_default_is_unchanged():
    ordered = _ordered_candidates()
    primary, _ = select_round_robin(ordered)
    assert len(primary) == 12
    assert [site.candidate_id for site in primary] == [
        ordered[group][rank].candidate_id
        for rank in range(3)
        for group in FRAME_GROUP_ORDER
    ]


def test_frozen_w_quantities_are_separate_from_primary():
    assert K == 9
    assert SITES == 36
    assert DOWNLOAD_SITE_YEARS == 144
    assert EXPECTED_TIFFS == 720
    assert NEW_TIFFS == 576
    assert INNER_CONTAGION_FITS == 1260
    assert ARCHIVE_YEARS == (2018, 2019, 2020, 2021, 2022)


def test_fold_table_is_order_invariant_for_every_analysis_code():
    site_ids = [site.candidate_id for site in replay_select_round_robin(_ordered_candidates()).retained]
    first = build_fold_table(site_ids)
    second = build_fold_table(list(reversed(site_ids)))
    assert first == second
    assert [row["fold_index"] for row in first] == list(range(36))
    for row in first:
        fold = row["fold_index"]
        assert row["unit_indices"]["code_0"] == 0
        for code in range(1, 6):
            assert row["unit_indices"][f"code_{code}"] == fold
        assert row["unit_indices"]["code_6"] == {
            "temporal_attention_unet": 2 * fold,
            "channel_stacked_unet": 2 * fold + 1,
        }


def test_no_specification_w_rng_stream_collides_with_primary_v11():
    primary_keys = {(0, 0, 0)}
    w_keys = {(0, 0, 0)}
    for code in range(1, 5):
        primary_keys.update((code, fold, replicate) for fold in range(12) for replicate in range(1000))
        w_keys.update((code, fold, replicate) for fold in range(36) for replicate in range(1000))
    primary_keys.update((5, fold, 0) for fold in range(12))
    w_keys.update((5, fold, 0) for fold in range(36))
    primary_keys.update((6, unit, 0) for unit in range(24))
    w_keys.update((6, unit, 0) for unit in range(72))

    primary_streams = {
        _fingerprint(primary_seed_sequence(*key)) for key in primary_keys
    }
    w_streams = {
        _fingerprint(specification_w_seed_sequence(*key)) for key in w_keys
    }
    assert len(primary_streams) == len(primary_keys)
    assert len(w_streams) == len(w_keys)
    assert primary_streams.isdisjoint(w_streams)


def test_amendment_builder_is_deterministic_and_extends_all_site_periods(tmp_path):
    primary = _write_primary_artifacts(tmp_path / "source")
    first = build_amendment_artifacts(
        primary, tmp_path / "first", new_site_window_start=lambda _: 11
    )
    second = build_amendment_artifacts(
        primary, tmp_path / "second", new_site_window_start=lambda _: 11
    )
    for key in ("manifest", "manifest_hash", "selection_skips", "fold_table", "rng_map", "seal"):
        assert first[key].read_bytes() == second[key].read_bytes()

    document = json.loads(first["manifest"].read_text(encoding="utf-8"))
    assert document["specification"] == "Specification W"
    assert document["status"] == "AMENDED / EXPLORATORY"
    assert len(document["sites"]) == 36
    assert sum(site["amendment_role"] == "incumbent" for site in document["sites"]) == 12
    assert sum(site["amendment_role"] == "addition" for site in document["sites"]) == 24
    for site in document["sites"]:
        assert tuple(int(year) for year in site["periods"]) == ARCHIVE_YEARS
        assert site["periods"]["2022"][1].startswith("2022-")
    source = json.loads(primary.read_text(encoding="utf-8"))
    assert document["source_artifacts"]["candidate_frame"]["sha256"] == source["candidate_frame"]["sha256"]
    assert document["source_artifacts"]["ordered_draw"]["sha256"] == source["ordered_draw"]["sha256"]
    expected_hash = _sha(first["manifest"])
    assert first["manifest_hash"].read_text(encoding="ascii") == (
        f"{expected_hash}  {first['manifest'].name}\n"
    )


def test_builder_rechecks_frame_hashes_on_every_run(tmp_path):
    primary = _write_primary_artifacts(tmp_path / "source")
    document = json.loads(primary.read_text(encoding="utf-8"))
    Path(document["ordered_draw"]["path"]).write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ordered_draw hash mismatch"):
        build_amendment_artifacts(
            primary, tmp_path / "output", new_site_window_start=lambda _: 6
        )
