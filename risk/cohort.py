"""Deterministic L13 QC replacement bookkeeping and cohort-floor checks."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from .config import COMBINED_MINIMUM, FRAME_GROUP_ORDER, FRAME_MIN_SEPARATION_KM, FRAME_REQUIRED
from .frame import Candidate, distance_km


def load_ordered_candidates(candidate_frame: str | Path, ordered_draw: str | Path
                            ) -> dict[str, list[Candidate]]:
    with Path(candidate_frame).open(newline="", encoding="utf-8") as handle:
        candidates = {row["candidate_id"]: Candidate(
            candidate_id=row["candidate_id"], group=row["group"],
            lon=float(row["lon"]), lat=float(row["lat"]),
            west=float(row["west"]), south=float(row["south"]),
            east=float(row["east"]), north=float(row["north"]),
            valid_land_share=float(row["valid_land_share"]),
            eligible_forest_share=float(row["eligible_forest_share"]),
            cumulative_loss_share=float(row["cumulative_loss_share"]),
            recent_loss_share=float(row["recent_loss_share"]),
        ) for row in csv.DictReader(handle)}
    ordered = {group: [] for group in FRAME_GROUP_ORDER}
    with Path(ordered_draw).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ordered[row["group"]].append(candidates[row["candidate_id"]])
    return ordered


def next_replacement(group: str, ordered: Mapping[str, Sequence[Candidate]],
                     attempted_ids: set[str], retained: Sequence[Candidate]) -> Candidate:
    for candidate in ordered[group]:
        if candidate.candidate_id in attempted_ids:
            continue
        if all(distance_km(candidate, existing) >= FRAME_MIN_SEPARATION_KM for existing in retained):
            return candidate
    raise RuntimeError(f"No QC replacement remains in {group}.")


def attrition_report(frame_retained: Sequence[Candidate], frame_failures: Sequence[Candidate],
                     replacements: Sequence[Candidate], legacy_survivors: int) -> dict[str, object]:
    retained_counts = Counter(site.group for site in frame_retained)
    report = {
        "frame_retained_by_group": {group: retained_counts[group] for group in FRAME_GROUP_ORDER},
        "frame_qc_failures_by_group": dict(Counter(site.group for site in frame_failures)),
        "frame_replacements_by_group": dict(Counter(site.group for site in replacements)),
        "frame_floor_passed": len(frame_retained) == FRAME_REQUIRED
                              and all(retained_counts[group] == 3 for group in FRAME_GROUP_ORDER),
        "combined_sites": len(frame_retained) + int(legacy_survivors),
    }
    report["combined_floor_passed"] = report["combined_sites"] >= COMBINED_MINIMUM
    return report
