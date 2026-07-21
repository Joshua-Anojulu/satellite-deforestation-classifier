"""Non-binding Specification W evaluability diagnostic over censored masks.

This module has no raw-GFC or network code.  It consumes only the pre-lift
boolean handoff schema from :mod:`forecast.gfc_censor`, scores both permitted
origins, and keeps the worst-of-two quiet indicator separate from the assumed
single-test-year quiet rates used by the sensitivity curve.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from scipy import ndimage
from scipy.stats import beta

from .gfc_censor import FROZEN_GFC_RELEASE, PRE_LIFT_MASKS, load_handoff
from .prelift_sandbox import require_pre_lift_role
from .specification_w import (
    FRAME_GROUP_ORDER,
    K,
    MIN_COMPONENTS_PER_REGION,
    MIN_COMPONENTS_PER_SITE,
    MIN_EVALUABLE_SITES,
    SITES,
    load_and_verify_ordered_draw,
    replay_select_round_robin,
    sha256_file,
)

MIN_COMPONENT_PX = 2
CONNECTIVITY_8 = np.ones((3, 3), dtype=bool)
PERMITTED_ORIGINS = (2020, 2021)
ASSUMED_SINGLE_YEAR_QUIET_RATES = (0.10, 0.25, 0.40, 0.50)


@dataclass(frozen=True)
class SiteResult:
    site_id: str
    group: str
    draw_rank: int
    retained_position: int
    amendment_role: str
    eligible_px: Mapping[int, int]
    positives_px: Mapping[int, int]
    components: Mapping[int, int]
    eligible_px_test_origin: int


def count_components(positive_mask: np.ndarray) -> int:
    """Frozen 8-connectivity event algorithm with the two-pixel floor."""

    labelled, count = ndimage.label(np.asarray(positive_mask, dtype=bool), structure=CONNECTIVITY_8)
    if count == 0:
        return 0
    sizes = np.bincount(labelled.ravel())[1:]
    return int((sizes >= MIN_COMPONENT_PX).sum())


def score_site_masks(site: Mapping[str, object], masks: Mapping[str, np.ndarray]) -> SiteResult:
    if set(masks) != set(PRE_LIFT_MASKS):
        raise ValueError("precheck requires the exact pre-lift mask schema")
    shapes = {np.asarray(values).shape for values in masks.values()}
    if len(shapes) != 1 or any(np.asarray(values).dtype != np.bool_ for values in masks.values()):
        raise ValueError("handoff masks must be aligned boolean arrays")
    eligible_px = {
        2020: int(masks["eligible_2020"].sum()),
        2021: int(masks["eligible_2021"].sum()),
    }
    positives_px = {
        2020: int(masks["positive_2021"].sum()),
        2021: int(masks["positive_2022"].sum()),
    }
    components = {
        2020: count_components(masks["positive_2021"]),
        2021: count_components(masks["positive_2022"]),
    }
    return SiteResult(
        site_id=str(site["candidate_id"]),
        group=str(site["group"]),
        draw_rank=int(site["draw_rank"]),
        retained_position=int(site["retained_position"]),
        amendment_role=str(site["amendment_role"]),
        eligible_px=eligible_px,
        positives_px=positives_px,
        components=components,
        eligible_px_test_origin=int(masks["eligible_2022"].sum()),
    )


def _binomial_survival(k: int, minimum: int, quiet_rate: float) -> float:
    evaluable_rate = 1.0 - quiet_rate
    return float(sum(
        math.comb(k, count)
        * evaluable_rate ** count
        * quiet_rate ** (k - count)
        for count in range(minimum, k + 1)
    ))


def _one_sided_quiet_upper(observed: int, trials: int) -> float:
    if trials <= 0 or not 0 <= observed <= trials:
        raise ValueError((observed, trials))
    if observed == trials:
        return 1.0
    return float(beta.ppf(0.95, observed + 1, trials - observed))


def build_report(results: Sequence[SiteResult]) -> dict[str, object]:
    """Build the explicitly non-binding diagnostic and sensitivity report."""

    if len(results) != SITES or len({result.site_id for result in results}) != SITES:
        raise ValueError(f"Specification W precheck requires all {SITES} retained sites")
    counts = Counter(result.group for result in results)
    if any(counts[group] != K for group in FRAME_GROUP_ORDER):
        raise ValueError("Specification W precheck is not K-balanced")
    additions = [result for result in results if result.retained_position > 3]
    if len(additions) != 4 * (K - 3):
        raise ValueError("precheck additions must be retained positions 4 through K")

    origins: dict[str, object] = {}
    for origin in PERMITTED_ORIGINS:
        origin_groups = {}
        for group in FRAME_GROUP_ORDER:
            group_results = [result for result in results if result.group == group]
            evaluable = sum(
                result.components[origin] >= MIN_COMPONENTS_PER_SITE
                for result in group_results
            )
            components = sum(result.components[origin] for result in group_results)
            origin_groups[group] = {
                "evaluable_sites": evaluable,
                "retained_sites": K,
                "projected_mapped_components": components,
                "site_count_arm_passes": evaluable >= MIN_EVALUABLE_SITES,
                "component_arm_projection_passes": components >= MIN_COMPONENTS_PER_REGION,
                "projection_only_not_test_origin_fact": True,
            }
        origins[str(origin + 1)] = origin_groups

    quiet_by_group = {}
    for group in FRAME_GROUP_ORDER:
        group_additions = [result for result in additions if result.group == group]
        quiet_each_origin = {
            str(origin + 1): sum(
                result.components[origin] < MIN_COMPONENTS_PER_SITE
                for result in group_additions
            )
            for origin in PERMITTED_ORIGINS
        }
        quiet_worst = sum(
            min(result.components.values()) < MIN_COMPONENTS_PER_SITE
            for result in group_additions
        )
        quiet_by_group[group] = {
            "new_retained_sites": K - 3,
            "quiet_each_origin": quiet_each_origin,
            "quiet_worst_of_2021_2022": quiet_worst,
            "one_sided_95pct_upper_bound_worst_of_two": _one_sided_quiet_upper(
                quiet_worst, K - 3
            ),
        }
    pooled_quiet = sum(
        min(result.components.values()) < MIN_COMPONENTS_PER_SITE for result in additions
    )
    pooled = {
        "quiet_worst_of_2021_2022": pooled_quiet,
        "new_retained_sites": len(additions),
        "one_sided_95pct_upper_bound_worst_of_two": _one_sided_quiet_upper(
            pooled_quiet, len(additions)
        ),
        "assumptions": "homogeneous and independent additions across all four strata",
        "reported_separately_from_stratum_bounds": True,
    }
    sensitivity = []
    for quiet_rate in ASSUMED_SINGLE_YEAR_QUIET_RATES:
        per_stratum_floor = _binomial_survival(K, MIN_EVALUABLE_SITES, quiet_rate)
        per_stratum_slack = _binomial_survival(K, MIN_EVALUABLE_SITES + 1, quiet_rate)
        sensitivity.append({
            "assumed_iid_single_test_year_quiet_rate": quiet_rate,
            "probability_all_strata_meet_site_floor": per_stratum_floor ** 4,
            "probability_all_strata_have_at_least_one_site_slack": per_stratum_slack ** 4,
            "not_estimated_from_historical_diagnostic": True,
        })
    return {
        "specification": "Specification W",
        "status": "AMENDED / EXPLORATORY",
        "K": K,
        "permitted_outcomes": [2021, 2022],
        "precheck_is_strictly_non_binding": True,
        "only_permitted_failure_action": "stop and re-plan with Josh in a logged amendment",
        "prohibited_action": "resize K or edit the retained frame",
        "site_results": [asdict(result) for result in results],
        "origin_specific_projection": origins,
        "worst_of_two_stability_diagnostic": quiet_by_group,
        "pooled_diagnostic": pooled,
        "assumed_single_year_sensitivity": sensitivity,
        "scope": "site-count-arm resilience only; does not establish the full regional gate",
    }


def verify_manifest(manifest_path: str | Path) -> dict[str, object]:
    """Re-verify source hashes, joins, replay, and derived hashes on every run."""

    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("specification") != "Specification W" or manifest.get("K") != K:
        raise ValueError("not the frozen Specification W manifest")
    sources = manifest["source_artifacts"]
    primary_record = sources["primary_manifest"]
    if sha256_file(primary_record["path"]) != primary_record["sha256"]:
        raise RuntimeError("primary analysis_sites.json hash mismatch")
    ordered = load_and_verify_ordered_draw({
        "candidate_frame": sources["candidate_frame"],
        "ordered_draw": sources["ordered_draw"],
    })
    replay = replay_select_round_robin(ordered)
    sites = manifest["sites"]
    by_id = {site["candidate_id"]: site for site in sites}
    if len(by_id) != SITES or set(by_id) != {site.candidate_id for site in replay.retained}:
        raise RuntimeError("manifest does not match the frozen K=9 replay")
    for site in replay.retained:
        record = by_id[site.candidate_id]
        if (
            record["draw_rank"] != replay.draw_ranks[site.candidate_id]
            or record["retained_position"] != replay.retained_positions[site.candidate_id]
            or record["group"] != site.group
        ):
            raise RuntimeError(f"rank/provenance mismatch for {site.candidate_id}")
    for record in manifest["derived_artifacts"].values():
        artifact = manifest_path.parent / record["file"]
        if sha256_file(artifact) != record["sha256"]:
            raise RuntimeError(f"derived artifact hash mismatch: {artifact.name}")
    return manifest


def run_precheck(
    manifest_path: str | Path,
    handoff_root: str | Path,
    gfc_pin_path: str | Path,
) -> dict[str, object]:
    manifest = verify_manifest(manifest_path)
    handoff_root = Path(handoff_root)
    gfc_pin_path = Path(gfc_pin_path)
    pin = json.loads(gfc_pin_path.read_text(encoding="utf-8"))
    if pin.get("gfc_release") != FROZEN_GFC_RELEASE:
        raise ValueError("precheck GFC pin is not the frozen study release")
    results = []
    for site in manifest["sites"]:
        document, masks = load_handoff(handoff_root / site["candidate_id"])
        if document["phase"] != "pre_lift":
            raise ValueError("precheck may consume pre-lift handoffs only")
        if document["gfc_release"] != FROZEN_GFC_RELEASE:
            raise ValueError("handoff GFC release differs from the frozen pin")
        results.append(score_site_masks(site, masks))
    report = build_report(results)
    report["gfc_pin"] = {
        "path": str(gfc_pin_path.resolve()),
        "sha256": sha256_file(gfc_pin_path),
        "release": FROZEN_GFC_RELEASE,
    }
    return report


def main() -> None:
    require_pre_lift_role("precheck")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("handoff_root", type=Path)
    parser.add_argument("gfc_pin", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_precheck(args.manifest, args.handoff_root, args.gfc_pin)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
