"""
Single-site Sentinel-2 download (true-colour RGB) from the Copernicus Data Space
Ecosystem -- the current service, which replaced the retired scihub.copernicus.eu
(shut down 2023).

This is the simple, one-site entry point. The multi-site study uses
`deforestation/download_sites.py`, which fetches RGB **plus NIR** (B08, needed for
the NDVI baseline) for every site. Prefer that one unless you specifically want a
quick single-area RGB pull.

Study-area boxes are imported from `deforestation/sites.py`, which is the single
source of truth. (They used to be duplicated here, and the copies had drifted --
this file's "gran_chaco" was a different rectangle than sites.py's, with a
different cloud threshold, so the two scripts silently downloaded different
imagery for the same name.)

You need a free CDSE account: https://dataspace.copernicus.eu/

Alternatives, if you would rather not script it:
  * Copernicus Browser (https://browser.dataspace.copernicus.eu/) -- draw the area,
    pick two low-cloud dates, export the True Color GeoTIFF.
  * Google Earth Engine -- export a Sentinel-2 SR true-colour composite.

Run:  python -m deforestation.download_sentinel [site_key]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as script OR as -m
from deforestation.sites import SITES

# Same dry season both years, so leaf-on/leaf-off phenology cannot masquerade as
# change. A wide A->B gap accumulates more clearing and strengthens the signal.
PERIOD_A = ("2016-06-01", "2016-09-30")
PERIOD_B = ("2024-06-01", "2024-09-30")
OUT_DIR = r"C:\Users\josha\ml-data\deforestation"   # outside OneDrive
DEFAULT_SITE = "sao_felix_xingu"
MAX_CLOUD = 25   # matches download_sites.py; per-site overrides live in sites.py


def download_openeo(site_key: str = DEFAULT_SITE) -> None:
    import openeo  # imported lazily so the file can be read without the dep

    if site_key not in SITES:
        raise SystemExit(f"Unknown site '{site_key}'. Known: {', '.join(SITES)}")
    bbox = SITES[site_key]["bbox"]
    max_cloud = SITES[site_key].get("max_cloud", MAX_CLOUD)

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Study area: {site_key}  BBOX={bbox}  max_cloud={max_cloud}%")
    print("Connecting to Copernicus Data Space (openEO)...")
    print(">>> A login URL + code will appear below. Open it, sign in, approve. <<<\n")
    con = openeo.connect("openeo.dataspace.copernicus.eu").authenticate_oidc()
    print("Authenticated. Building + downloading composites (a few minutes each)...\n")

    def truecolor(period, out):
        cube = con.load_collection(
            "SENTINEL2_L2A",
            spatial_extent=bbox,
            temporal_extent=list(period),
            bands=["B04", "B03", "B02"],
            max_cloud_cover=max_cloud,
        )
        # Median composite over the period reduces clouds/gaps.
        composite = cube.reduce_dimension(dimension="t", reducer="median")
        composite.download(out)
        print(f"Downloaded {out} for {period}")

    truecolor(PERIOD_A, os.path.join(OUT_DIR, f"sentinel_{site_key}_A.tif"))
    truecolor(PERIOD_B, os.path.join(OUT_DIR, f"sentinel_{site_key}_B.tif"))
    print("\nNext: python -m deforestation.patchify <tif> <out.npz>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Download a two-date RGB pair for one site.")
    ap.add_argument("site", nargs="?", default=DEFAULT_SITE,
                    help=f"Site key from sites.py (default: {DEFAULT_SITE})")
    args = ap.parse_args()
    download_openeo(args.site)
