# Within-frontier deforestation-risk package

`risk/` implements the frozen `PLAN.md` study without changing the existing
detector paper. Large artifacts default to
`C:\Users\josha\ml-data\deforestation-risk` and can be redirected with
`RISK_DATA_ROOT`.

The intended stage order is:

```powershell
# 0. Assumption evidence (real network reads + an actual composite histogram)
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.phase0

# L13 inputs. CHIRPS is 7.70 GB and is opt-in; the exact Miettinen extent must
# be supplied because the frozen plan does not give a stable data-file URL.
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.external_layers --include-chirps --peatland <exact-file>

# Build/screen/draw/hash the pre-2021 frame. The downloaded HydroBASINS layer
# identifies the level-3 Amazon polygon as HYBAS_ID 6030007000.
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.frame `
  --ecoregions <Ecoregions2017.shp> `
  --hydrobasins <hybas_sa_lev03_v1c.shp> `
  --peatland <exact-Miettinen-layer> `
  --amazon-hybas-id 6030007000

# Freeze CHIRPS windows and screen legacy sites before imagery:
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.finalize_sites <selected_sites.json> <chirps-v2.0.monthly.1991-2020.nc>

C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.download_timeseries <analysis_sites.json> --dry-run
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.download_timeseries <analysis_sites.json>

# Prepare each QC-passing site, concatenate its two cell tables, then fit both
# normalized and unnormalized pipelines.
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.prepare <analysis_sites.json> <site-id> --raw-root <composites>
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.models <combined-cells.csv> --pipeline normalized --output <predictions.csv>
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m risk.evaluation <predictions.csv>

# Proof suite
C:\Users\josha\.venvs\satclf\Scripts\python.exe -m pytest risk/tests/ -v
```

Download provenance JSON stores the exact openEO process graph for every
site-year. `download_timeseries` refuses to start if either pre-download L13 hash
does not match. `prepare` writes tables even when QC fails so attrition can be
audited; failed sites must not be concatenated into a model input.
