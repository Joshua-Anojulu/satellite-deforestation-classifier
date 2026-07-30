# Static-Features Plan — Review Log

**Task.** Turn the acquired static archive into model-ready features on the pinned GFC 30 m grid and the
90 m block grid: road density and distance-to-road from dated OSM extracts, elevation and slope from
SRTM v4.1. Feeds the `contagion+static` and `full_without_sar` arms.

**Plan file.** `STATIC-FEATURES-PLAN.md`
**Governing documents.** `FORECAST-PLAN.md` §3/§8, as amended by `ANALYSIS-DRIVER-PLAN.md`
(`approved-final`, body `030d78fa`) and its logged deviations 1–3.

## Resolved caps

| Var | Value |
|---|---|
| `MAX_ROUNDS` | 5 |
| `MAX_ATTEMPTS` | 8 |
| `PLAN_FILE` | `STATIC-FEATURES-PLAN.md` |
| `LOG_FILE` | `STATIC-FEATURES-REVIEW-LOG.md` |
| reviewer | resolved at Act 2 |

## Act 1 — Grill (Claude ↔ Josh)

**Why this plan exists:** `FORECAST-PLAN.md` §3 names roads and terrain as static drivers but freezes **no
feature formulas** for either, unlike §8's contagion features. The definitions were genuinely undefined.

State established by measurement before any question was asked:

- **No OSM `.pbf` reader is installed** (pyrosm, osmium, osmread all absent). GDAL's OSM driver is
  available through pyogrio 0.13.0 and reads the acquired extracts.
- **A bbox-filtered read costs ~20 s on a 79 MB extract** — the driver has no spatial index and scans the
  whole file. Indonesia is 1.4 GB. This makes one-pass-per-file (12 reads) rather than per-site-origin
  (108 reads) a structural requirement, not an optimisation.
- **`track` is the largest road class** at the sampled site: 15 of 43 highway features, more than
  `residential` and `service` combined.
- **OSM mapping drift is real and measurable.** At `F3_M020.720_M0058.500`, engineered road length moved
  +0.1 % across 2020→2022 while **track length rose +30 %, all of it into the test origin**. The 2020 and
  2021 snapshots were byte-identical for that window.
- The GFC grid is geographic, so pixels are **8.1 % anisotropic** on the ground across the site latitude
  span, and the distortion correlates with biome (`dry_forest` is furthest from the equator).

Decisions locked with Josh:

| # | Decision |
|---|---|
| 1 | Two road tiers — `engineered` vs `track` — computed separately, never merged; unexpected tags excluded **and counted**. |
| 2 | **Roads frozen at the 2020-01-01 snapshot for every origin.** Kills the measured +30 % track-mapping artifact that trends toward the test origin. 2021/2022 extracts retained as evidence and as the step-9 sensitivity input. |
| 3 | Road features mirror the §8 contagion shapes: multi-radius density + censored distance + an explicit absent flag, per tier. |
| 4 | Slope computed on the **native 90 m** grid, then resampled to 30 m — never the reverse. |
| 5 | All distances, radii and areas **in metres**, via a per-site azimuthal-equidistant projection. Radii `{30,90,150,300,600,1500}` m; `R_MAX = 1500 m`. |
| 6 | `roads_covered` derived from **any mapped OSM feature** in the window, so "roadless" is distinguished from "unmapped". No invented density threshold. |

Carried forward as an open question rather than settled: decision 5 makes roads metric while the
`approved-final` analysis plan specifies contagion in pixels (`R_MAX = 50 px`). Phase C1 is unbuilt, so
aligning them is cheap — but it would be a change to an approved body and must be a logged deviation.

---

## Round 1 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb0d1-a664-7723-a29b-1e87121fcaf2
- reviewed body_sha256: 42e6cbbb8f4d3980c23467cfb3929b66da86543a3103b6d76eabe4f9f8eb87d9
- verdict: REVISE (2 critical, 11 high, 4 medium)

### Critique (verbatim)

Material problems remain, including unresolved conflicts with the approved design.

