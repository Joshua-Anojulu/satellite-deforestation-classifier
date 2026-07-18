"""Empirical backing for the identifiability obstruction. Two measurements, cohort-wide.

PART 1 — IQR motion fabricates history (measures the corollary, does not assume it).
  Within-site standardization is z_it = (x_it - m_t)/IQR_t. For a cell whose RAW condition never
  changes (x_it = x_i), dz_i = x_i*(1/IQR_20 - 1/IQR_18) + const: a spurious trend proportional to
  static condition, appearing whenever the site scale moves. This measures the REAL m_t/IQR_t of
  each site-year over a FIXED support and reports the spurious dz an unchanged cell acquires.

PART 2 — the offset residual, cohort-wide and in CONSISTENT UNITS (discharges Codex r1#9/#10).
  The earlier test compared a raw index change (index units) against a standardized residual
  (z units) and concluded "no better than raw" — dimensionally invalid. Here BOTH are expressed in
  baseline-IQR units, across every site and index.

Support is the fixed three-year intersection: eligible30 AND finite in all three years (Codex r1#7 —
"fixed support" must mean fixed OBSERVED support). Label-blind (<=2020), read-only, no downloads.
"""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds

from risk.config import REFLECTANCE_BANDS, BOA_QUANTIFICATION_VALUE, FEATURE_YEARS
from risk.features import spectral_indices
from risk.hansen import read_hansen_window, eligible_mask_to_master

OFFSET = 0.005          # realistic L2A atmospheric-correction offset, reflectance units
DIFF_GAIN = 0.02        # differential NIR/RED gain
ROOT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"C:\Users\josha\ml-data\deforestation-risk\composites")
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
band_names = tuple(REFLECTANCE_BANDS)
INDICES = ("ndvi", "ndmi", "nbr")


def load(site_id, year):
    with rasterio.open(ROOT / site_id / f"{year}_reflectance.tif") as src:
        arr = src.read().astype(np.float32)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        return arr / BOA_QUANTIFICATION_VALUE, str(src.crs), src.transform, (src.height, src.width), src.bounds


part1, part2 = [], []
for site in manifest["sites"]:
    sid = str(site["candidate_id"])
    try:
        refl, crs, tr, shape, bounds = load(sid, 2020)
    except Exception as exc:
        print(f"{sid}: SKIP ({type(exc).__name__})", flush=True)
        continue

    hb = transform_bounds(crs, "EPSG:4326", *bounds, densify_pts=21)
    h = read_hansen_window(hb)
    el30 = (h.arrays["datamask"] == 1) & (h.arrays["treecover2000"] >= 30) & \
           ((h.arrays["lossyear"] == 0) | (h.arrays["lossyear"] >= 21))
    support = eligible_mask_to_master(el30, h.transform, h.crs, shape, tr, crs)

    idx_by_year, ok = {}, support.copy()
    for year in FEATURE_YEARS:
        r = refl if year == 2020 else load(sid, year)[0]
        idx_by_year[year] = spectral_indices(r, band_names)
        for name in INDICES:
            ok &= np.isfinite(idx_by_year[year][name])
        if year != 2020:
            del r
    if ok.sum() < 10_000:
        print(f"{sid}: SKIP (fixed 3-year support only {int(ok.sum())} px)", flush=True)
        continue

    # ---- PART 1 ----
    for name in INDICES:
        stats = {}
        for year in FEATURE_YEARS:
            v = idx_by_year[year][name][ok]
            stats[year] = (float(np.median(v)),
                           float(np.percentile(v, 75) - np.percentile(v, 25)))
        m18, i18 = stats[FEATURE_YEARS[0]]
        m20, i20 = stats[FEATURE_YEARS[-1]]
        if i18 <= 0 or i20 <= 0:
            continue
        # A cell whose RAW value never changed, sitting at z=+1 and z=-1 in the final year.
        row = dict(site=sid, index=name, iqr18=i18, iqr20=i20,
                   iqr_change_pct=100.0 * (i20 - i18) / i18)
        for z_ref in (1.0, -1.0):
            x = m20 + z_ref * i20              # its constant raw value
            row[f"dz_at_{'p1' if z_ref > 0 else 'm1'}"] = float(z_ref - (x - m18) / i18)
        part1.append(row)

    # ---- PART 2 ----
    base = idx_by_year[2020]
    drift = refl + OFFSET
    nir, red = band_names.index("B08"), band_names.index("B04")
    drift[nir] *= (1.0 + DIFF_GAIN)
    drift[red] *= (1.0 - DIFF_GAIN)
    dref = spectral_indices(drift, band_names)
    for name in INDICES:
        a, b = base[name], dref[name]
        ref = a[ok]
        iqr = float(np.percentile(ref, 75) - np.percentile(ref, 25))
        if iqr <= 0:
            continue
        raw_in_iqr = np.abs(b - a)[ok] / iqr                       # raw change, IQR units
        za = (a - np.median(ref)) / iqr
        refb = b[ok]
        zb = (b - np.median(refb)) / float(np.percentile(refb, 75) - np.percentile(refb, 25))
        std_in_iqr = np.abs(zb - za)[ok]                           # standardized residual, z == IQR units
        part2.append(dict(site=sid, index=name,
                          raw_med=float(np.median(raw_in_iqr)), raw_p95=float(np.percentile(raw_in_iqr, 95)),
                          std_med=float(np.median(std_in_iqr)), std_p95=float(np.percentile(std_in_iqr, 95))))
    print(f"{sid}: done ({int(ok.sum()):,} fixed-support px)", flush=True)
    del refl, drift, idx_by_year

