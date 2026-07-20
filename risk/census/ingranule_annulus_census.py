"""Do PIF-eligible targets exist OUTSIDE the 4 km box but near enough to share the S2 granule?

Codex review of the identifiability draft, finding #5: "the analysis box is not the sensor scene."
The distant-reference route was rejected on same-scene transport grounds, but that argument was
calibrated to a ~60 km patch possibly in a DIFFERENT granule. A Sentinel-2 granule is ~110 km, so a
reference annulus a few km outside the buffered box can share acquisition time, platform and much of
the atmosphere. That escape was never tested, and it decides whether the study is dead.

This applies the LOCKED PIF criterion (datamask==1, treecover2000 >= 70, no 2001-2020 loss,
>= 1,920 m from ANY 2001-2020 loss pixel, floor 5,000 px) to concentric annuli measured outward from
the buffered box edge, and reports the smallest radius at which the floor is reached.

Distances use the full outer window, so the 1,920 m transform is naturally haloed. Read-only, Hansen
only. Uses ONLY <=2020 Hansen fields (lossyear 1..20, treecover2000, datamask) -- unlike the study's
`eligible30`, this census never reads post-2020 loss codes.
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

RINGS_KM = (5, 10, 20, 30, 50)
OUTER_KM = 50.0
geod = Geod(ellps="WGS84")
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

print("PIF-eligible pixels in annuli OUTSIDE the buffered box (locked criterion, floor 5,000).")
print("S2 granule ~110 km, so rings <= ~30 km are plausibly same-granule.\n")
print(f"{'site':<26}" + "".join(f"{f'<={r}km':>11}" for r in RINGS_KM) + f"{'floor at':>10}")
print("-" * 96)

rows = []
for site in manifest["sites"]:
    sid = str(site["candidate_id"])
    bb = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    inner = (bb["west"], bb["south"], bb["east"], bb["north"])
    mid_lat = (inner[1] + inner[3]) / 2
    dlat = (OUTER_KM * 1000.0) / 110_574.0
    dlon = (OUTER_KM * 1000.0) / (111_320.0 * max(0.05, np.cos(np.radians(mid_lat))))
    outer = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)

    try:
        h = read_hansen_window(outer)
    except Exception as exc:
        print(f"{sid:<26} ERROR {type(exc).__name__}")
        continue

    loss, tree, dm = h.arrays["lossyear"], h.arrays["treecover2000"], h.arrays["datamask"]
    prior = (loss >= 1) & (loss <= 20)
    base = (dm == 1) & (tree >= PIF_TREECOVER_THRESHOLD) & ~prior

    _, _, x_size = geod.inv(h.transform.c, mid_lat, h.transform.c + abs(h.transform.a), mid_lat)
    _, _, y_size = geod.inv(h.transform.c, mid_lat, h.transform.c, mid_lat + abs(h.transform.e))
    dist_loss = (distance_transform_edt(~prior, sampling=(abs(y_size), abs(x_size)))
                 if prior.any() else np.full(prior.shape, np.inf))
    pif = base & (dist_loss >= 1920.0)

    rows_i, cols_i = np.indices(pif.shape)
    xs = h.transform.c + (cols_i + 0.5) * h.transform.a
    ys = h.transform.f + (rows_i + 0.5) * h.transform.e
    # Metric distance from the buffered box edge (0 inside the box).
    dx_deg = np.maximum(0.0, np.maximum(inner[0] - xs, xs - inner[2]))
    dy_deg = np.maximum(0.0, np.maximum(inner[1] - ys, ys - inner[3]))
    dx_m = dx_deg * 111_320.0 * np.cos(np.radians(mid_lat))
    dy_m = dy_deg * 110_574.0
    dist_box = np.sqrt(dx_m ** 2 + dy_m ** 2)
    outside = dist_box > 0

    counts, floor_at = [], None
    for r in RINGS_KM:
        n = int((pif & outside & (dist_box <= r * 1000.0)).sum())
        counts.append(n)
        if floor_at is None and n >= MIN_PIF_PIXELS:
            floor_at = r
    rows.append((sid, counts, floor_at))
    print(f"{sid:<26}" + "".join(f"{c:>11,}" for c in counts) +
          f"{(str(floor_at) + ' km') if floor_at else 'NONE':>10}")
    sys.stdout.flush()

print("-" * 96)
for i, r in enumerate(RINGS_KM):
    n = sum(1 for _, c, _ in rows if c[i] >= MIN_PIF_PIXELS)
    print(f"  sites reaching the 5,000 floor within {r:>2} km of the box: {n}/{len(rows)}")
same = sum(1 for _, _, f in rows if f is not None and f <= 30)
print(f"\nsites with a PIF population within ~30 km (plausibly same-granule): {same}/{len(rows)}")
print("If this is high, the obstruction is NOT general -- it is a property of the 4 km box, and a")
print("same-granule reference annulus is a live design. If low, the escape is closed empirically.")
print("\nCAVEAT: proximity does not prove same-granule. Confirm MGRS tile membership per site before")
print("relying on shared acquisition; a box near a granule edge may have its annulus split across")
print("tiles with different acquisition dates.")