1. **Critical: the 2020 road freeze is an unlogged fourth deviation.** The proposal freezes every origin to 2020 ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:43>)), while deviation 3, the registry, and tests require January 1 of each origin ([log](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-REVIEW-LOG.md:642>), [registry](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_layers.py:82>), [test](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/tests/test_static_layers.py:184>)).
   Fix: Either log and approve deviation 4 and update the registry, schema manifest, and tests atomically, or retain per-origin snapshots.

2. **Critical: the metric-road versus pixel-contagion conflict is unresolved.** The approved formulas are explicitly `{1,3,5,10,20,50}` pixels ([approved plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:192>)); the proposal incorrectly says they are already expressed as metres, then leaves the contradiction open ([static plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:88>)).
   Fix: Keep approved contagion unchanged and describe metric roads as a distinct kernel family, or approve a logged deviation that revises every contagion formula, halo, test, and artifact schema.

3. **High: one site cannot establish that the observed 33 km is mapping drift.** Snapshot differences alone cannot distinguish late mapping, retagging, geometry edits, and actual construction, so “nobody built” and the claimed 0.1% cost are unsupported extrapolations ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:45>)).
   Fix: Run a preregistered all-site audit using identical clips, element IDs/versions, raw tags, and a blinded imagery sample before freezing the vintage.

4. **High: freezing removes direct year encoding but relocates the confound.** A fixed snapshot preserves spatial variation in 2020 OSM completeness, mapping conventions, and divided-road representation, while measurement staleness grows from 2020 to 2022 and may differ systematically by biome or country.
   Fix: Treat the feature as “mapped centreline network as of 2020,” independently audit completeness by site, and exclude or sensitivity-mask sites or tiers that fail that audit.

5. **High: `roads_covered` is not a survey-coverage measure.** An imported boundary, river, or land-use polygon does not show that roads were surveyed, and one feature anywhere in a roughly 0.25-degree window cannot establish coverage throughout it ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:94>)).
   Fix: Replace it with `roads_source_available` derived from full PBF polygon coverage per cell, and represent road-map completeness as unknown unless an independent coverage source exists.

6. **High: the terrain pipeline is internally inconsistent.** SRTM is a geographic three-arcsecond grid, so slope cannot simultaneously be computed on its “native 90 m grid” and in a projected metric CRS without first resampling elevation; the later slope-resampling operator and nodata behavior are also unspecified ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:103>)).
   Fix: Freeze one explicit pipeline, such as mosaic, metric 90 m elevation warp with stated operator and halo, Horn slope, stated 30 m sampling operator, nodata rules, and disclosure that 30 m values remain interpolated 90 m estimates.

7. **High: “mapped back to the analysis grid” leaves a result-changing operation undefined.** A second raster warp can shift or smooth densities and distances and can corrupt binary flags, partially recreating the lattice artifacts the projection was meant to avoid ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:67>)).
   Fix: Compute features for immutable GFC cell centres and return them by `(row, column)` without raster reprojection, or freeze alignment and a per-feature resampling operator with error tests.

8. **Medium: AEQD is not equidistant between every focal pixel and every road and is not equal-area.** The window is small enough that distortion is probably negligible, but the plan supplies no numeric ceiling for pairwise distance, road length, or density-denominator area error.
   Fix: Calculate worst-case distance, line-length, and area scale error across every site edge and radius and fail above a prespecified tolerance.

9. **High: the road-tag contract is neither exact nor portable.** “Their `_link` forms” is ambiguous and appears to create nonstandard values such as `residential_link`; `service` combines driveways and industrial access with tracks; country-specific use of `unclassified`, `track`, and `service` is not assessed ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:28>)).
   Fix: Enumerate every accepted literal tag, separate `service`, and publish count and length cross-tabs by raw tag, lifecycle tag, `surface`, `tracktype`, `access`, site, and country before freezing tiers.

10. **High: filtering on the tier allow-list makes excluded-tag counting impossible.** Step 7.2 proposes filtering highways to the accepted lists on read, but step 1 requires values outside those lists to be counted ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:118>)).
    Fix: Stream every feature with a non-null `highway` tag once, classify locally, and record both count and centreline length for every excluded raw value.

11. **High: multi-region sites can double-count or truncate roads.** Existing acquisition deliberately permits multiple overlapping Geofabrik regions ([implementation](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_archive.py:120>)), but the proposal defines no deduplication for ways duplicated or split across extracts.
    Fix: Mosaic by OSM element type, ID, and version, reconcile split geometries, clip only after deduplication, and assert complete metric-halo coverage with zero duplicate length.

