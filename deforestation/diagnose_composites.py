"""
Composite data-quality diagnostics for the multi-site study.

For each site/date 4-band (B04,B03,B02,B08) Sentinel-2 median composite, report
indicators that distinguish a *degraded* composite (clouds, gaps, haze) from a
clean one - so we can tell whether a poor CNN result (e.g. Congo/Tshopo) is a
data problem or genuine domain shift:

  nodata%   fraction of pixels that are exactly 0 in all bands (compositing gaps)
  sat%      fraction near the top of the reflectance range (cloud/bright haze)
  meanNDVI  scene-mean NDVI (healthy tropical forest is high, ~0.7-0.9)
  forest%   fraction of pixels with NDVI >= 0.6 (rough vegetation vigor proxy)
  brightR   mean red reflectance (haze/cloud raises this)

Run:  python -m deforestation.diagnose_composites
"""
import numpy as np
import rasterio

from deforestation.sites import SITES

DIR = r"C:\Users\josha\ml-data\deforestation\sites"


def diagnose(path):
    with rasterio.open(path) as s:
        a = s.read().astype(np.float32)  # (4,H,W): R,G,B,NIR
    red, nir = a[0], a[3]
    # nodata = all four bands zero (compositing gap)
    nodata = np.all(a == 0, axis=0)
    valid = ~nodata
    v = valid.mean()
    # Reflectance scale: L2A is typically 0-10000 (uint16). Use robust top ref.
    top = np.percentile(a[:, valid], 99.9) if valid.any() else 0.0
    sat = (a.max(axis=0) >= 0.9 * top) if top > 0 else np.zeros_like(red, bool)
    ndvi = (nir - red) / (nir + red + 1e-6)
    ndvi_v = ndvi[valid]
    return {
        "nodata%": 100 * nodata.mean(),
        "sat%": 100 * (sat & valid).mean(),
        "meanNDVI": float(np.nanmean(ndvi_v)) if ndvi_v.size else float("nan"),
        "forest%": 100 * float((ndvi_v >= 0.6).mean()) if ndvi_v.size else float("nan"),
        "brightR": float(red[valid].mean()) if valid.any() else float("nan"),
        "valid%": 100 * v,
    }


def main():
    print(f"{'site_date':28s} {'valid%':>7s} {'nodata%':>8s} {'sat%':>6s} "
          f"{'meanNDVI':>9s} {'forest%':>8s} {'brightR':>8s}")
    for key in SITES:
        for y in (2016, 2024):
            p = f"{DIR}\\{key}_{y}.tif"
            try:
                d = diagnose(p)
            except Exception as e:
                print(f"{key}_{y:<22} MISSING/ERR: {str(e)[:40]}")
                continue
            print(f"{key+'_'+str(y):28s} {d['valid%']:7.2f} {d['nodata%']:8.2f} "
                  f"{d['sat%']:6.2f} {d['meanNDVI']:9.3f} {d['forest%']:8.2f} {d['brightR']:8.1f}")


if __name__ == "__main__":
    main()
