"""
Acquire two-date Sentinel-2 true-color imagery for a study area from the
Copernicus Data Space Ecosystem (CDSE) -- the CURRENT service that replaced the
retired scihub.copernicus.eu (shut down 2023).

There are three practical paths; this file documents all three and implements
the openEO one (most reproducible for a paper). You need a free CDSE account:
    https://dataspace.copernicus.eu/

--------------------------------------------------------------------------
PATH A (recommended, scripted): openEO
    pip install openeo
    Then fill in BBOX and the two date ranges below and run this file.
    It requests a cloud-masked, least-cloudy true-color (B04,B03,B02) composite
    per period and downloads a GeoTIFF for each -> feed to patchify.py.

PATH B (point-and-click): Copernicus Browser
    https://browser.dataspace.copernicus.eu/  -> draw your area, pick two dates
    with low cloud cover, export the True Color GeoTIFF. Simplest, no code.

PATH C: Google Earth Engine (earthengine.google.com)
    Good if you already use GEE; export a Sentinel-2 SR true-color composite.
--------------------------------------------------------------------------

Fill these in for your chosen study area before running Path A.
"""
import os

# === STUDY AREA (pinned candidates) ========================================
# Each box is ~20-25 km on a side, sitting on an ACTIVE deforestation frontier
# with heavy 2016->2024 forest loss (so the two-date change signal is strong)
# and dense Global Forest Watch coverage (so validation works).
#
# >>> Confirm the red "Tree cover loss" on https://www.globalforestwatch.org/map
#     for your chosen box and nudge the edges onto the active frontier. <<<

STUDY_AREAS = {
    # CLASSIC Amazon "fishbone" clearing near Ariquemes/Machadinho, Rondonia, BR.
    "rondonia": {"west": -63.10, "south": -10.00, "east": -62.85, "north": -9.78},
    # Sao Felix do Xingu, Para, BR - one of the highest-deforestation municipalities,
    # very active recent loss (cattle frontier).
    "sao_felix_xingu": {"west": -52.10, "south": -6.70, "east": -51.85, "north": -6.48},
    # Gran Chaco near Filadelfia, Paraguay - large clean rectangular clearings.
    "gran_chaco": {"west": -60.10, "south": -22.20, "east": -59.85, "north": -21.98},
}

# Active selection: change this one key to switch study area.
STUDY_AREA = "sao_felix_xingu"
BBOX = STUDY_AREAS[STUDY_AREA]

# Same (dry) season both years avoids false change from crop/leaf phenology.
# Wider A->B gap = more accumulated clearing = stronger signal.
PERIOD_A = ("2016-06-01", "2016-09-30")   # earlier date range
PERIOD_B = ("2024-06-01", "2024-09-30")   # later date range
OUT_DIR = r"C:\Users\josha\ml-data\deforestation"   # outside OneDrive
OUT_A = os.path.join(OUT_DIR, f"sentinel_{STUDY_AREA}_A.tif")
OUT_B = os.path.join(OUT_DIR, f"sentinel_{STUDY_AREA}_B.tif")
MAX_CLOUD = 20  # percent
# ===========================================================================


def download_openeo():
    import openeo  # imported lazily so the file can be read without the dep

    if BBOX["west"] is None:
        raise SystemExit("Set BBOX (and dates) at the top of this file first.")

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Study area: {STUDY_AREA}  BBOX={BBOX}")
    print("Connecting to Copernicus Data Space (openEO)...")
    print(">>> A login URL + code will appear below. Open it, sign in, approve. <<<\n")
    con = openeo.connect("openeo.dataspace.copernicus.eu").authenticate_oidc()
    print("Authenticated. Building + downloading composites (a few minutes each)...\n")

    def truecolor(period, out):
        cube = con.load_collection(
            "SENTINEL2_L2A",
            spatial_extent=BBOX,
            temporal_extent=list(period),
            bands=["B04", "B03", "B02"],
            max_cloud_cover=MAX_CLOUD,
        )
        # Median composite over the period reduces clouds/gaps.
        composite = cube.reduce_dimension(dimension="t", reducer="median")
        composite.download(out)
        print(f"Downloaded {out} for {period}")

    truecolor(PERIOD_A, OUT_A)
    truecolor(PERIOD_B, OUT_B)
    print("\nNext: python deforestation/patchify.py <tif> <out.npz>")


if __name__ == "__main__":
    download_openeo()
