# Deforestation change-detection pipeline

Apply the EuroSAT-trained classifier to two-date Sentinel-2 imagery of a study
area, flag **Forest -> non-Forest** transitions, and validate against
**Global Forest Watch** (Hansen Global Forest Change) data.

## Pipeline

```
download_sentinel.py   Get two-date Sentinel-2 true-color GeoTIFFs (Copernicus Data Space)
patchify.py            Tile each scene into georeferenced 64x64 patches
classify_patches.py    Classify every patch -> land-cover grid (GeoTIFF)
change_detection.py    Compare year A vs B -> forest-loss map + event list
validate_gfw.py        Compare detected loss vs Global Forest Watch raster
```

## Prerequisites (need YOUR input)

1. **Study area** — a region with documented deforestation and clear-ish
   Sentinel-2 coverage for two dates (e.g. 2018 vs 2024). A small bounding box
   (~10-20 km) keeps it tractable.
2. **Copernicus Data Space account** (free) — the original guide's
   `scihub.copernicus.eu` was **retired in 2023**. Register at
   <https://dataspace.copernicus.eu/>. `download_sentinel.py` documents the
   current openEO / STAC access path.

## Important methodological caveat (radiometric matching) — VERIFIED CRITICAL

EuroSAT was built from hazier, less atmospherically-corrected Sentinel-2 (a blue
cast; global RGB mean ~ (86,97,103)). Modern Copernicus L2A composites are
atmospherically corrected, so a naive render is classified ~72% "SeaLake"
(forest read as water). `patchify.py` therefore applies per-channel **moment
matching**: it rescales each channel of the scene so its mean/std match EuroSAT's
global statistics. This fixed the run (forest correctly dominant; ~1% water) and
is the single most important step for valid results. Still a documented source of
domain shift — report it in the paper.
