"""Is a PIF annulus covered by the SAME Sentinel-2 acquisitions as the box?

Proximity is not granule membership. The annulus is only defensible as a reference if it shares
acquisitions with the target -- same overpass, same platform, essentially the same atmosphere. This
tests that directly rather than by MGRS naming:

  1. locate the NEAREST PIF-eligible pixel outside the buffered box (locked criterion, Hansen only);
  2. ask the CDSE catalogue which S2 L2A products cover that point in the site's frozen 2020 window;
  3. intersect those product UUIDs with the ones PROVENANCE records as actual contributors to the
     site's own 2020 composite.

Shared UUIDs == shared acquisitions. A high share means the annulus is genuinely same-scene; a low
share means it is a different granule wearing a nearby postcode, and the same-scene argument that
justifies the annulus fails.

Read-only: catalogue metadata only, no imagery. Hansen fields used are <=2020 only.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from pyproj import Geod

from risk.config import PIF_TREECOVER_THRESHOLD
from risk.download_timeseries import buffered_bbox
from risk.hansen import read_hansen_window

OUTER_KM = 30.0
COMPOSITES = Path(r"C:\Users\josha\ml-data\deforestation-risk\composites")
ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter="
geod = Geod(ellps="WGS84")


def products_at(lon, lat, start, end):
    q = ("Collection/Name eq 'SENTINEL-2' and "
         f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon:.5f} {lat:.5f})') and "
         f"ContentDate/Start gt {start}T00:00:00.000Z and ContentDate/Start lt {end}T23:59:59.999Z")
    url = ODATA + urllib.parse.quote(q) + "&$top=1000&$select=Id,Name"
    with urllib.request.urlopen(url, timeout=120) as r:
        vals = json.load(r).get("value", [])
    return {p["Id"]: p["Name"] for p in vals if "MSIL2A" in p["Name"]}


def tiles(names):
    out = set()
    for n in names:
        for part in n.split("_"):
            if len(part) == 6 and part.startswith("T") and part[1:3].isdigit():
                out.add(part)
    return out


manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None

print(f"{'site':<26}{'annulus km':>11}{'ctr pts':>9}{'ann pts':>9}{'shared':>8}{'share':>8}{'contrib':>9}  tiles ctr / annulus")
print("-" * 112)
for site in manifest["sites"]:
    sid = str(site["candidate_id"])
    if only and sid not in only:
        continue
    prov_path = COMPOSITES / sid / "2020_provenance.json"
    if not prov_path.exists():
        continue
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    box_ids = set(prov["acquisition_metadata"]["product_ids"])
    start, end = prov["period"]

    bb = buffered_bbox({k: site[k] for k in ("west", "south", "east", "north")})
    inner = (bb["west"], bb["south"], bb["east"], bb["north"])
    mid_lat = (inner[1] + inner[3]) / 2
    dlat = (OUTER_KM * 1000.0) / 110_574.0
    dlon = (OUTER_KM * 1000.0) / (111_320.0 * max(0.05, np.cos(np.radians(mid_lat))))
    outer = (inner[0] - dlon, inner[1] - dlat, inner[2] + dlon, inner[3] + dlat)

    h = read_hansen_window(outer)
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
    dx = np.maximum(0.0, np.maximum(inner[0] - xs, xs - inner[2])) * 111_320.0 * np.cos(np.radians(mid_lat))
    dy = np.maximum(0.0, np.maximum(inner[1] - ys, ys - inner[3])) * 110_574.0
    dbox = np.sqrt(dx ** 2 + dy ** 2)
    cand = pif & (dbox > 0)
    if not cand.any():
        print(f"{sid:<26}{'no PIF <=30km':>11}")
        continue
    flat = np.argmin(np.where(cand, dbox, np.inf))
    r, c = np.unravel_index(flat, dbox.shape)
    a_lon, a_lat = float(xs[r, c]), float(ys[r, c])
    a_km = float(dbox[r, c]) / 1000.0

    try:
        a_prod = products_at(a_lon, a_lat, start, end)
        b_prod = products_at((inner[0] + inner[2]) / 2, mid_lat, start, end)
    except Exception as exc:
        print(f"{sid:<26}{a_km:>11.1f}  catalogue ERROR {type(exc).__name__}")
        continue

    # POINT-vs-POINT is the valid comparison. Comparing a point's coverage against the box's whole
    # contributor set is invalid: a ~36 km box intersects products from several orbits/tiles, so no
    # single point inside it is covered by all of them.
    pt_shared = set(a_prod) & set(b_prod)
    pt_share = len(pt_shared) / len(b_prod) if b_prod else 0.0
    contrib = box_ids & set(a_prod)   # of the composite's ACTUAL contributors, how many reach the annulus
    print(f"{sid:<26}{a_km:>11.1f}{len(b_prod):>9}{len(a_prod):>9}{len(pt_shared):>8}{pt_share:>8.0%}"
          f"{len(contrib):>9}  {','.join(sorted(tiles(b_prod.values()))) or '?'} / "
          f"{','.join(sorted(tiles(a_prod.values()))) or '?'}")
    sys.stdout.flush()

print("-" * 104)
print("share = |products(annulus point) & products(box CENTRE point)| / |products(box centre)| —")
print("point vs point, the only valid comparison. High => the annulus sees the same overpasses as the")
print("box interior itself: same platform, essentially the same atmosphere, so it is a defensible")
print("same-scene reference. Low => a different granule wearing a nearby postcode.")
print("contrib = how many of the composite's ACTUAL contributing products also reach the annulus")
print("(informative, but not a share: the box is a polygon, the annulus a point).")
