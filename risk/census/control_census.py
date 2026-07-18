"""D2.2 pre-approval control census — the feasibility question Codex round 4 says is unanswered.

Does every frozen site have BOTH control classes in enough fixed 640 m blocks?
  (a) vegetation: Hansen datamask==1 & treecover2000 >= 70 & no 2001-2020 loss  (NO distance rule)
  (b) water:      Hansen datamask==2 (permanent water)

Label-blind (<=2020 categorical Hansen only), read-only, no imagery, no locked parameter touched.
Control masks are time-invariant by construction (treecover2000, loss<=2020, datamask), which is
what round-3 finding #2 demands: identical pixels in all three years.

Reports raw pixels AND effective 640 m blocks at several occupancy thresholds. Thresholds are
reported as a SPECTRUM precisely so the floor is not chosen to fit the answer -- the floor must be
locked from a power/equivalence calculation, not from this table.
"""
import json
import sys
from pathlib import Path

import numpy as np
from pyproj import Geod

from risk.config import PIF_TREECOVER_THRESHOLD, CELL_SIZE_M
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

geod = Geod(ellps="WGS84")
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))


def blocks_with(mask, block_px, min_px):
    """Count aligned CELL_SIZE_M blocks holding >= min_px control pixels."""
    h, w = mask.shape
    bh, bw = block_px
    nh, nw = h // bh, w // bw
    if nh == 0 or nw == 0:
        return 0
    trimmed = mask[: nh * bh, : nw * bw]
    counts = trimmed.reshape(nh, bh, nw, bw).sum(axis=(1, 3))
    return int((counts >= min_px).sum())


print(f"D2.2 control census — fixed 640 m blocks. vegetation = tree>=%d, no 2001-2020 loss; "
      f"water = datamask==2\n" % PIF_TREECOVER_THRESHOLD)
print(f"{'site':<26}{'veg px':>10}{'vegB>=1':>9}{'vegB>=53':>9}{'wat px':>10}{'watB>=1':>9}{'watB>=53':>9}  both?")
print("-" * 96)
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
    veg = (datamask == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior
    water = datamask == 2

    centre_lat = (bounds[1] + bounds[3]) / 2
    _, _, x_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c + abs(hansen.transform.a), centre_lat)
    _, _, y_size = geod.inv(hansen.transform.c, centre_lat,
                            hansen.transform.c, centre_lat + abs(hansen.transform.e))
    block_px = (max(1, int(round(CELL_SIZE_M / abs(y_size)))),
                max(1, int(round(CELL_SIZE_M / abs(x_size)))))

    r = dict(
        site=site_id, group=str(site.get("group", "")),
        veg_px=int(veg.sum()),
        veg_b1=blocks_with(veg, block_px, 1),
        veg_b53=blocks_with(veg, block_px, 53),
        wat_px=int(water.sum()),
        wat_b1=blocks_with(water, block_px, 1),
        wat_b53=blocks_with(water, block_px, 53),
    )
    rows.append(r)
    both = "YES" if (r["veg_b53"] > 0 and r["wat_b53"] > 0) else "*** NO ***"
    print(f"{r['site']:<26}{r['veg_px']:>10}{r['veg_b1']:>9}{r['veg_b53']:>9}"
          f"{r['wat_px']:>10}{r['wat_b1']:>9}{r['wat_b53']:>9}  {both}")
    sys.stdout.flush()

print("-" * 96)
for thresh in ("b1", "b53"):
    n_both = sum(1 for r in rows if r[f"veg_{thresh}"] > 0 and r[f"wat_{thresh}"] > 0)
    n_veg = sum(1 for r in rows if r[f"veg_{thresh}"] > 0)
    n_wat = sum(1 for r in rows if r[f"wat_{thresh}"] > 0)
    print(f"blocks>= {'1' if thresh=='b1' else '53'} px: vegetation {n_veg}/19 sites, "
          f"water {n_wat}/19 sites, BOTH {n_both}/19")
print("\nD2.7: a shortfall at ANY frozen site makes the whole headline INCONCLUSIVE "
      "(sites are never excluded).")
