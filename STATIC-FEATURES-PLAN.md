---
review_provenance:
  schema_version: 2
  status: reviewed-unapproved
  rounds:
    - round: 1
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb0d1-a664-7723-a29b-1e87121fcaf2
      body_sha256: 42e6cbbb8f4d3980c23467cfb3929b66da86543a3103b6d76eabe4f9f8eb87d9
      verdict: REVISE
    - round: 2
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb0d1-a664-7723-a29b-1e87121fcaf2
      body_sha256: ab41bafae5d4bedd698c2077f52332b19610f9f0340c6b976b22186675a61cce
      verdict: REVISE
    - round: 3
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb0d1-a664-7723-a29b-1e87121fcaf2
      body_sha256: a675bb06863d6bb75dc88f4071ea67f5b6779133cbc25b4a8bf9102606badb00
      verdict: REVISE
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
  status_note: >-
    SUPERSEDED, not approved. Closed after round 3 by Josh's decision to split the work
    into three sequenced plans (infrastructure, vintage audit, feature extraction),
    because the rising critical count came from bundling three separable concerns in one
    document. This body was never approved and must not be built from. Its content is the
    input to the three successor plans.
---

# Plan: Road and terrain feature extraction for Specification W
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–2_

> **Governing documents.** `FORECAST-PLAN.md` §3 (static drivers, issue-date firewall) and §8 (contagion
> feature shapes), as amended by `ANALYSIS-DRIVER-PLAN.md` (`approved-final`, body `030d78fa`) and its
> logged deviations 1–3. §3 names roads and terrain as static drivers but **freezes no feature formulas**
> for either — that gap is why this plan exists.

## Goal

Turn the acquired static archive (64/64 files, 9.42 GB, zero publisher MD5s) into model-ready features on
the pinned GFC 30 m grid and the 90 m block grid: road density and distance-to-road from OSM extracts, and
elevation and slope from SRTM v4.1, feeding the `contagion+static` and `full_without_sar` arms.

**Corrections carried from review.** v1 claimed the approved §8 radii were already in metres; they are
**px** (`ANALYSIS-DRIVER-PLAN.md:194`). v2's halo verification used 59 px, but one east–west pixel at
23.25° is 25.57 m, so `R_MAX` + one cell = 1525.6 m needs **60 px** — the conclusion (28 tiles) survived,
the arithmetic did not. Both are fixed below.

## Approach

### 1. Sequencing — the audit runs FIRST and its outcome is preregistered

The freeze in step 3 is a **deviation from committed code** (`static_layers.py:72` returns
`date(origin,1,1)`), so it cannot be adopted on judgement after seeing results. Order is fixed:

1. Build the audit tooling and the tag cross-tab (steps 2–3.2). **No feature code, no registry change.**
2. Run the audit. Its outcome is read off the **decision table in 3.3**, which is frozen now.
3. **Only on FREEZE** is deviation 4 appended and the registry, schema manifest and tests mutated —
   atomically, in one commit. On PER-ORIGIN, no deviation is logged and the committed behaviour stands.
   On any DROP, the tier is removed from the schema.
4. Feature extraction begins only after (3).

### 2. Road tiers — three, enumerated literally, provisional until the cross-tab