12. **Medium: the acquired halo and proposed halo use different definitions.** Acquisition used `51 × 0.00025°`, about 1,410 m north-south, while the proposal requires 1,500 m plus one pixel ([implementation](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_archive.py:81>)).
    Fix: Introduce one shared metric-halo derivation and revalidate every acquired SRTM tile and OSM region union before extraction.

13. **High: the 90 m aggregation rule is misstated.** The proposal says all block features are means of nine values, whereas the approved plan requires continuous means but categorical majority with a fixed tie rule ([static plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:124>), [approved plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:221>)).
    Fix: Freeze aggregation per field, including majority rules for coverage/absence flags and exact `valid_count`, `any_missing`, and `*_undefined` semantics.

14. **High: the output schema cannot yet join safely to the approved tables.** “Per `(site, scale)`” omits the immutable GFC key and gives no one-to-one join contract with the approved `(θ, site, origin, scale)` tables; it also omits the required `terrain_covered` feature ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:128>), [schema](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_layers.py:210>)).
    Fix: Define a normalized static table keyed by `(site_id, scale, gfc_row, gfc_col)`, require cardinality-preserving joins, and enumerate every column, dtype, unit, coverage flag, and missingness rule.

15. **High: provenance can silently certify mutated inputs.** The feature manifest merely copies hashes from the inventory instead of rehashing consumed files, even though the inventory has zero publisher MD5s and explicitly provides only receipt-time self-pinning ([inventory](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/artifacts/static_archive_inventory.json:645>)).
    Fix: Rehash every input before parsing, fail against the inventory, and record the inventory hash, weak-anchor disclaimer, site-manifest hash, code tree, GDAL/PROJ/pyogrio configuration, and output hashes.

16. **High: the extraction structure will not reliably survive interrupted or overlapping runs.** There are no atomic per-PBF intermediates, durable checkpoints, exclusive run lock, or bounded-memory streaming contract; the per-window coverage probes may also defeat the claimed one-scan design, while the required OSM stack is absent from [requirements.txt](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/requirements.txt:15>).
    Fix: Create a content-addressed normalized cache in one streaming scan per PBF, publish each stage atomically under an exclusive lock, checkpoint per PBF and site, and pin the complete geospatial environment and OSM configuration.

17. **Medium: the sensitivity promises work declared out of scope.** Reporting how the `contagion+static` model arm “moves” requires fitting and evaluation, while the plan says model fitting, evaluation, and embargo handling are excluded ([sensitivity](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:135>), [scope](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:171>)).
    Fix: Limit this plan’s sensitivity to feature-drift summaries and defer model-arm impact to the approved modelling phase.

Verified context: the approved body recomputes to `030d78fa…`; the log contains exactly three deviations; the inventory contains 64 files totaling 9.423 GB, including 36 road snapshots and 28 SRTM tiles, with no publisher MD5s. No files were modified.

VERDICT: REVISE
### Claude's response (round 1)

**All 17 findings accepted; none rejected.** Three load-bearing claims were verified in source first:

- **#2 confirmed — my error.** `ANALYSIS-DRIVER-PLAN.md:194` specifies `r ∈ {1,3,5,10,20,50}` **px**. v1's
  claim that the approved plan "already writes them as metres" was false; the metre values were a
  parenthetical gloss. Withdrawn.
- **#12 confirmed and worse than stated.** The acquisition halo is `51 × 0.00025°` = **1419 m north–south
  and 1304 m east–west at 23°S**, against a proposed `R_MAX` of 1500 m — short in *both* directions, not
  just the ~1410 m Codex cited. Re-deriving the SRTM set at the worst-case 59 px nevertheless yields **the
  same 28 tiles**, so the acquired archive is sufficient; the plan now derives the halo in metres and
  asserts coverage at startup rather than inheriting a pixel constant.
- **#1 confirmed.** `forecast/static_layers.py:72` returns `date(origin, 1, 1)`, so the committed registry
  genuinely contradicts the freeze.

