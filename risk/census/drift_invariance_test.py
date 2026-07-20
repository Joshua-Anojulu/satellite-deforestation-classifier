"""Does within-site standardization actually cancel per-band affine drift?

REFRAME-PLAN.md rests on this claim and currently ASSERTS it. Exact for bands:
  x -> g*x + o  =>  median -> g*median + o, IQR -> g*IQR  =>  z = (x-median)/IQR unchanged.
Indices are nonlinear in the bands (NDVI = (N-R)/(N+R)), so cancellation is only approximate.
This measures the residual on real imagery already on disk.

Method: take a real site-year composite, apply a synthetic per-band affine drift, and compare
    (a) the RAW index change            -- what an unnormalized pipeline would suffer
    (b) the STANDARDIZED index change   -- what the reframe would suffer
over the study's own fixed support (eligible30). Reports median and p95 of |delta| in z units,
so it is directly comparable to a feature-equivalence margin.

Label-blind (<=2020 imagery + Hansen), read-only, no downloads. Not a study result: a property
of the estimator.
"""
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds

from risk.config import REFLECTANCE_BANDS, BOA_QUANTIFICATION_VALUE
from risk.features import spectral_indices
from risk.hansen import read_hansen_window, eligible_mask_to_master

# Realistic Sentinel-2 L2A drift scenarios. Gains/offsets are per band, in reflectance units.
# "uniform" is the benign case; "differential" is the dangerous one -- gain differing BETWEEN the
# bands an index contrasts is exactly what a ratio index cannot cancel.
SCENARIOS = {
    "uniform gain +3%": dict(gain=1.03, offset=0.0, differential=0.0),
    "uniform offset +0.005": dict(gain=1.0, offset=0.005, differential=0.0),
    "differential gain +-2% (NIR vs RED)": dict(gain=1.0, offset=0.0, differential=0.02),
    "combined (gain +3%, offset +0.005, diff 2%)": dict(gain=1.03, offset=0.005, differential=0.02),
}


def zscore(values, support):
    ref = values[support]
    ref = ref[np.isfinite(ref)]
    median = np.median(ref)
    iqr = np.percentile(ref, 75) - np.percentile(ref, 25)
    if iqr <= 0:
        return None
    return (values - median) / iqr


path = Path(sys.argv[1])
with rasterio.open(path) as src:
    raw = src.read().astype(np.float64)
    if src.nodata is not None:
        raw[raw == src.nodata] = np.nan
    master_crs, master_transform, master_shape = str(src.crs), src.transform, (src.height, src.width)
    master_bounds = src.bounds

reflect = raw / BOA_QUANTIFICATION_VALUE
band_names = tuple(REFLECTANCE_BANDS)

hansen_bounds = transform_bounds(master_crs, "EPSG:4326", *master_bounds, densify_pts=21)
h = read_hansen_window(hansen_bounds)
eligible30 = (h.arrays["datamask"] == 1) & (h.arrays["treecover2000"] >= 30) & \
             ((h.arrays["lossyear"] == 0) | (h.arrays["lossyear"] >= 21))
support = eligible_mask_to_master(eligible30, h.transform, h.crs, master_shape,
                                  master_transform, master_crs)
support = support & np.isfinite(reflect).all(axis=0)
print(f"file    : {path.name}")
print(f"support : {int(support.sum()):,} eligible forest pixels of {support.size:,}\n")

base_idx = spectral_indices(reflect, band_names)
nir = band_names.index("B08") if "B08" in band_names else None
red = band_names.index("B04") if "B04" in band_names else None

print(f"{'scenario':<44}{'index':<8}{'RAW |d|':>12}{'Z |d| med':>12}{'Z |d| p95':>12}")
print("-" * 88)
for label, cfg in SCENARIOS.items():
    drifted = reflect * cfg["gain"] + cfg["offset"]
    if cfg["differential"] and nir is not None and red is not None:
        drifted[nir] *= (1.0 + cfg["differential"])
        drifted[red] *= (1.0 - cfg["differential"])
    drift_idx = spectral_indices(drifted, band_names)

    for name in base_idx:
        a, b = base_idx[name], drift_idx[name]
        raw_delta = float(np.nanmedian(np.abs(b - a)[support]))
        za, zb = zscore(a, support), zscore(b, support)
        if za is None or zb is None:
            print(f"{label:<44}{name:<8}{'zero IQR':>12}")
            continue
        dz = np.abs(zb - za)[support]
        dz = dz[np.isfinite(dz)]
        print(f"{label:<44}{name:<8}{raw_delta:>12.4f}{np.median(dz):>12.4f}"
              f"{np.percentile(dz, 95):>12.4f}")
    print()

print("RAW |d|  : median |change| in the index itself (native units) -- an unnormalized pipeline.")
print("Z |d|    : median/p95 |change| in the WITHIN-SITE STANDARDIZED index, in z units.")
print("A pure band z-score would show exactly 0.0000 (algebraically invariant); any nonzero")
print("value here is the nonlinearity residual the reframe must budget for.")