print("\n" + "=" * 92)
print("PART 1 — real site-scale motion, and the spurious trend it gives an UNCHANGED cell")
print("=" * 92)
print(f"{'index':<7}{'sites':>7}{'|IQR change| med':>18}{'max':>10}{'dz@z=+1 med':>14}{'dz@z=+1 p90':>14}")
print("-" * 92)
for name in INDICES:
    rows = [r for r in part1 if r["index"] == name]
    if not rows:
        continue
    ch = np.abs([r["iqr_change_pct"] for r in rows])
    dz = np.abs([r["dz_at_p1"] for r in rows])
    print(f"{name:<7}{len(rows):>7}{np.median(ch):>17.1f}%{np.max(ch):>9.1f}%"
          f"{np.median(dz):>14.3f}{np.percentile(dz, 90):>14.3f}")
print("\ndz@z=+1 is the trend, in z units, that a cell with CONSTANT raw condition acquires between")
print("the first and last feature year purely because the site's median/IQR moved. It is what block D")
print("would read as 'condition history' for a cell that never changed.")

print("\n" + "=" * 92)
print(f"PART 2 — offset {OFFSET} + differential gain {DIFF_GAIN}: both effects in BASELINE-IQR UNITS")
print("=" * 92)
print(f"{'index':<7}{'sites':>7}{'RAW med':>11}{'RAW p95':>11}{'STD med':>11}{'STD p95':>11}   standardization helps?")
print("-" * 92)
for name in INDICES:
    rows = [r for r in part2 if r["index"] == name]
    if not rows:
        continue
    rm, rp = np.median([r["raw_med"] for r in rows]), np.median([r["raw_p95"] for r in rows])
    sm, sp = np.median([r["std_med"] for r in rows]), np.median([r["std_p95"] for r in rows])
    verdict = "YES" if sm < rm else ("no — WORSE" if sm > rm * 1.05 else "no material change")
    print(f"{name:<7}{len(rows):>7}{rm:>11.4f}{rp:>11.4f}{sm:>11.4f}{sp:>11.4f}   {verdict}")
print("\nBoth columns are now in the same units (multiples of the baseline IQR), so they are")
print("directly comparable — the earlier index-units vs z-units comparison was invalid.")
