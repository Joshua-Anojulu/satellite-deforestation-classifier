"""Re-run the PIF census with a Hansen halo -- tests Codex review finding #2.

The original census ran distance_transform_edt over the downloaded extent only. The
transform treats the array edge as "no loss beyond", so a forest pixel near the edge
with real clearing just outside is credited with an INFLATED distance and can be
counted as PIF. This re-runs the identical locked reading but reads a >=1,920 m + 1px
Hansen halo around the extent, computes distance on the haloed array, and counts only
pixels inside the original extent.

If the counts drop, finding #2 is confirmed and the earlier census overstated PIF.
Read-only; Hansen only; no locked parameter touched.
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

HALO_M = 1920.0 + 60.0  # the distance rule plus ~2 Hansen pixels of slack
geod = Geod(ellps="WGS84")
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

print(f"{'site':<26}{'no-halo':>10}{'halo':>10}{'delta':>10}   verdict change")
print("-" * 76)
flips = 0
for site in manifest["sites"]:
    site_id = str(site["candidate_id"])
    bbox = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    inner = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])

    dlat = HALO_M / 110_574.0
    mid_lat = (inner[1] + inner[3]) / 2
    dlon = HALO_M / (111_320.0 * max(0.05, np.cos(np.radians(mid_lat))))
    outer = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)

    counts = {}
    for label, bounds in (("nohalo", inner), ("halo", outer)):
        hansen = read_hansen_window(bounds)
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
        if prior.any():
            distance = distance_transform_edt(~prior, sampling=(abs(y_size), abs(x_size)))
        else:
            distance = np.full(prior.shape, np.inf)
        qualifies = base & (distance >= 1920.0)

        if label == "halo":
            # Count only pixels whose centres fall inside the ORIGINAL extent.
            rows, cols = np.indices(qualifies.shape)
            xs = hansen.transform.c + (cols + 0.5) * hansen.transform.a
            ys = hansen.transform.f + (rows + 0.5) * hansen.transform.e
            inside = ((xs >= inner[0]) & (xs <= inner[2]) & (ys >= inner[1]) & (ys <= inner[3]))
            qualifies = qualifies & inside
        counts[label] = int(qualifies.sum())

    a, b = counts["nohalo"], counts["halo"]
    was, now = a >= MIN_PIF_PIXELS, b >= MIN_PIF_PIXELS
    change = "" if was == now else ("*** PASS -> fail ***" if was else "*** fail -> PASS ***")
    flips += was != now
    print(f"{site_id:<26}{a:>10}{b:>10}{b - a:>10}   {change}")
    sys.stdout.flush()

print("-" * 76)
print(f"verdict flips: {flips}")
