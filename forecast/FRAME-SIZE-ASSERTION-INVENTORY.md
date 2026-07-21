# Specification W frame-size assertion inventory

This inventory is part of the amended/exploratory implementation. The 12-site
v11 primary defaults are intentionally not replaced.

| Module / assertion | Specification W disposition |
|---|---|
| `risk.config`: `FRAME_SITES_PER_GROUP=3`, `FRAME_REQUIRED=12`, `FEATURE_YEARS=(2018,2019,2020)` | Primary-only and unchanged. W uses `forecast.specification_w.K=9`, `SITES=36`, and separate archive/model-history constants. |
| `risk.frame.select_round_robin`: three rounds | Default remains three. W passes the additive `sites_per_group=9` argument and records every rejection through the callback. |
| `risk.frame.finalize_analysis_sites`: original frame and `FEATURE_YEARS` | Primary-only. W uses `build_amendment_artifacts`, which replays the draw and freezes 2018–2022 periods for all 36 sites. |
| `risk.download_timeseries.validate_pre_download_manifest`: 3x4, exact `FEATURE_YEARS`, no post-2020 period | Primary path unchanged. W uses `download_forecast_schedule`, which validates and consumes only the separately frozen 144-pair schedule. |
| `risk.download_timeseries.download_manifest`: loops all manifest sites | Primary path unchanged. W's downloader loops schedule entries only, so no legacy site or already-held pair can enter. |
| `risk.cohort.attrition_report`: 12 retained and 3 per group | Outside W. It is availability/QC replacement bookkeeping for the original frame. W forbids replacement or lower-K analysis; its frozen manifest and completeness gate are the only admission path. |
| `risk.models.run_loso`: 12 outer / 11 training sites | Default remains 12/11. W's wrapper supplies 36, producing 35 training sites, and stamps a separate result namespace. |
| `risk.features`, `risk.grid`, `risk.normalization`, `risk.prepare`: exact `FEATURE_YEARS` | Intentionally unchanged: these are rolling three-year model-history assertions, not archive-availability assertions. W selects the appropriate three-year history per origin; it does not turn the model into a five-year history. |
| `risk.hansen` / `risk.prepare`: raw Hansen readers | Excluded from W's pre-lift and evaluator paths. W frame selection replays frozen CSV artifacts, the precheck consumes censored boolean handoffs, and evaluators receive only the post-lift mask schema. |
| `risk.census.verify_composites`: scan whatever exists | Replaced by the W manifest/schedule-derived 720-TIFF gate; partial, corrupt, schema-invalid, provenance-invalid, or all-nodata archives are not analysable. |

Unrelated numeric threes are explicitly unchanged: the three-evaluable-site
regional floor, the 30-component regional floor, and the three-site SAR pilot.