| Tier | Accepted `highway` values (exact) |
|---|---|
| `engineered` | `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `motorway_link`, `trunk_link`, `primary_link`, `secondary_link`, `tertiary_link`, `unclassified`, `residential` |
| `track` | `track` |
| `service` | `service` |

`service` is separate from `track`: it mixes driveways and industrial forecourts with rural access.
2.1 **Cross-tab published before tiers are frozen:** count and centreline length by raw `highway` value,
    lifecycle prefixes (`disused:`, `proposed:`, `construction`), `surface`, `tracktype`, `access`, site
    and country. Lifecycle-prefixed and `access=private` ways are **excluded and counted**, not silently
    absorbed.

### 3. Roads vintage — audited against a frozen decision table

3.1 **What is measured.** For every site and tier, at origins 2020 and 2022, using identical clips: total
    centreline length, and every way's OSM **element id and version**, so Δlength decomposes into
    `new_id` (absent in 2020), `same_id_geometry_changed`, and `same_id_retagged` (moved into or out of
    the tier).
3.2 **Blinded imagery adjudication.** From the `new_id` ways, a **stratified random sample of n = 50 per
    tier** (or all, if fewer), allocated across sites proportional to each site's `new_id` length with a
    floor of 2 per contributing site. Each is labelled against imagery at both dates —
    **construction** (absent on 2020 imagery), **pre-existing-unmapped** (visible on 2020 imagery), or
    **ambiguous** — by an adjudicator blind to site identity and to which hypothesis each label supports.
    Imagery source and dates are recorded per sample.
3.3 **The decision table, frozen before the audit runs.** Let `p` be the `new_id`-length-weighted share
    labelled *pre-existing-unmapped*, with **ambiguous counted as construction** (conservative: it argues
    against freezing). Let `q` be the Wilson 95 % lower bound on `p`.

    | Condition | Outcome |
    |---|---|
    | `q ≥ 0.50` | **FREEZE** that tier at 2020-01-01 for all origins |
    | `q < 0.50` and upper bound `< 0.50` | **PER-ORIGIN** snapshots for that tier; no deviation logged |
    | CI straddles 0.50 | **PER-ORIGIN**, and the ambiguity is disclosed |
    | tier Δlength `< 5 %` of its 2020 length | **FREEZE** (drift immaterial either way) |

    Outcomes are **per tier and global** — never per site (see 3.4). The measured single-site signal
    (+30 % track, +0.1 % engineered) is the hypothesis under test, not evidence the plan leans on.
3.4 **No site is ever excluded on completeness grounds.** v2 said sites failing a completeness audit would
    be excluded or masked — but the audit above measures *temporal drift*, not *how much of the 2020
    network was unmapped*, and those are different quantities. Worse, dropping sites would disturb the
    frozen 36-site population and could encode biome through masking, which is precisely the failure that
    retired the earlier risk study. **All 36 sites are retained unconditionally.** Road-map completeness
    stays **unknown** and no decision is taken on it without an independent coverage source.
3.5 **Freezing relocates rather than removes the confound**, and the feature is named for what it is:
    **"mapped centreline network as of 2020-01-01"**. A fixed snapshot still carries spatial variation in
    2020 mapping effort, and its staleness grows toward 2022.

### 4. Roads are a distinct metric kernel family; approved contagion untouched

Approved contagion stays in **pixels** (`{1,3,5,10,20,50}` px, `R_MAX = 50 px`) — unchanged, no deviation.
Road kernels are a **separate family in metres**, unit-suffixed in the schema, never compared
radius-for-radius with contagion. Aligning contagion to metric remains available as a future deviation and
is **not** taken here.

**The metric halo is scoped to road extraction only** (v2 wrongly said "for both families"). Rationale for
metric on the road side: the GFC grid is geographic, so pixels are 27.8 m north–south but 27.8·cos(φ) m
east–west — up to 8.1 % anisotropy across latitudes −23.25 to +18.33, correlated with biome.

### 5. Halo — geodesic, not pixel-approximated

The road halo is a **geodesic buffer of `R_MAX` + one analysis cell** around each site box, computed with
`pyproj.Geod`, not a pixel count. v2's 59 px was an approximation and was off by one (60 px is needed at
the worst latitude). A startup assertion re-derives the required SRTM tiles and OSM regions from the
geodesic buffer and **fails closed** if any is absent from the pinned inventory. Verified: the tile set is
28 at every halo from 51 to 66 px, so the acquired archive is sufficient — but the assertion re-checks it
rather than trusting this note.

### 6. Road features — operator frozen, not just the locations

Per tier ∈ {`engineered`, `track`, `service`}:

| Feature | Definition | Parameters |
|---|---|---|
| `road_density_{tier}_{r}m` | centreline length (m) within radius `r` ÷ disc area (km²) | `r ∈ {30, 90, 150, 300, 600, 1500}` m |
| `dist_nearest_road_{tier}` | distance (m) to nearest centreline, censored at `R_MAX` | 1500 m |
| `road_absent_within_rmax_{tier}` | `uint8` censoring flag | — |

**Evaluation locations** are the immutable GFC cell centres, projected *into* the site CRS; results return
keyed by `(gfc_row, gfc_col)`. No raster is ever warped back.

**The operator is frozen too** — v2 named the locations but left the computation undefined:
- **Primary: exact vector.** Roads are indexed in a `shapely` `STRtree`; `dist_nearest_road` is exact
  point-to-line distance to the nearest candidate within `R_MAX`; `road_density` is the exact clipped
  length of the network inside each point-centred disc. Both are exact, with no discretisation.
- **Runtime gate.** ~880 k cells × 3 tiers × 6 radii is potentially prohibitive. A benchmark on one site
  fixes the projected cost; **above a frozen ceiling of 4 h per site-scale**, the run switches to the
  approximation below.
- **Approximation, if the gate trips:** a metric raster at **10 m** in the site CRS, roads rasterised by
  exact per-cell clipped length (not cell-count), distance by exact Euclidean transform on that raster,
  densities by summed-area convolution over disc kernels. It is **validated against the exact vector
  oracle on a 5 000-cell random sample per site and radius**, and must agree within **1 %** of the disc
  area for density and **one raster cell** for distance, or the run fails.

### 7. Coverage — pinned polygons, and completeness declared unknown

v2 required PBF coverage polygons that **were never acquired**: the inventory holds only `roads` and
`terrain` kinds, and a PBF header bbox is not the extraction polygon, so the feature was not reproducible
from the certified archive.

7.1 **Acquire and pin the Geofabrik `.poly` extraction polygons** for the 12 resolved regions as
    *auxiliary* inputs, in a **separate** write-once auxiliary inventory. The existing
    `static_archive_inventory.json` is **not** overwritten.
7.2 `roads_source_available` is derived per cell from the **union of those polygons**, and records whether
    the extract covers that cell — a property of the data distribution, not an inference about survey
    effort. A cell is available only if its **full `R_MAX` disc** lies inside the union, so an edge cell
    with a truncated neighbourhood is marked unavailable rather than silently under-counted.
7.3 **Road-map completeness is represented as unknown**, never estimated from unrelated features.

### 8. Terrain — one pipeline, with a validity mask carried end to end

1. **Mosaic** the required SRTM tiles over the geodesic halo; nodata preserved, never filled.
2. **Warp elevation** to a metric 90 m grid in the site CRS, **bilinear**, carrying an explicit
   **source-validity mask** warped by **nearest** alongside it — bilinear alone would renormalise over
   valid neighbours and silently invent values beside voids.
3. **Horn slope** on that grid. Horn's kernel spans 3×3, so a cell's slope is undefined if **any** of its
   nine inputs is invalid; the slope validity mask is the 3×3 erosion of the elevation mask.
4. **Sample to GFC cell centres**, bilinear, with each feature carrying **its own** validity: a point whose
   bilinear support touches an invalid cell yields `NaN` for that feature.
5. **Feature-specific undefined flags** — `elevation_undefined` and `slope_undefined` are separate, because
   near a void a cell can have valid elevation and undefined slope. `terrain_covered` is reserved for
   **source-footprint availability** only.
6. **Disclosed in the manifest:** 30 m values are interpolated 90 m estimates, not 30 m measurements.

### 9. Extraction — one interleaved scan, deduplicated, checkpointed

9.1 **Parser configuration is pinned, because the defaults do not supply what this plan needs.** GDAL's
    stock `osmconf.ini` **disables `osm_version`**, which the audit in step 3 depends on. A repo-local
    `osmconf.ini` sets `osm_version=yes` and the required tag list, and its **sha256 is recorded** in every
    cache key and in the manifest.
9.2 **Dataset-level interleaved reading** (`GetNextFeature()` / `ogr2ogr` interleaved import), which is what
    GDAL documents for large PBFs. v2's "one streaming scan" was not achieved by per-layer pyogrio reads,
    which re-traverse the file per layer.
9.3 **Deduplication key is `(origin, type, id)` — not `(type, id, version)`.** Including version *retains*
    both copies when overlapping extracts hold the same way at different versions. Rule: within an origin,
    **highest version wins**; same-version fragments split at an extract boundary are **geometrically
    unioned**; cross-origin lineage for split/merged/renumbered ways uses geometry overlap plus changeset,
    and unresolved cases are **counted and reported**, not silently dropped. Assert **zero duplicated
    centreline length** after dedup.
9.4 **Content-addressed cache** keyed by input sha256 + code tree + **resolved GDAL/PROJ/pyogrio versions +
    `osmconf.ini` hash**, since those determine the parsed geometry. Atomic stage publication, an exclusive
    run lock, per-PBF and per-site checkpoints, bounded-memory streaming. Phase B needed six passes under
    this environment's time limits; a design that cannot checkpoint will not finish.
9.5 **Pin the geospatial stack** in `requirements.txt` — currently absent entirely.

### 10. Output schema

Keyed **`(site_id, scale, block_row, block_col)`**, where at 30 m the block indices *are* the native GFC
`(row, col)`, and at 90 m they are `(row // 3, col // 3)` under a **global 3×3 alignment anchored at the
pinned GFC grid origin** — so the key is unambiguous rather than leaving top-left/centre/block-index to the
implementer. Joins to the approved `(θ, site, origin, scale)` tables are asserted **cardinality-preserving**.

**90 m aggregation is per field:** continuous → mean over non-NaN; categorical → majority, ties to smallest
category code; flags → majority; with `valid_count` and `any_missing` carried, and `*_undefined` set only
when all nine inputs are undefined.

### 11. Provenance

Every input **rehashed before parsing** and checked against the inventory; mismatch fails closed. Copying
the inventory's hashes would certify bytes nobody re-read, and that inventory has **zero publisher MD5s**.
The manifest records recomputed input hashes, the inventory hash and its weak-anchor disclaimer verbatim,
the auxiliary `.poly` inventory hash, the code tree SHA, resolved GDAL/PROJ/pyogrio versions, the
`osmconf.ini` hash, tier lists, radii, `R_MAX`, the vintage decision with its audit outcome and
deviation-4 reference (if taken), the projection rule with measured error, the operator actually used
(exact or approximate) with its validation result, and output hashes.

### 12. Projection

Per-site **azimuthal-equidistant** centred on the site. Worst-case **pairwise distance, line-length and
disc-area error** are computed across the full haloed window at every radius and must be **≤ 0.5 %**;
above that the site switches to a **deterministic fallback: the UTM zone containing the site centroid**
(v2 left "transverse-Mercator or UTM" to the implementer). Substitutions are recorded per site.

### 13. Sensitivity — feature drift only

Feature-level drift summaries per site and tier across origins: length, density and distance
distributions. Model-arm impact requires fitting and is out of scope here.

## Key decisions & tradeoffs

- **The audit precedes and decides the freeze**, against a table frozen before results are seen. The
  alternative — freezing now and auditing later — is threshold shopping, which this repo has retracted once.
- **All 36 sites retained unconditionally.** Completeness-based exclusion would disturb the frozen
  population and risk encoding biome; the audit does not measure completeness anyway.
- **Exact vector operators with a benchmarked runtime gate**, and an oracle-validated raster fallback —
  rather than an unstated operator behind well-defined locations.
- **Dedup on `(origin, type, id)`**, because versioning the key defeats deduplication.
- **Coverage polygons pinned as auxiliary inputs**, since the certified archive does not contain them.
- **Separate validity masks per terrain feature**, because elevation and slope fail at different distances
  from a void.
- **Roads metric, contagion untouched** — two conventions, named rather than hidden.

## Risks / open questions

- **The audit may return PER-ORIGIN**, overturning the grilled preference for a freeze. That is the point
  of gating it, but it means the vintage is genuinely not settled until the audit runs.
- **Blinded adjudication needs an imagery source with 2020 and 2022 coverage** at these sites; if none is
  available for some sites, those samples are unresolvable and count as ambiguous (against the freeze).
- **The exact-vector operator may be too slow** and the fallback may fail its 1 % validation, in which case
  the operator question reopens.
- **Cross-origin way lineage** (split/merged/renumbered) may not resolve cleanly; unresolved cases are
  reported, but a large unresolved fraction would weaken the audit.
- **`service` may be mostly urban noise** at these sites — the cross-tab decides.
- **Runtime for the 1.4 GB extracts is unmeasured** (20 s on 79 MB).

## Out of scope

- **Contagion features** (Phase C1, sealed worker) and anything touching `lossyear`.
- **Rivers, ecoregion, climate** — already pinned; re-checksummed, not recomputed.
- **WDPA and PEATMAP** — excluded by deviation 3.
- **Model fitting, evaluation, the embargo**, and model-arm impact.
- **Any modification** to the 12-site v11 path, `risk/`, the sealed worker, the frozen Specification W
  artifacts, or either certified archive.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: literal tag membership with lifecycle/access
   exclusion counts **and lengths**; the frozen audit decision table evaluated against synthetic inputs at
   every branch including the CI-straddles case; geodesic halo derivation failing closed on a missing tile;
   exact-vector distance and clipped-length against hand-computed geometries; the raster fallback validated
   against the exact oracle within 1 % / one cell; dedup asserting zero duplicate length across a synthetic
   two-extract overlap **and** correct highest-version resolution; `roads_source_available` false for a
   cell whose full disc leaves the polygon union; terrain validity masks giving valid elevation with
   undefined slope beside a void; per-field 90 m aggregation with the 3×3 anchor; cardinality-preserving
   join against an approved table; `osmconf.ini` hash present in cache keys.
2. The tag cross-tab, and the audit artifact with per-site/per-tier/per-origin lengths, id/version deltas,
   the blinded sample with imagery dates, and the decision-table outcome per tier.
3. The auxiliary `.poly` inventory, write-once, leaving `static_archive_inventory.json` untouched.
4. The feature manifest with recomputed hashes, pinned stack, measured projection error, and which operator
   was used.
5. Feature parquet for all 36 sites at both scales.
6. Feature-drift summaries, labelled exploratory.

Josh runs the proof. Reviewer and builder claims are advisory.
