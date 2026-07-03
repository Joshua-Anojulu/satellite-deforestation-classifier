"""
Download RGB + NIR (B04,B03,B02,B08) Sentinel-2 L2A median composites for all
study areas in deforestation/sites.py, 2016 and 2024 dry seasons, from the
Copernicus Data Space Ecosystem via openEO.

RGB feeds the (proven) classifier pipeline; the NIR band feeds the NDVI-difference
baseline. Reuses the saved openEO refresh token (no re-login if still valid).

Run:  python -m deforestation.download_sites            # all sites
      python -m deforestation.download_sites rondonia   # one site
"""
import os
import sys
import time

from deforestation.sites import SITES

OUT_DIR = r"C:\Users\josha\ml-data\deforestation\sites"
BANDS = ["B04", "B03", "B02", "B08"]   # red, green, blue, NIR
PERIOD_A = ("2016-06-01", "2016-09-30")
PERIOD_B = ("2024-06-01", "2024-09-30")
MAX_CLOUD = 25


def download(only=None):
    import openeo
    os.makedirs(OUT_DIR, exist_ok=True)
    con = openeo.connect("openeo.dataspace.copernicus.eu").authenticate_oidc()
    print("Authenticated.\n")

    keys = [only] if only else list(SITES)
    for key in keys:
        bbox = SITES[key]["bbox"]
        for period, tag in [(PERIOD_A, "2016"), (PERIOD_B, "2024")]:
            out = os.path.join(OUT_DIR, f"{key}_{tag}.tif")
            if os.path.exists(out) and os.path.getsize(out) > 0:
                print(f"skip (exists): {out}"); continue
            cube = con.load_collection(
                "SENTINEL2_L2A", spatial_extent=bbox, temporal_extent=list(period),
                bands=BANDS, max_cloud_cover=MAX_CLOUD)
            result = cube.reduce_dimension(dimension="t", reducer="median")
            for attempt in range(1, 5):  # retry transient 5xx errors
                try:
                    result.download(out)
                    print(f"downloaded {out}  ({key}, {tag})", flush=True)
                    break
                except Exception as e:
                    print(f"  attempt {attempt} failed for {key} {tag}: {str(e)[:80]}", flush=True)
                    if os.path.exists(out) and os.path.getsize(out) == 0:
                        os.remove(out)
                    if attempt == 4:
                        print(f"  GAVE UP on {key} {tag}", flush=True)
                    else:
                        time.sleep(15 * attempt)
    print("\nALL_SITE_DOWNLOADS_DONE")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else None)