Five findings were **internal contradictions in my own plan**, which is the more uncomfortable half of this
round: filtering on the tier allow-list while requiring excluded-tag counts (#10); promising a model-arm
sensitivity while declaring model fitting out of scope (#17); computing slope both "natively" and "in a
projected CRS" (#6); the px/metres misstatement (#2); and a uniform 90 m mean contradicting the approved
per-field rule (#13).

| Finding | Change |
|---|---|
| 1 | Freeze declared **deviation 4**, with registry, schema manifest and tests updated **atomically** with the feature code. |
| 2 | Conflict resolved by keeping approved contagion **unchanged** and declaring roads a **distinct metric kernel family**, never compared radius-for-radius. Aligning contagion stays available as a future deviation, not taken here. |
| 3 | Freeze made **conditional on a preregistered all-site audit** using element **id and version** deltas plus a blinded imagery sample, since a snapshot diff cannot separate late mapping, retagging, geometry edits and construction. The one-site measurement is demoted to the hypothesis under test. |
| 4 | Stated that freezing **relocates** the confound; feature renamed "mapped centreline network as of 2020-01-01"; sites/tiers failing the completeness audit are excluded or masked. |
| 5 | `roads_covered` → **`roads_source_available`** from PBF coverage polygons; road-map completeness declared **unknown** rather than inferred from unrelated features. |
| 6 | One explicit terrain pipeline: mosaic → bilinear warp to metric 90 m → Horn slope → bilinear sample to cell centres → nodata rules → manifest discloses 30 m values are interpolated 90 m estimates. |
| 7 | **No raster back-warp.** GFC cell centres are projected *into* the local CRS and features evaluated at those points, returned by `(gfc_row, gfc_col)`. Geometry moves; the grid never does. |
| 8 | Worst-case distance, length and area error computed per site, **failing closed above 0.5 %**, with a per-site UTM/TM fallback. |
| 9 | Every accepted tag **enumerated literally** (no `_link` hand-wave, no invented `residential_link`); `service` split into its own tier; tiers **provisional** until the raw-tag/surface/tracktype/access/country cross-tab is published. |
| 10 | Stream **every** non-null `highway` feature once, classify locally, record count **and length** per excluded raw value. |
| 11 | Deduplicate by **(element type, id, version)** across overlapping extracts, reconcile split ways, clip only after dedup, assert **zero duplicate length**. |
| 12 | One metric halo (`R_MAX` + one pixel), **verified** against the acquired archive with a fail-closed startup assertion. |
| 13 | Per-field 90 m aggregation: continuous mean, categorical majority with tie rule, flags majority, explicit `valid_count`/`any_missing`/`*_undefined` semantics. |
| 14 | Output keyed **`(site_id, scale, gfc_row, gfc_col)`** with a cardinality-preserving join test; `terrain_covered` added. |
| 15 | Inputs **rehashed before parsing** and checked against the inventory; manifest records recomputed hashes, the inventory hash, its weak-anchor disclaimer verbatim, code tree, and resolved GDAL/PROJ/pyogrio versions. |
| 16 | Content-addressed per-PBF cache, atomic stage publication, exclusive lock, per-PBF/per-site checkpoints, bounded-memory streaming, and the geospatial stack **pinned in requirements.txt** (currently absent entirely). |
| 17 | Sensitivity narrowed to **feature-drift summaries**; model-arm impact deferred to the modelling phase. |


## Attempt 2 — codex — NOT A ROUND (timeout)

Cut off mid-turn by this environment's background time limit, not a Codex failure: the event stream
held `thread.started`, `turn.started` and five completed items but **no `turn.completed` and no error
event**, with empty stderr. No capture file was written, so per invariant 1 it is not a round and does
not consume MAX_ROUNDS. Josh authorised one retry, unchanged, into a fresh capture directory.

## Round 2 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb0d1-a664-7723-a29b-1e87121fcaf2 (resumed)
- reviewed body_sha256: ab41bafae5d4bedd698c2077f52332b19610f9f0340c6b976b22186675a61cce
- verdict: REVISE (1 critical, 6 high, 3 medium)
- NOTE: reviewer conceded the separate metric-kernel declaration as "a valid resolution rather than a
  rename", closing round-1 finding #2.

### Critique (verbatim)

## Remaining material findings

1. **Critical: the audit gate is not actually preregistered.** Neither the all-site audit nor the provisional tier cross-tab specifies sample size, imagery dates/source, adjudication, uncertainty calculation, pass thresholds, or deterministic outcomes for freeze/per-origin/drop-tier ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:57>), [audit](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:70>)). Results would therefore trigger post-audit judgment, and deviation 4 cannot yet be approved or implemented atomically.

   Fix: Freeze an audit decision table now, then sequence audit tooling first, append deviation 4 and mutate the registry only on PASS, and stop for plan revision on FAIL.

2. **High: the audit does not measure the “completeness” used by its exclusion rule.** Element deltas and imagery distinguish temporal mapping from construction; they do not estimate how much of the 2020 road network was unmapped. This contradicts both “completeness unknown” and “site or tier failing the completeness audit is excluded” ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:79>), [coverage](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:135>)). Site-specific exclusion would also disturb the frozen 36-site population or encode biome through masking.

   Fix: Remove completeness-based site exclusion, keep all frozen sites, make tier decisions globally from the temporal-drift gate, and require an independent source before making any completeness decision.

