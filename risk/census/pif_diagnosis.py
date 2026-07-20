"""READ-ONLY diagnosis of why the locked PIF criterion is unsatisfiable.

Writes nothing into the study tree and changes no locked parameter. Every number
below is FEASIBILITY (can a PIF population exist at all), never a study RESULT.

The hazard this must not walk into: choosing a PIF definition because it yields a
workable cohort is cohort-size tuning, which is exactly what the plan's freeze
exists to prevent. So this reports the readings side by side and does not rank them.

Readings compared:
  A  LITERAL / AS LOCKED : pixel >= 1,920 m from ANY 2001-2020 loss pixel (L3 as written).
  B  LOSS-CELL           : pixel >= 1,920 m from any 640 m neighbourhood whose loss
                           fraction over the forest universe is >= 0.25. This is the
                           plan's OWN other definition of "a cleared place"
                           (b_dist_nearest_loss, L20 >= 0.25). Implemented as a moving
                           window, so it is grid-phase independent -- a PROXY for the
                           study's aligned 640 m cells, not identical to them.
  D  SPECKLE             : reading A after dropping prior-loss clusters < 5 pixels
                           (~0.45 ha). Diagnostic of noise sensitivity ONLY.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt, label, uniform_filter
from pyproj import Geod

from risk.config import MIN_PIF_PIXELS, PIF_TREECOVER_THRESHOLD
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

PIF_DISTANCE_M = 1_920.0
LOSS_CELL_FRACTION = 0.25
CELL_M = 640.0


def _distance_to(mask, sampling):
    if not mask.any():
        return np.full(mask.shape, np.inf)
    return distance_transform_edt(~mask, sampling=sampling)


manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
geod = Geod(ellps="WGS84")
rows = []

for site in manifest["sites"]:
    site_id = str(site["candidate_id"])
    bbox = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    bounds = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    hansen = read_hansen_window(bounds)
    loss = hansen.arrays["lossyear"]
    tree = hansen.arrays["treecover2000"]
    datamask = hansen.arrays["datamask"]

    prior = (loss >= 1) & (loss <= 20)
    universe = (datamask == 1) & (tree >= 30)
    base = (datamask == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior

    centre_lat = (bounds[1] + bounds[3]) / 2
    _, _, x_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c + abs(hansen.transform.a), centre_lat)
    _, _, y_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c, centre_lat + abs(hansen.transform.e))
    sampling = (abs(y_size), abs(x_size))

    # --- A: as locked -------------------------------------------------------
    dist_a = _distance_to(prior, sampling)
    pif_a = int((base & (dist_a >= PIF_DISTANCE_M)).sum())

    # --- B: loss-cell reading (moving-window proxy for aligned 640 m cells) --
    win = (max(1, int(round(CELL_M / sampling[0]))), max(1, int(round(CELL_M / sampling[1]))))
    loss_num = uniform_filter((prior & universe).astype(np.float32), size=win, mode="nearest")
    univ_den = uniform_filter(universe.astype(np.float32), size=win, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        loss_frac = np.where(univ_den > 0, loss_num / univ_den, 0.0)
    loss_cells = loss_frac >= LOSS_CELL_FRACTION
    dist_b = _distance_to(loss_cells, sampling)
    pif_b = int((base & (dist_b >= PIF_DISTANCE_M)).sum())

    # --- D: speckle sensitivity --------------------------------------------
    labelled, n_clusters = label(prior)
    if n_clusters:
        sizes = np.bincount(labelled.ravel())
        sizes[0] = 0
        small = np.isin(labelled, np.flatnonzero((sizes > 0) & (sizes < 5)))
        prior_despeckled = prior & ~small
        speck_frac = float(small.sum() / prior.sum()) if prior.sum() else 0.0
        median_cluster = float(np.median(sizes[sizes > 0]))
    else:
        prior_despeckled, speck_frac, median_cluster = prior, 0.0, 0.0
    dist_d = _distance_to(prior_despeckled, sampling)
    pif_d = int((base & (dist_d >= PIF_DISTANCE_M)).sum())

    # --- treecover sensitivity (dry-forest structural issue) ----------------
    base_50 = (datamask == 1) & (tree >= 50) & ~prior
    base_30 = (datamask == 1) & (tree >= 30) & ~prior

    rows.append(dict(
        site=site_id, group=str(site.get("group", "")),
        base70=int(base.sum()), base50=int(base_50.sum()), base30=int(base_30.sum()),
        pif_a=pif_a, pif_b=pif_b, pif_d=pif_d,
        maxdist_a=float(dist_a[base].max()) if base.any() else 0.0,
        maxdist_b=float(dist_b[base].max()) if base.any() else 0.0,
        n_clusters=int(n_clusters), median_cluster_px=median_cluster,
        speckle_frac=speck_frac,
        pif_b_50=int((base_50 & (dist_b >= PIF_DISTANCE_M)).sum()),
    ))

ok = lambda n: "PASS" if n >= MIN_PIF_PIXELS else "fail"
print("PIF population under each reading (>= 5,000 pixels required)\n")
print(f"{'site':<26}{'stratum':<14}{'A:locked':>10}{'B:losscell':>12}{'D:despeck':>11}   verdicts")
print("-" * 92)
for r in rows:
    print(f"{r['site']:<26}{r['group']:<14}{r['pif_a']:>10}{r['pif_b']:>12}{r['pif_d']:>11}   "
          f"A={ok(r['pif_a']):<4} B={ok(r['pif_b']):<4} D={ok(r['pif_d'])}")
print("-" * 92)
for key, name in (("pif_a", "A literal (as locked)"), ("pif_b", "B loss-cell proxy"), ("pif_d", "D despeckled")):
    n_all = sum(1 for r in rows if r[key] >= MIN_PIF_PIXELS)
    n_frame = sum(1 for r in rows if r[key] >= MIN_PIF_PIXELS and r["site"].startswith("F"))
    print(f"{name:<24} cohort {n_all:>2}/19 (floor 14)   frame {n_frame:>2}/12 (needs 12/12)")

print("\nWhy the box saturates -- prior-loss structure (diagnostic, not a dial):")
print(f"{'site':<26}{'clusters':>10}{'med px':>9}{'<5px share':>12}{'maxdist A':>11}{'maxdist B':>11}")
print("-" * 92)
for r in rows:
    print(f"{r['site']:<26}{r['n_clusters']:>10}{r['median_cluster_px']:>9.0f}"
          f"{r['speckle_frac']:>11.1%}{r['maxdist_a']:>11.0f}{r['maxdist_b']:>11.0f}")

print("\nTreecover threshold sensitivity (PIF base population, no distance rule):")
print(f"{'site':<26}{'stratum':<14}{'>=70 (locked)':>15}{'>=50':>10}{'>=30':>10}")
print("-" * 92)
for r in rows:
    print(f"{r['site']:<26}{r['group']:<14}{r['base70']:>15}{r['base50']:>10}{r['base30']:>10}")
