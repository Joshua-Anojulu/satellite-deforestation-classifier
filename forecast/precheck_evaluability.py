"""Feasibility precheck: will the regional generalization gate have any margin?

FORECAST-PLAN.md §10 grants a region a per-region generalization estimate only if it
has >= 3 evaluable sites, where an evaluable site has >= 5 mapped loss components in
the test origin. The frame carries exactly 3 sites per stratum, so a SINGLE site
falling below the component floor takes its whole region dark. That is the failure
that retired the previous study on this branch (CONTEXT_HANDOFF.md §11: "the frame
breaks down BY STRATUM -- amazon_moist 2/3, sea_peat 1/3").

This script answers "is any stratum one marginal site from going dark?" BEFORE the
Sentinel archive is extended, using GFC alone.

*** LEAKAGE FIREWALL -- READ THIS BEFORE CHANGING ANYTHING HERE ***

This script NEVER reads the 2023 outcome. Counting test-origin loss components would
mean reading the test labels, and any frame decision taken in response (swapping a
marginal site, moving the floor) would be selection on the test outcome -- the same
class of breach as the round-8 variogram leak, and fatal to the study's central claim
in a way no amount of later disclosure repairs.

It therefore evaluates the TRAINING (2021) and VALIDATION (2022) outcomes only, both
of which are open under §F, and treats them as the projection basis for 2023. The
eligible-population mask AT the test origin IS computed -- eligibility at T=2022
depends on loss THROUGH 2022, not on the 2023 outcome -- because population size is a
design quantity the plan already treats as a retrospective product (§3).

Read-only. Downloads nothing to disk: GFC granules are read as windowed /vsicurl/
requests, so only each site's footprint crosses the network.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy import ndimage

# --- Frozen study parameters (FORECAST-PLAN.md) -------------------------------------
TREECOVER_THRESHOLD = 30       # theta, §4 population definition (default 30%)
MIN_COMPONENT_PX = 2           # §10 event algorithm, min size >= 2 px (~0.18 ha)
EVALUABLE_MIN_COMPONENTS = 5   # §10, an evaluable site has >= 5 mapped loss components
REGION_MIN_EVALUABLE_SITES = 3 # §10 regional gate
REGION_MIN_COMPONENTS = 30     # §10 regional gate
CONNECTIVITY_8 = np.ones((3, 3), dtype=bool)  # §10, 8-connectivity (4-conn is the sensitivity)

# GFC release. Pinned here for the precheck only; §5 pins the study's own version+md5
# at download time. v1.12 covers loss years 2001-2024.
GFC_VERSION = "GFC-2024-v1.12"
GFC_BASE = f"https://storage.googleapis.com/earthenginepartners-hansen/{GFC_VERSION}"

# Origins this script is PERMITTED to score. 2022 (-> 2023 outcome) is deliberately absent.
PERMITTED_ORIGINS = (2020, 2021)


@dataclass
class SiteResult:
    site_id: str
    group: str
    eligible_px: dict[int, int]
    positives_px: dict[int, int]
    components: dict[int, int]
    eligible_px_test_origin: int


def gfc_tile_name(north: float, west: float) -> str:
    """Hansen granules are 10x10 degrees, named by their TOP-LEFT corner."""
    top = math.ceil(north / 10.0) * 10
    left = math.floor(west / 10.0) * 10
    ns = "N" if top >= 0 else "S"
    ew = "E" if left >= 0 else "W"
    return f"{abs(top):02d}{ns}_{abs(left):03d}{ew}"


def tiles_for_bbox(west: float, south: float, east: float, north: float) -> list[str]:
    """Every granule intersecting the box (a site may straddle a granule seam)."""
    names = []
    lat = south
    while lat < north + 1e-9:
        lon = west
        while lon < east + 1e-9:
            name = gfc_tile_name(min(lat + 1e-9, north), lon)
            if name not in names:
                names.append(name)
            lon += 10.0
        lat += 10.0
    # also catch the exact top/right edges
    for name in (gfc_tile_name(north, west), gfc_tile_name(north, east), gfc_tile_name(south, east)):
        if name not in names:
            names.append(name)
    return names


def read_layer(layer: str, bbox: tuple[float, float, float, float]) -> np.ndarray:
    """Windowed read of one GFC layer over bbox, mosaicked across granule seams."""
    west, south, east, north = bbox
    out = None
    for tile in tiles_for_bbox(west, south, east, north):
        url = f"/vsicurl/{GFC_BASE}/Hansen_{GFC_VERSION}_{layer}_{tile}.tif"
        try:
            with rasterio.open(url) as src:
                # clip the request to what this granule actually covers
                b = src.bounds
                w, s = max(west, b.left), max(south, b.bottom)
                e, n = min(east, b.right), min(north, b.top)
                if w >= e or s >= n:
                    continue
                win = from_bounds(w, s, e, n, src.transform)
                data = src.read(1, window=win)
                if out is None:
                    out = data
                else:
                    # Sites are 0.25 deg; a straddle contributes a thin strip. Stack on
                    # the axis that matches, so component counting sees one field.
                    if out.shape[0] == data.shape[0]:
                        out = np.hstack([out, data])
                    elif out.shape[1] == data.shape[1]:
                        out = np.vstack([out, data])
                    else:
                        raise RuntimeError(f"cannot mosaic {tile} for {layer}: {out.shape} vs {data.shape}")
        except rasterio.errors.RasterioIOError:
            continue
    if out is None:
        raise RuntimeError(f"no GFC data read for {layer} over {bbox}")
    return out


def count_components(positive_mask: np.ndarray) -> int:
    """§10 event algorithm: 8-connectivity, components smaller than 2 px dropped."""
    labelled, n = ndimage.label(positive_mask, structure=CONNECTIVITY_8)
    if n == 0:
        return 0
    sizes = np.bincount(labelled.ravel())[1:]
    return int((sizes >= MIN_COMPONENT_PX).sum())


def score_site(site: dict) -> SiteResult:
    bbox = (site["west"], site["south"], site["east"], site["north"])
    treecover = read_layer("treecover2000", bbox)
    datamask = read_layer("datamask", bbox)
    lossyear = read_layer("lossyear", bbox)

    base = (datamask == 1) & (treecover >= TREECOVER_THRESHOLD)

    eligible_px, positives_px, components = {}, {}, {}
    for origin in PERMITTED_ORIGINS:
        t = origin - 2000
        eligible = base & ((lossyear == 0) | (lossyear > t))
        positive = eligible & (lossyear == t + 1)
        eligible_px[origin] = int(eligible.sum())
        positives_px[origin] = int(positive.sum())
        components[origin] = count_components(positive)

    # Population size at the TEST origin: depends on loss THROUGH 2022 only.
    t_test = 2022 - 2000
    eligible_test = base & ((lossyear == 0) | (lossyear > t_test))

    return SiteResult(
        site_id=site["candidate_id"],
        group=site["group"],
        eligible_px=eligible_px,
        positives_px=positives_px,
        components=components,
        eligible_px_test_origin=int(eligible_test.sum()),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sites", default=r"C:\Users\josha\ml-data\deforestation-risk\frame\analysis_sites.json")
    ap.add_argument("--only", default=None, help="score a single site id (smoke test)")
    args = ap.parse_args()

    doc = json.load(io.open(args.sites, encoding="utf-8"))
    rows = doc["sites"]
    rows = rows if isinstance(rows, list) else list(rows.values())
    frame = [s for s in rows if s.get("cohort") == "frame"]
    if args.only:
        frame = [s for s in frame if s["candidate_id"] == args.only]

    print(f"GFC release: {GFC_VERSION}   theta={TREECOVER_THRESHOLD}%   "
          f"origins scored: {PERMITTED_ORIGINS} (2022->2023 deliberately NOT scored)")
    print(f"frame sites: {len(frame)}\n")

    hdr = (f"{'site':30}{'group':14}{'elig@2022':>12}{'cmp 2021':>10}"
           f"{'cmp 2022':>10}{'min':>7}{'evaluable?':>12}")
    print(hdr)
    print("-" * len(hdr))

    results: list[SiteResult] = []
    for site in frame:
        r = score_site(site)
        results.append(r)
        worst = min(r.components[o] for o in PERMITTED_ORIGINS)
        verdict = "OK" if worst >= EVALUABLE_MIN_COMPONENTS else "** BELOW **"
        print(f"{r.site_id:30}{r.group:14}{r.eligible_px_test_origin:12,}"
              f"{r.components[2020]:10,}{r.components[2021]:10,}{worst:7,}{verdict:>12}")

    print("\n" + "=" * 78)
    print("STRATUM MARGIN (regional gate needs >= 3 evaluable sites AND >= 30 components)")
    print("=" * 78)
    ok_overall = True
    for group in sorted({r.group for r in results}):
        grp = [r for r in results if r.group == group]
        for origin in PERMITTED_ORIGINS:
            n_eval = sum(1 for r in grp if r.components[origin] >= EVALUABLE_MIN_COMPONENTS)
            total = sum(r.components[origin] for r in grp)
            margin = n_eval - REGION_MIN_EVALUABLE_SITES
            gate = (n_eval >= REGION_MIN_EVALUABLE_SITES) and (total >= REGION_MIN_COMPONENTS)
            flag = "PASS" if gate else "FAIL"
            note = "  <-- ZERO MARGIN" if margin == 0 and gate else ("  <-- DARK" if not gate else "")
            print(f"  {group:14} outcome {origin+1}: {n_eval}/{len(grp)} evaluable, "
                  f"{total:,} components  [{flag}]{note}")
            ok_overall &= gate
        print()

    print("Any stratum showing ZERO MARGIN is one marginal site from losing its regional")
    print("estimate in 2023 -- the failure mode that retired the previous study.")
    print("\nNOTE: 2023 is projected from 2021/2022, never measured. Do NOT re-run this")
    print("against the test origin to 'check' -- that would select the frame on test labels.")


if __name__ == "__main__":
    main()
