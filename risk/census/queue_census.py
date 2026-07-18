"""READ-ONLY: does the plan's own L13.5 replacement queue survive the locked PIF rule?

L13.5 prescribes the remedy for an L2 QC failure -- and the PIF floor IS an L2 check:
"QC failure (L2) -> take the next box in that stratum's queue. Never a re-roll, never
by hand." So the question is not "which threshold" but "does the pre-drawn queue
contain passing boxes, or is PIF failure a property of the stratum?"

Walks each stratum's rng(42)-ordered queue in rank order and applies the LOCKED
reading (A): PIF pixel = datamask==1, treecover2000>=70, no 2001-2020 loss,
>=1,920 m from ANY 2001-2020 loss pixel; floor 5,000 px on the buffered extent.

Changes nothing, downloads no imagery, writes nothing into the study tree. Hansen
only. This tests FEASIBILITY of replacement, not any study outcome. Note it does NOT
apply the L13.4 >=50 km greedy separation check, so its pass counts are an UPPER
BOUND on how many replacements are actually usable.
"""
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from pyproj import Geod

from risk.config import MIN_PIF_PIXELS, PIF_TREECOVER_THRESHOLD, LATTICE_BOX_SIZE
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

PER_STRATUM = int(sys.argv[2]) if len(sys.argv) > 2 else 25
geod = Geod(ellps="WGS84")
rows = list(csv.DictReader(open(sys.argv[1])))

by_group = {}
for r in rows:
    by_group.setdefault(r["group"], []).append(r)
for group in by_group:
    by_group[group].sort(key=lambda r: int(r["rank"]))


def pif_count(lon, lat):
    box = {
        "west": lon - LATTICE_BOX_SIZE[0] / 2, "east": lon + LATTICE_BOX_SIZE[0] / 2,
        "south": lat - LATTICE_BOX_SIZE[1] / 2, "north": lat + LATTICE_BOX_SIZE[1] / 2,
    }
    bbox = buffered_bbox(box)
    inner = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    # Codex finding #2: distance must see loss OUTSIDE the extent, else edge pixels
    # get inflated distances and are wrongly counted as PIF.
    halo = 1980.0
    dlat = halo / 110_574.0
    dlon = halo / (111_320.0 * max(0.05, np.cos(np.radians((inner[1] + inner[3]) / 2))))
    bounds = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)
    hansen = read_hansen_window(bounds)
    loss = hansen.arrays["lossyear"]
    tree = hansen.arrays["treecover2000"]
    datamask = hansen.arrays["datamask"]
    prior = (loss >= 1) & (loss <= 20)
    base = (datamask == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior
    if not base.any():
        return 0
    if not prior.any():
        return int(base.sum())
    centre_lat = (bounds[1] + bounds[3]) / 2
    _, _, x_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c + abs(hansen.transform.a), centre_lat)
    _, _, y_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c, centre_lat + abs(hansen.transform.e))
    distance = distance_transform_edt(~prior, sampling=(abs(y_size), abs(x_size)))
    qualifies = base & (distance >= 1920.0)
    rows, cols = np.indices(qualifies.shape)
    xs = hansen.transform.c + (cols + 0.5) * hansen.transform.a
    ys = hansen.transform.f + (rows + 0.5) * hansen.transform.e
    inside = (xs >= inner[0]) & (xs <= inner[2]) & (ys >= inner[1]) & (ys <= inner[3])
    return int((qualifies & inside).sum())


print(f"Walking each stratum's pre-drawn queue in rank order (first {PER_STRATUM} unselected).")
print(f"Locked reading A; floor {MIN_PIF_PIXELS} px. Separation check NOT applied -> upper bound.\n")
for group, entries in sorted(by_group.items()):
    queue = [r for r in entries if r["selected"] != "1"][:PER_STRATUM]
    depth = sum(1 for r in entries if r["selected"] != "1")
    passes = 0
    tested = 0
    print(f"--- {group} (queue depth {depth}) ---")
    for r in queue:
        try:
            n = pif_count(float(r["lon"]), float(r["lat"]))
        except Exception as exc:
            print(f"  rank {r['rank']:>4} {r['candidate_id']:<26} ERROR {type(exc).__name__}")
            continue
        tested += 1
        ok = n >= MIN_PIF_PIXELS
        passes += ok
        print(f"  rank {r['rank']:>4} {r['candidate_id']:<26} pif={n:>8}  {'PASS' if ok else 'fail'}")
    rate = passes / tested if tested else 0.0
    print(f"  {group}: {passes}/{tested} pass ({rate:.0%}) "
          f"{'-- can refill 3 slots' if passes >= 3 else '-- CANNOT refill 3 slots from this sample'}\n")
    sys.stdout.flush()