3. **High: projected cell centres define evaluation locations, not a computational operator.** Exact point-to-line distance and exact line length inside millions of point-centred discs are well-defined but potentially prohibitive; a raster EDT/convolution requires a metric raster resolution, origin, line-length rasterization rule, kernel discretization, and sampling operator that the plan deliberately removed ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:109>)).

   Fix: Freeze either exact vector `STRtree`/line-disc operations with a runtime gate, or a specified metric-raster approximation validated against an exact vector oracle at every radius.

4. **High: `(type, id, version)` is the wrong deduplication identity.** If overlapping same-origin extracts contain the same ID at different versions, including version in the key retains both; split fragments with the same key need geometric union, while split, merged, or renumbered ways across origins defeat the audit’s ID-delta interpretation ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:168>)).

   Fix: Deduplicate per `(origin, type, id)`, require or deterministically resolve version conflicts, union same-version fragments, and use geometry-overlap plus changeset/tag lineage for cross-origin split/merge matching.

5. **High: the required PBF coverage polygons were never acquired or pinned.** Existing acquisition fetches the current Geofabrik index to select regions, but the saved plan and inventory retain URLs and hashes, not geometries ([loader](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_archive.py:62>), [saved plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_archive.py:417>)). A PBF header bounding box is not the exact extraction polygon, so `roads_source_available` and the startup coverage assertion are not reproducible from the certified archive.

   Fix: Pin and hash the exact Geofabrik index or `.poly` artifacts as auxiliary inputs and derive full-disc availability from their union, without overwriting the existing write-once inventory.

6. **High: terrain nodata still does not propagate coherently.** Bilinear warping may renormalize over valid neighbours unless a validity mask is carried explicitly; Horn slope expands support to 3×3 cells, and final bilinear sampling expands it again. A single `terrain_covered` cannot distinguish valid elevation from undefined slope near a void ([pipeline](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:146>)).

   Fix: Propagate a strict source-validity mask through warp, Horn, and final sampling, emit feature-specific undefined flags, and reserve `terrain_covered` for source-footprint availability.

