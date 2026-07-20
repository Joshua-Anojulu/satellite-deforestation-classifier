"""Halo-corrected distance distribution for one site. Verifies the figures cited in the draft.

The originally-quoted stats (median 168 m, max-in-forest 1,561 m, max-anywhere 2,006 m) were
computed WITHOUT the Hansen halo -- i.e. with the very edge bias the draft documents. Distances
can only shrink when surrounding loss becomes visible, so those were upper-biased. This recomputes
them correctly. Read-only, Hansen only, <=2020.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from pyproj import Geod

from risk.config import PIF_TREECOVER_THRESHOLD
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

site_id = sys.argv[2]
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
site = next(s for s in manifest["sites"] if s["candidate_id"] == site_id)

bbox = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
inner = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
halo = 1980.0
dlat = halo / 110_574.0
dlon = halo / (111_320.0 * max(0.05, np.cos(np.radians((inner[1] + inner[3]) / 2))))
outer = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)

geod = Geod(ellps="WGS84")
for label, bounds in (("NO HALO (biased, as originally quoted)", inner), ("HALO (correct)", outer)):
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
    distance = distance_transform_edt(~prior, sampling=(abs(y_size), abs(x_size)))

    rows, cols = np.indices(distance.shape)
    xs = hansen.transform.c + (cols + 0.5) * hansen.transform.a
    ys = hansen.transform.f + (rows + 0.5) * hansen.transform.e
    inside = (xs >= inner[0]) & (xs <= inner[2]) & (ys >= inner[1]) & (ys <= inner[3])
    sel = base & inside

    print(f"\n--- {site_id}: {label} ---")
    print(f"  intact forest px inside extent : {int(sel.sum())}")
    print(f"  median distance -> nearest loss : {np.median(distance[sel]):.0f} m")
    print(f"  p90 / p99                       : {np.percentile(distance[sel], 90):.0f} / "
          f"{np.percentile(distance[sel], 99):.0f} m")
    print(f"  farthest FOREST pixel           : {distance[sel].max():.0f} m")
    print(f"  farthest ANY pixel in extent    : {distance[inside].max():.0f} m")
    print(f"  PIF px (>=1920 m, floor 5000)   : {int((sel & (distance >= 1920.0)).sum())}")
