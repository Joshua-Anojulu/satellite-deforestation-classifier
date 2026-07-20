"""Feasibility of a DISJOINT two-class vegetation control, split by frontier exposure.

Codex r3#8 demanded two independently defined control classes, failing D2 when their
corrections disagree, so the favourable class can never be chosen. The water class is
infeasible (10/19 sites). This tests an alternative whose two classes probe the actual
concern behind #8 -- degradation contamination of a vegetation control -- rather than
surface-type transport:

  (a) veg_near : intact forest (datamask==1, tree>=70, no 2001-2020 loss) WITHIN  640 m of loss
  (b) veg_far  : intact forest (same definition)                          BEYOND 640 m of loss

DISJOINT by construction (not nested, so agreement is not tautological). Both are forest,
so radiometric transport to the target is ideal. If drift estimated from frontier-adjacent
forest disagrees with drift from interior forest, the estimate is contaminated by real
degradation -> D2 fails.

Distances use the 1,980 m halo per D. Label-blind (<=2020 Hansen only), read-only.
The 640 m split is CELL_SIZE_M, the study's own grid unit -- not a tuned value.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from pyproj import Geod

from risk.config import PIF_TREECOVER_THRESHOLD, CELL_SIZE_M
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

geod = Geod(ellps="WGS84")
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))


def blocks_with(mask, block_px, min_px):
    h, w = mask.shape
    bh, bw = block_px
    nh, nw = h // bh, w // bw
    if nh == 0 or nw == 0:
        return 0
    trimmed = mask[: nh * bh, : nw * bw]
    counts = trimmed.reshape(nh, bh, nw, bw).sum(axis=(1, 3))
    return int((counts >= min_px).sum())


print("Disjoint vegetation controls split at 640 m from nearest 2001-2020 loss pixel.\n")
print(f"{'site':<26}{'near px':>10}{'nearB>=53':>11}{'far px':>10}{'farB>=53':>10}  both?")
print("-" * 80)
rows = []
for site in manifest["sites"]:
    site_id = str(site["candidate_id"])
    bbox = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    inner = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    halo = 1980.0
    dlat = halo / 110_574.0
    dlon = halo / (111_320.0 * max(0.05, np.cos(np.radians((inner[1] + inner[3]) / 2))))
    bounds = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)

    hansen = read_hansen_window(bounds)
    loss = hansen.arrays["lossyear"]
    tree = hansen.arrays["treecover2000"]
    datamask = hansen.arrays["datamask"]
    prior = (loss >= 1) & (loss <= 20)
    veg = (datamask == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior

    centre_lat = (bounds[1] + bounds[3]) / 2
    _, _, x_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c + abs(hansen.transform.a), centre_lat)
    _, _, y_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c, centre_lat + abs(hansen.transform.e))
    sampling = (abs(y_size), abs(x_size))
    distance = (distance_transform_edt(~prior, sampling=sampling) if prior.any()
                else np.full(prior.shape, np.inf))

    rows_i, cols_i = np.indices(veg.shape)
    xs = hansen.transform.c + (cols_i + 0.5) * hansen.transform.a
    ys = hansen.transform.f + (rows_i + 0.5) * hansen.transform.e
    inside = (xs >= inner[0]) & (xs <= inner[2]) & (ys >= inner[1]) & (ys <= inner[3])

    near = veg & (distance < CELL_SIZE_M) & inside
    far = veg & (distance >= CELL_SIZE_M) & inside
    block_px = (max(1, int(round(CELL_SIZE_M / sampling[0]))),
                max(1, int(round(CELL_SIZE_M / sampling[1]))))

    r = dict(site=site_id, near_px=int(near.sum()), far_px=int(far.sum()),
             near_b=blocks_with(near, block_px, 53), far_b=blocks_with(far, block_px, 53))
    rows.append(r)
    both = "YES" if (r["near_b"] > 0 and r["far_b"] > 0) else "*** NO ***"
    print(f"{r['site']:<26}{r['near_px']:>10}{r['near_b']:>11}{r['far_px']:>10}{r['far_b']:>10}  {both}")
    sys.stdout.flush()

print("-" * 80)
n_both = sum(1 for r in rows if r["near_b"] > 0 and r["far_b"] > 0)
n_near = sum(1 for r in rows if r["near_b"] > 0)
n_far = sum(1 for r in rows if r["far_b"] > 0)
print(f"blocks >=53 px: near {n_near}/19 sites, far {n_far}/19 sites, BOTH {n_both}/19")
print("(water class for comparison: BOTH 10/19 — the design this replaces)")