7. **High: the proposed OSM stack does not yet guarantee the required metadata or one-pass stream.** GDAL’s default `osmconf.ini` disables `osm_version`, and large PBFs require dataset-level interleaved reading; bulk per-layer pyogrio reads do not by themselves establish the promised single scan. GDAL explicitly recommends `GDALDataset::GetNextFeature()` or interleaved import for large OSM files in its [OSM driver documentation](https://gdal.org/en/stable/drivers/vector/osm.html).

   Fix: Pin a custom configuration with `osm_version=yes` and required tags, and freeze a dataset-level `GetNextFeature()` or `ogr2ogr` interleaved import path rather than an unspecified pyogrio loop.

8. **Medium: the convention conflict is conceptually resolved, but step 4 reintroduces contradictory wording and an off-by-one halo.** Separate, unit-suffixed road kernels can coexist with approved pixel contagion, but “expressed in metres for both families” contradicts leaving contagion untouched. At 23.25° latitude, one east-west pixel is about 25.57 m, so 59 pixels cover only 1508.6 m; `R_MAX + one pixel` requires 60, not 59 ([plan](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:99>)).

   Fix: Scope the metric halo exclusively to road extraction and verify the archive using the exact geodesic `1500 m + one-cell` buffer, not the 59-pixel approximation.

9. **Medium: the 90 m key remains ambiguous.** `(scale, gfc_row, gfc_col)` does not say whether a 90 m row/column is the block’s top-left native cell, centre cell, or a new block index, so two implementations can produce different joins while each appears cardinality-preserving ([schema](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:181>)).

   Fix: Freeze global 3×3 block alignment and define the 90 m key explicitly as either block indices or a canonical native-cell anchor.

10. **Medium: projection fallback and cache identity are underdetermined.** “Local transverse-Mercator or UTM” leaves a result-changing choice to the implementer, while the normalized cache key omits the resolved GDAL/PROJ versions and OSM configuration that determine parsed geometries ([projection](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:127>), [cache](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:172>)).

    Fix: Freeze one deterministic fallback CRS and include the complete parser, configuration, and geospatial-stack fingerprint in every cache and checkpoint key.

The separate metric-kernel declaration is otherwise a valid resolution rather than a rename: predictor families need not share spatial units once their names, supports, and comparisons are explicit. The audit gate, point operator, deduplication, coverage provenance, and nodata contract remain implementation-blocking. No files were modified.

VERDICT: REVISE
### Claude's response (round 2)

**All 10 findings accepted; none rejected.** Two were verified in source first:

- **#8 confirmed — my arithmetic was wrong.** One east–west pixel at 23.25° is 25.57 m, so 59 px covers
  1508.6 m while `R_MAX` + one cell = 1525.6 m needs **60 px**. The v2 verification used 59. The
  *conclusion* survived (the SRTM set is 28 tiles at every halo from 51 to 66 px) but was reached by a
  wrong calculation, so the halo is now a **geodesic buffer** re-derived and asserted at startup rather
  than a pixel approximation.
- **#5 confirmed.** `static_archive_inventory.json` contains only `roads` and `terrain` kinds — **no
  coverage polygon was ever acquired or pinned**, so `roads_source_available` as written was not
  reproducible from the certified archive.

| Finding | Change |
|---|---|
| 1 | **Sequencing made explicit and preregistered**: audit tooling first, then the audit, then deviation 4 **only on FREEZE**, then features. A full **decision table is frozen before results are seen** — `p` = new-id-length share labelled pre-existing-unmapped with **ambiguous counted as construction**, `q` = Wilson 95 % lower bound, and four deterministic branches including the CI-straddles case and an immaterial-drift shortcut. |
| 2 | **Completeness-based site exclusion removed entirely.** The audit measures temporal drift, not how much of the 2020 network was unmapped — different quantities. All **36 sites retained unconditionally**; dropping sites would disturb the frozen population and risk encoding biome, which is the failure that retired the earlier risk study. Tier decisions are global. |
| 3 | **Operator frozen, not just locations**: exact vector `STRtree` distance and exact clipped length primary; a **benchmarked runtime gate at 4 h per site-scale**; and if it trips, a 10 m metric-raster approximation **validated against the exact oracle** on 5 000 sampled cells per site and radius, within 1 % of disc area / one cell. |
| 4 | Dedup key corrected to **`(origin, type, id)`** — versioning the key *retains* both copies. Highest version wins within an origin; same-version fragments unioned; cross-origin lineage by geometry overlap plus changeset, with unresolved cases **counted and reported**. |
| 5 | **Geofabrik `.poly` polygons acquired and pinned** as auxiliary inputs in a **separate** write-once inventory, leaving the existing one untouched. A cell is available only if its **full `R_MAX` disc** lies inside the union. |
| 6 | **Validity mask carried end to end**: warped by nearest alongside bilinear elevation; slope mask is the 3×3 erosion (Horn's kernel); per-feature undefined flags, since a cell can have valid elevation and undefined slope beside a void; `terrain_covered` reserved for source footprint. |
| 7 | **Repo-local `osmconf.ini` with `osm_version=yes`** — GDAL's default disables it, and the audit depends on it — with its sha256 in every cache key. **Dataset-level interleaved reading**, since per-layer pyogrio reads re-traverse the file and do not deliver the claimed single scan. |
| 8 | Metric halo **scoped to roads only** (v2's "for both families" contradicted leaving contagion untouched), and the halo is now geodesic. |
| 9 | 90 m key frozen as `(row // 3, col // 3)` under **global 3×3 alignment anchored at the pinned GFC grid origin**. |
| 10 | Fallback CRS frozen to the **UTM zone of the site centroid**; cache key extended with resolved GDAL/PROJ/pyogrio versions and the `osmconf.ini` hash. |

**Round-1 #2 closed by the reviewer**, which is worth recording: the separate metric-kernel declaration was
accepted as "a valid resolution rather than a rename".


## Round 3 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb0d1-a664-7723-a29b-1e87121fcaf2 (resumed)
- reviewed body_sha256: a675bb06863d6bb75dc88f4071ea67f5b6779133cbc25b4a8bf9102606badb00
- verdict: REVISE (3 critical, 5 high)

### Critique (verbatim)

Material inconsistencies remain; the plan is not yet deterministic or implementable end to end.

1. **Critical: the audit decision table is overlapping and incomplete.** The `<5%` shortcut overlaps every confidence-interval branch, “delta length” is not defined as signed, absolute, or gross change, zero-new-ID cases leave `p` and its interval undefined, and sequencing mentions `DROP` although the table defines no DROP outcome. [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:89>)  
   **Fix:** Freeze an ordered, mutually exclusive table using gross change, with explicit zero-denominator, boundary-equality, DROP, and precedence rules.

2. **Critical: the sampling design cannot support the stated Wilson interval.** A sample of 50 with a two-item floor for every contributing site is impossible above 25 sites, while length-weighted observations selected through site-stratified sampling are not ordinary binomial trials for which a Wilson interval is valid.  
   **Fix:** Freeze a feasible allocation, seed, imagery source/date hierarchy, and inclusion probabilities, then use a design-based stratified interval for the length-weighted estimator.

3. **High: the audit does not measure all mapping drift that affects the features.** `p` classifies only new IDs, while same-ID geometry changes, retagging, splits, merges, and spatial relocation can materially change distance or density without increasing net road length; unresolved lineage has no conservative treatment in the decision rule.  
   **Fix:** Gate on gross feature-space drift across every delta class and count unresolved lineage against FREEZE, with deterministic site and biome aggregation.

4. **Critical: mixed tier outcomes cannot be represented by the proposed schema.** The table can freeze one tier, retain per-origin behavior for another, and drop a third, but the committed registry has one `roads` vintage policy, while the proposed output key omits `origin`. [static_layers.py](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_layers.py:46>) [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:209>)  
   **Fix:** Give every tier its own manifest policy and include `origin` in the logical road-feature key for all outcomes, allowing frozen tiers to deduplicate physically only.

5. **High: the stated sequencing depends on machinery scheduled after the audit.** The audit requires normalized parsing, version-aware deduplication, cross-origin lineage, pinned parser configuration, and reproducible length calculations, but those contracts appear in the later extraction phase. [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:51>) [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:188>)  
   **Fix:** Add a prerequisite phase that pins the stack and builds the normalized caches, deduplication, and lineage outputs before either the cross-tab or audit runs.

6. **High: fallback validation still lacks an executable acceptance contract.** “Within 1% of disc area for density” compares incompatible quantities; the 5,000-cell sample lacks a seed and road-stratification rule; grid origin, disc edge-cell treatment, and GFC sampling are unspecified; and summed-area tables do not directly implement circular kernels. The sampled exact-vector oracle is viable even when full exact extraction is too slow, but only after these details are frozen. [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:132>)  
   **Fix:** Freeze raster alignment, circular-kernel construction, boundary attribution, deterministic road-stratified oracle samples, and feature-unit tolerances including explicit zero-road cases.

7. **High: deduplication and lineage cannot yet be executed safely from the extracts.** Highest-version-wins can discard complementary or more complete fragments from another regional extract; same-version union has no tag-conflict rule; split/merge overlap thresholds are absent; and `osm_version=yes` does not itself guarantee the changeset field required by lineage.  
   **Fix:** Pin and verify version, timestamp, and changeset fields; fail closed on conflicting versions/tags; freeze fragment completeness and overlap thresholds; and propagate unresolved length into the audit decision.

8. **High: terrain validity is not coherent through bilinear warping.** A validity mask warped by nearest neighbour does not indicate whether every source sample used by the bilinear elevation warp was valid, so the subsequent 3×3 erosion can still certify slopes derived from nodata-contaminated elevation values. [STATIC-FEATURES-PLAN.md](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/STATIC-FEATURES-PLAN.md:173>)  
   **Fix:** Derive destination elevation validity from the complete bilinear support footprint, then erode that mask for Horn slope and require all final interpolation neighbours valid, with the local 90 m grid origin frozen.

The separate metric road-kernel family does resolve the pixel-versus-metric convention conflict conceptually because contagion remains unchanged and the road variables have distinct semantics and units. It does not resolve the independent mixed-vintage schema problem above.

VERDICT: REVISE
### Claude's response (round 3) — and Resolution: SUPERSEDED by a three-way split

**All 8 findings accepted; none rejected.** Two were confirmed by arithmetic alone:

- **#2 confirmed.** The sampling design demanded a floor of 2 per contributing site across up to 36 sites
  — **72 samples against a stated n = 50**. Impossible on its face, before reaching the separate and also
  correct point that length-weighted stratified observations are not binomial trials and so cannot carry a
  Wilson interval.
- **#4 confirmed.** `forecast/static_layers.py` holds exactly **one** `roads` vintage policy, so a mixed
  per-tier outcome (FREEZE `track`, PER-ORIGIN `engineered`) is unrepresentable by construction — and the
  proposed output key omitted `origin`.

**Resolution: this plan is closed as `reviewed-unapproved` and superseded, not deadlocked.** The cap was
not reached (3 of 5 rounds, 4 of 8 attempts). Josh chose to re-scope after the following observation.

Total findings fell 17 → 10 → 8, but **criticals rose 2 → 1 → 3**, and every round-3 critical was a
structural failure in a fix introduced the round before:

| Round-3 critical | Which round-2 fix it broke |
|---|---|
| Decision table overlapping/incomplete | the "frozen deterministic table" (r2 #1) |
| Sampling design impossible and statistically invalid | the "preregistered audit" (r2 #1) |
| Mixed tier outcomes unrepresentable | per-tier decisions (r2 #2) |
| Sequencing circular — audit needs the later phase's machinery | "audit first" (r2 #1) |

The diagnosis is that this document bundles **three separable concerns**: OSM parsing/dedup/lineage
infrastructure, a preregistered statistical study, and a geospatial feature specification. Each fix to one
destabilised another, which is why criticals rose while totals fell. Round-3 finding #5 says the same thing
from the other direction: the audit depends on machinery scheduled after it.

**Superseded by three sequenced plans**, each independently reviewable, each taking its predecessor's
output as a fixed input:

- **Plan A — OSM normalisation infrastructure.** Pinned geospatial stack and repo-local `osmconf.ini`
  (`osm_version=yes`, changeset fields verified present); dataset-level interleaved reading; deduplication
  on `(origin, type, id)` with version/tag conflict rules; cross-origin lineage with overlap thresholds and
  an unresolved-fraction report; content-addressed caches, atomic stages, checkpoints. Absorbs round-3
  findings #5 and #7.
- **Plan B — the roads vintage audit**, as a preregistered study taking Plan A's normalised output as
  input. Must fix the decision table (ordered, mutually exclusive, gross change, zero-denominator,
  boundary equality, DROP defined) and replace the sampling design with a feasible allocation and a
  design-based stratified interval. Absorbs #1, #2, #3, and #4's per-tier policy question.
- **Plan C — feature extraction**, taking Plan B's per-tier vintage decision as a fixed input. Operators,
  the oracle-validated fallback with unit-correct tolerances, terrain validity through the full bilinear
  support footprint, schema and provenance. Absorbs #6 and #8.

Nothing in this body may be built from. Its content is the input to the three successor plans, and the
material already settled by the grill — three literal tiers, metric road kernels as a distinct family with
approved contagion untouched, geodesic halo, GFC-cell-centre evaluation with no back-warp, all 36 sites
retained unconditionally, completeness declared unknown — carries forward into them.
