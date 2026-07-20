"""Integrity check for every downloaded composite. Existence != readability.

`download_timeseries._download` skips files that already exist, so a truncated or corrupt
GeoTIFF is silently retained and never re-fetched, and every "N/N complete" count based on
file existence (including the drive_sites.ps1 logs and this session's own progress checks)
will report it as done. Discovered when a cohort-wide read hit:

    2019_reflectance.tif, band 3: IReadBlock failed at X offset 7, Y offset 14:
    TIFFReadEncodedTile() failed.

This fully reads every band of every composite and reports which files cannot be decoded.
Read-only. Deletes nothing: a corrupt file is reported, and re-downloading it is a separate,
deliberate act (the file is evidence until then).
"""
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\josha\ml-data\deforestation-risk\composites")

tifs = sorted(ROOT.glob("*/*.tif"))
print(f"checking {len(tifs)} GeoTIFFs under {ROOT}\n")

bad, nan_only, ok = [], [], 0
for path in tifs:
    rel = f"{path.parent.name}/{path.name}"
    try:
        with rasterio.open(path) as src:
            for b in range(1, src.count + 1):
                arr = src.read(b)          # full read — this is what catches tile corruption
                if b == 1 and src.count >= 1:
                    finite = np.isfinite(arr.astype(np.float64)).sum() if arr.dtype.kind == "f" else arr.size
                    if finite == 0:
                        nan_only.append(rel)
        ok += 1
    except Exception as exc:
        bad.append((rel, f"{type(exc).__name__}: {str(exc)[:110]}"))
        print(f"CORRUPT  {rel}\n         {type(exc).__name__}: {str(exc)[:110]}", flush=True)

print("\n" + "=" * 78)
print(f"readable : {ok}/{len(tifs)}")
print(f"corrupt  : {len(bad)}")
for rel, err in bad:
    print(f"   {rel}  <- {err}")
if nan_only:
    print(f"all-nodata band 1 ({len(nan_only)}):")
    for rel in nan_only:
        print(f"   {rel}")
print("=" * 78)
if bad:
    sites = sorted({rel.split('/')[0] for rel, _ in bad})
    print(f"\naffected sites ({len(sites)}): {', '.join(sites)}")
    print("\nRe-download: delete ONLY the corrupt files, then re-run the site through")
    print("risk.download_timeseries — _download skips what exists, so the rest is untouched.")
    print("Do NOT trust an existence-based N/N count again; use this check.")
