"""Census: can the locked PIF criterion be satisfied at each cohort site?

Read-only. Touches no locked parameter and writes nothing into the study tree.

The binding conjunct is the >=1,920 m distance-to-prior-loss rule, which needs only
Hansen (lossyear/treecover2000/datamask) over the buffered extent -- no reflectance.
The clear-observation conjunct is effectively non-binding (measured ~100% of pixels
pass at rondonia), so this is an UPPER BOUND on the PIF count: a site failing here
cannot pass with the clear criterion applied.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from pyproj import Geod

from risk.config import MIN_PIF_PIXELS, PIF_TREECOVER_THRESHOLD
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
geod = Geod(ellps="WGS84")

print(f"{'site':<28} {'stratum':<14} {'base':>9} {'maxdist':>9} {'>=1920':>8}  verdict")
print("-" * 86)
rows = []
for site in manifest["sites"]:
    site_id = str(site["candidate_id"])
    bbox = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    bounds = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    try:
        hansen = read_hansen_window(bounds)
    except Exception as exc:
        print(f"{site_id:<28} {'?':<14} {'ERR':>9} {type(exc).__name__}")
        continue
    loss = hansen.arrays["lossyear"]
    tree = hansen.arrays["treecover2000"]
    datamask = hansen.arrays["datamask"]
    prior = (loss >= 1) & (loss <= 20)
    base = (datamask == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior

    centre_lat = (bounds[1] + bounds[3]) / 2
    _, _, x_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c + abs(hansen.transform.a), centre_lat)
    _, _, y_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c, centre_lat + abs(hansen.transform.e))
    if not prior.any():
        maxdist, n_pif = float("inf"), int(base.sum())
    else:
        distance = distance_transform_edt(~prior, sampling=(abs(y_size), abs(x_size)))
        maxdist = float(distance[base].max()) if base.any() else 0.0
        n_pif = int((base & (distance >= 1920.0)).sum())
    verdict = "PASS" if n_pif >= MIN_PIF_PIXELS else "FAIL(PIF)"
    rows.append((site_id, n_pif, verdict))
    print(f"{site_id:<28} {str(site.get('group','')):<14} {int(base.sum()):>9} "
          f"{maxdist:>9.0f} {n_pif:>8}  {verdict}")

passed = [r for r in rows if r[2] == "PASS"]
print("-" * 86)
print(f"sites reaching PIF floor ({MIN_PIF_PIXELS}): {len(passed)} / {len(rows)}")
print(f"cohort floor is 14; frame cohort needs 12/12")
