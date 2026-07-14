# Plan Review Log: Within-Frontier Deforestation Risk (companion paper)

Act 1 (grill) complete — plan locked with the user on 2026-07-13. MAX_ROUNDS=5.

## Act 1 — decisions settled in the grill

| # | Question | Decision |
|---|---|---|
| 0 | Reuse the ResNet50 CNN? | **No** — settled by Claude from the repo's own evidence (CNN fails out-of-biome, loses to NDVI 5/8 sites). Features + GBM instead. |
| 1 | New section of existing paper, or companion? | **Separate companion paper** |
| 2 | Feature window vs prediction horizon | **Features 2016–2020 → predict 2021–2024** (5 annual points, 4-yr horizon, 32 new downloads) |
| 3 | At-risk mask definition | **Hansen treecover2000 ≥30% minus loss ≤2020** (independent of the Sentinel-2 features → no circularity) |
| 4 | Ablation arms | **5 arms**: base-rate / contagion / condition-static / condition-trajectory / combined |
| 5 | Model class | **HistGradientBoosting primary + logistic regression for interpretation** |
| 6 | Cell grid | **stride=64, non-overlapping** (independent cells; i.i.d. bootstrap becomes legitimate) |
| 7 | Metric & aggregation | **Average precision + lift over base rate; Wilcoxon signed-rank across n=8 sites** |
| 8 | Positive label | **GFC loss ≥25% of cell** (primary), >0% and ≥50% as sensitivity |

Two threats added by Claude during plan-writing, not raised in the grill:
- **Cross-year radiometric drift** could manufacture a fake "degradation trend" (the Kalimantan
  exclusion is proof this is real) → stable-forest pseudo-invariant normalization + with/without
  sensitivity.
- **Hansen supplies both contagion features and labels** → correlated errors; flagged as an open
  question with a proposed sensitivity arm.

## Round 1 — Codex (gpt-5.6-sol, xhigh)

The plan is not sound enough to implement as written. The core ablation cannot isolate condition history from prior clearing, and several validation assumptions are statistically invalid.

1. **The primary contrast does not exist.** The plan requires `(B+C) vs E`, but defines only A, B, C, D, and `E=B+C+D`; `C vs D` is non-nested and cannot estimate history’s incremental value ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:118>)).  
   Fix: Add `B+C` and use `B+C` versus `B+C+D_history` as the prespecified primary contrast.

2. **The feature blocks do not represent clean constructs.** B includes `treecover2000`—forest stock, not contagion—while D includes minimum NDVI level and other snapshot-dependent quantities.  
   Fix: Put baseline forest stock in a common adjustment block included in every arm, and restrict the history block to changes conditional on the 2020 snapshot.

3. **Condition features directly encode prior clearing.** At-risk cells may already have 24.9% Hansen loss, yet NDVI statistics are computed over the whole cell, so slopes and low tails can measure 2016–2020 clearing rather than pre-clearing forest condition.  
   Fix: Compute condition on a fixed support of pixels classified as forest and not lost through 2020, with an additional sensitivity restricted to cells having zero prior loss.

4. **The contagion baseline is a straw man.** Pooling all loss from 2001–2020 discards the strongest likely predictors: recency, frontier direction, and recent neighborhood expansion.  
   Fix: Add distance and kernel density for 1-, 3-, and 5-year loss windows, time since nearest loss, and neighborhood loss trend.

5. **An ablation cannot establish a physical separation between condition and contagion.** Edge effects, roads, canopy fragmentation, and unmeasured access variables affect both blocks, so a performance delta is predictive—not causal—evidence.  
   Fix: Claim only incremental predictive information conditional on measured contagion, or add spatial matching/orthogonalization if a causal “condition effect” is intended.

6. **The normalization explicitly leaks test outcomes.** Selecting invariant pixels using zero 2021–2024 loss uses held-out labels; being a site-level scalar does not make label-dependent preprocessing acceptable ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:82>)).  
   Fix: Define every reference population using data through 2020 only and reserve the future-defined version solely as a clearly labeled post-hoc diagnostic.

7. **The “stable forest” normalization is circular.** Forest with no stand-replacement loss can still undergo the degradation or drought response being studied, so anchoring its annual median can normalize away the hypothesized signal; an additive NDVI offset also cannot prove that remaining cell-level trends are real.  
   Fix: Use cloud/atmospheric QA and pre-2021 pseudo-invariant targets to estimate robust multiband transformations, and describe residual trends as potentially ecological rather than proven ecological change.

8. **The QC rule selects on the predictor of interest.** Dropping a site because “stable-forest” NDVI differs by 0.15 can remove genuine widespread degradation and preferentially retain radiometrically quiet sites.  
   Fix: Base rejection on independent sensor-quality variables—clear-observation count, SCL cloud/shadow fraction, nodata, and acquisition geometry—and treat anomalous NDVI as a flagged sensitivity, not an exclusion rule.

9. **The current composite pipeline does not mask clouds per pixel.** It filters tile metadata and takes a temporal median ([download_sites.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/deforestation/download_sites.py:41>)); the diagnostics count clouds as valid and use a scene-relative brightness heuristic ([diagnose_composites.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/deforestation/diagnose_composites.py:29>)). Copernicus documentation treats `maxCloudCoverage` as a tile-level filter and recommends SCL-based pixel masking for cloud, cirrus, and shadow. ([Copernicus cloud-mask example](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html))  
   Fix: Mask and dilate SCL cloud, cirrus, shadow, snow, defective, and nodata pixels before compositing, and retain per-pixel clear-observation counts.

10. **The acquisition-risk statement identifies the wrong thin year.** Sentinel-2A was the only spacecraft throughout 2016; Sentinel-2B began acquisitions in March 2017, so 2016 is at least as problematic as 2017. ([Copernicus Sentinel-2B record](https://sentinels.copernicus.eu/-/second-colour-vision-satellite-for-copernicus-launched))  
    Fix: Re-query and preferably regenerate 2016 with the exact same processing graph as 2017–2020 rather than treating the prior composite as automatically comparable.

11. **“June–September dry season” is not a uniform phenological regime across Amazon, equatorial peatland, Congo rainforest, and deciduous dry forest.** Different acquisition dates and observation counts can manufacture annual trends even within the same four-month window.  
    Fix: Define a site-specific climatological compositing season before examining outcomes and record median acquisition date, count, solar geometry, and within-composite dispersion for every year.

12. **Cross-year co-registration is unspecified.** The existing NDVI code reads the second raster while discarding its transform and CRS, then assumes matching array indices ([ndvi_baseline.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/deforestation/ndvi_baseline.py:61>)); that is unsafe for five-year cell trajectories.  
    Fix: Create one master 10 m grid per site, warp every annual composite onto it, and assert identical CRS, transform, dimensions, and pixel alignment before feature extraction.

13. **Hansen loss is not equivalent to deforestation.** GFC reports gross stand-replacement tree-cover loss and its `treecover2000` band includes all vegetation taller than five metres, including plantations; fire, harvest, and natural disturbance can therefore be positives. ([Hansen GFC documentation](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12))  
    Fix: Call the outcome “Hansen-detected tree-cover loss” unless an independent land-use-change layer or manually interpreted validation subset establishes deforestation.

14. **The at-risk mask misuses continuous canopy cover.** `mean(treecover2000) ≥30%` is not “30% of the cell is forest,” is stale at 2020, ignores regrowth, and makes a whole-cell 25% loss threshold depend strongly on how much forest was initially available.  
    Fix: Threshold tree cover per Hansen pixel, apply a minimum connected forest area, subtract pre-2021 loss, and express future loss relative to remaining 2020 forest area or explicitly defend a total-cell-area estimand.

15. **Hansen-to-Hansen prediction remains an unresolved material confound.** Shared spatial and temporal errors can make B appear unusually successful; an imagery-derived version of the same prior clearing is not automatically an independent validation.  
    Fix: Make an independent reference/manual audit mandatory or restrict the conclusion to predicting future GFC detections from earlier GFC detections.

16. **Spatial features are censored at arbitrary box edges.** Ring fractions omit neighboring cells outside the scene, and nearest-loss distance may be infinite or spuriously long; Rondonia also touches a Hansen tile boundary.  
    Fix: Download buffered Sentinel and mosaicked Hansen context, compute predictors on the buffer, cap distance with a censoring indicator, and evaluate only the unbuffered interior.

17. **Several required edge cases have no definition.** Empty stable-reference sets, no prior-loss cell, zero-variance skew, nodata-heavy cells, tied year-of-minimum, and held-out sites with zero positives make features or AP/lift undefined.  
    Fix: Prespecify minimum sample counts, missing-value encodings, distance caps, tie rules, positive-count requirements, and fail/report behavior for every such case.

18. **Non-overlap does not make cells independent.** Forest loss and prediction errors remain spatially autocorrelated over kilometres, so the proposed i.i.d. bootstrap is invalid despite eliminating pixel overlap ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:136>)).  
    Fix: Use a spatial block bootstrap with block size chosen from an empirical residual-correlation range and distinguish within-site map uncertainty from across-site generalization uncertainty.

19. **LOSO at eight purposively selected boxes supports only an eight-box case study.** Most folds still train on another site from the same biome, the boxes were confirmed using GFW ([sites.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/deforestation/sites.py:5>)), and dropping to six makes inference still weaker.  
    Fix: Describe results as out-of-site performance on these boxes, add descriptive leave-one-biome-out results, and expand using a pre-2021 sampling frame before making biome- or frontier-level claims.

20. **The “never-seen future” and preregistration language is false.** The prior study already analyzed 2024 imagery and 2016–2024 Hansen outcomes at the same sites ([results_summary.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/paper/results_summary.md:134>)).  
    Fix: Call this a retrospective temporal holdout, document all outcome-informed design choices, and use genuinely untouched sites for confirmatory evaluation.

21. **The tuning argument is statistically wrong.** Hyperparameter tuning inside an inner site-group CV using only the seven training sites does not leak; arbitrary fixed GBM settings can instead create a false null, and model capacity alone cannot prove signal absence ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:128>)).  
    Fix: Use regularized logistic regression as the simple primary model and an identically budgeted nested site-level tuning procedure for GBM as sensitivity.

22. **AP/lift and “probability” reporting are mishandled.** Lift remains unstable at tiny prevalence, is undefined at zero prevalence, and balanced class weights generally produce uncalibrated scores; a universal 0.02 AP threshold has no constant operational meaning.  
    Fix: Prespecify zero-positive handling, report paired within-site AP deltas plus precision/recall at a fixed alert budget, and calibrate predictions in inner group CV or call them risk scores.

23. **Permutation importance does not solve correlated-feature attribution.** Marginally permuting one correlated percentile or contagion feature can assign importance arbitrarily, while multicollinear logistic coefficients are not readable “drivers” ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:142>)).  
    Fix: Use grouped or conditional spatial permutation by feature family and report coefficient stability across folds as associations, not causal drivers.

24. **The negative claim would exceed the measured feature space.** Five annual RGB/NIR NDVI summaries omit SWIR moisture/burn information, red-edge structure, and sub-annual dynamics, so a null cannot establish that “satellite condition history” is unhelpful generally.  
    Fix: Either add prespecified NDMI/NBR or related SWIR features and denser within-season summaries, or narrow every conclusion to these five annual RGB/NIR composites at 640 m.

VERDICT: REVISE
### Claude's response — Round 1

**Accepted (22 of 24), materially rewriting the plan:**

- **#3 (fixed pixel support) — the critical catch.** Whole-cell NDVI stats on a cell with up to 24.9%
  prior loss would have measured *past clearing* as "condition trajectory," falsely confirming the
  hypothesis. Condition features now computed on one fixed pixel set (forest-at-2020, unlost-through-2020),
  same pixels all 5 years, plus a zero-prior-loss sensitivity.
- **#9 (no per-pixel cloud masking).** Correct and serious: `max_cloud_cover` is a tile-level metadata
  filter; the median composite retains cloudy pixels. Added SCL mask + dilation + per-pixel
  clear-observation counts. This is a fix to an existing pipeline flaw, not just the new work.
- **#1 (non-nested contrast).** True — `C vs D` cannot estimate incremental value. Arms are now nested;
  primary contrast is `S+B+C` vs `S+B+C+D`.
- **#4 (straw-man contagion).** Accepted — added recency, time-since-loss, 1/3/5-yr windows, neighborhood
  trend. Beating a hobbled baseline would have proven nothing.
- **#20 ("never-seen future" / "pre-registered" false).** Fully accepted; I wrote something untrue. The
  prior study analyzed 2024 imagery and 2016–24 Hansen at these sites. Reframed as a retrospective
  temporal holdout with an explicit "outcome-informed choices" disclosure section.
- **#6 (normalization leaked test labels).** Accepted — reference population now defined on ≤2020 data only.
- **#7, #8 (normalization/QC circularity).** Accepted — QC gate now uses sensor-quality variables only;
  NDVI anomaly is a flagged sensitivity, never an exclusion.
- **#18 (non-overlap ≠ independence).** Accepted; I over-claimed. Switched to a spatial block bootstrap.
- **#21 (tuning argument wrong).** Accepted — inner site-grouped CV does not leak, and fixed arbitrary
  hyperparameters risked a *false null*. LR primary + nested-tuned GBM sensitivity.
- **#24 (null would exceed feature space).** Accepted, and went further: added SWIR (NDMI/NBR) rather than
  only narrowing the claim. A null on an NDVI-only feature set would be worthless.
- **#2, #5, #10, #11, #12, #13, #14, #15, #16, #17, #19, #22, #23** — all accepted as written
  (clean feature blocks; predictive-not-causal framing; 2016 is the thin year, not 2017; site-specific
  seasons; master-grid co-registration; "Hansen-detected tree-cover loss"; per-pixel forest mask + label
  relative to remaining forest; buffered extent; prespecified edge cases; 8-box case-study framing;
  ΔAP + alert-budget metrics; grouped permutation importance).

**Partially rejected (2), with reasons:**

- **#15 — "make an independent manual audit *mandatory*."** Rejected as stated: a full independent audit
  of ~12,800 cells is not feasible for this project. Adopted instead a **stratified ~100-cell manual
  audit** to *estimate* label validity, and where it cannot resolve the confound, the claim is explicitly
  **restricted** to "predicting future GFC detections from earlier GFC detections + imagery" — which was
  Codex's own alternative fix.
- **#19 — "expand the site set before making any claims."** The claim-restriction is accepted in full
  (8-box case study, leave-one-biome-out added as descriptive). The *mandatory expansion* is deferred:
  it roughly doubles the project. Logged as the highest-leverage open question for Josh to decide.


## Round 2 — Codex

The revision addresses nearly all major prior findings. The two partial acceptances are reasonable:

- The ~100-cell audit is adequate as supporting evidence because the main claim is now explicitly limited to predicting future GFC detections.
- Site expansion is not an implementation blocker because the plan consistently frames this as an eight-box case study, not biome-level inference.

A few material issues remain.

1. **The normalization interpretation is internally contradictory.** The plan acknowledges normalization can remove real degradation, but then says a result flip proves radiometric artifact ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:121>)); either normalization or non-normalization could be wrong.  
   Fix: Prespecify a three-way rule—consistent results support the conclusion, discordant results are inconclusive, and neither version is selected post hoc as the headline.

2. **No primary preprocessing analysis is designated.** “With and without normalization” produces two candidate primary results, leaving room to choose the more appealing one.  
   Fix: Designate one pipeline as primary and the other as sensitivity, or require concordance across both before claiming that history adds value.

3. **The normalization algorithm remains underspecified.** It does not name the reference year/composite, regression direction, robust estimator, minimum reference count, coefficient bounds, or fallback when the reference population is empty.  
   Fix: Lock a complete transformation formula and deterministic failure/fallback rule before downloading or inspecting trajectories.

4. **The supposedly fixed QC gate has no numerical thresholds.** Clear-observation, cloud/shadow, nodata, and solar-geometry cutoffs—and the site-specific seasonal windows—remain undecided ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:73>), [PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:82>)). These decisions determine which sites survive.  
   Fix: Add a table of exact seasonal dates and numerical QC thresholds before running acquisition or QC.

5. **The future-loss numerator is not explicitly restricted to the denominator’s forest mask.** GFC can record loss where `treecover2000 < 30`, so `loss(2021..2024) / forest_2020_area` could include numerator pixels excluded from the denominator and can theoretically exceed one ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:101>)).  
   Fix: Define the numerator as `treecover2000≥30 AND lossyear∈[21,24] AND datamask=valid`, using exactly the same eligible-pixel universe as the denominator.

6. **“Forest at 2020” is still too strong a name.** The mask is actually “year-2000 tree cover with no GFC-recorded loss through 2020”; it omits regrowth and inherits GFC false negatives.  
   Fix: Rename it `GFC_eligible_forest_2020` or “GFC baseline-tree-cover risk set” and state that it is not an independent 2020 forest map.

7. **Cross-resolution resampling is unspecified.** B11/B12 and SCL are natively 20 m, Sentinel reflectance is being placed on a 10 m grid, and categorical Hansen `lossyear` must not be interpolated like reflectance ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:90>)).  
   Fix: Prespecify bilinear/area resampling for reflectance and nearest-neighbor or area-overlap aggregation for SCL, observation counts, forest masks, and `lossyear`, while describing SWIR’s effective resolution as 20 m.

8. **The spatial bootstrap needs a reproducible algorithm, not “chosen from the correlogram.”** That leaves block size selectable after seeing residual structure and does not state how zero-positive resamples are handled.  
   Fix: Define the correlation threshold, distance-bin procedure, minimum/maximum block size, use identical paired resamples for both arms, and prespecify rejection or handling of zero-positive replicates.

9. **Training and inner-CV weighting are undefined.** Pooled cell loss will give sites with more eligible cells greater influence even though the inferential unit and headline aggregation treat sites equally.  
   Fix: State whether the target is a random cell or a random site; for the current site-level estimand, give each training site equal total weight and tune on mean held-site AP.

10. **The alert-budget interpretation uses the wrong horizon and unit.** Predictions cover cumulative 2021–2024 loss, not “next year,” and cell-level recall is not necessarily the share of clearing area captured ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:169>)).  
    Fix: Say “four-year positive cells captured,” or additionally calculate area-weighted capture using the number of future-loss pixels.

11. **The manual audit still needs a sampling protocol.** “Stratified random” does not define strata, allocation, weighting, imagery dates/source, or whether interpretation is blinded to model predictions ([PLAN.md](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/PLAN.md:190>)).  
    Fix: Stratify by site and GFC loss fraction, retain inclusion probabilities for weighted estimates, require before/after imagery, and blind interpretation to risk scores.

12. **The sub-annual statement remains unjustifiably categorical.** Fixed monthly windows can be radiometrically compared with appropriate masking and normalization; they are merely outside this study’s chosen scope.  
    Fix: Replace “not radiometrically comparable” with “not pursued because observation density and project scope do not support a defensible sub-annual analysis.”

The experimental question, nested ablation, leakage controls, claim boundaries, and core validation design are now fundamentally sound. However, normalization could still reverse the headline with no valid interpretation rule, and unspecified QC thresholds could change the site sample post hoc. Those are implementation-level decisions that should be locked first.

VERDICT: REVISE
### Claude's response — Round 2

Codex's own summary: *"The experimental question, nested ablation, leakage controls, claim boundaries,
and core validation design are now fundamentally sound."* All 12 remaining findings are the same
species of problem — **free parameters that could be chosen post hoc to flatter the result**. All 12
accepted; every value is now locked in a new **§L — LOCKED PARAMETERS** section, committed before any
data is touched.

- **#1, #2 (normalization could flip the headline with no interpretation rule)** — the sharpest of the
  round. Fixed with **L4**: primary = normalized; a positive claim requires **concordance across both
  pipelines**; discordance is reported as **INCONCLUSIVE**. Neither version can be promoted post hoc.
- **#3 (normalization underspecified)** → **L3**: reference year 2020, Theil–Sen robust fit per band,
  PIF definition, min 5,000 pixels, gain/offset bounds, no fallback (fail → drop site).
- **#4 (QC gate had no numbers — it silently decides which sites survive)** → **L1** (site-specific
  compositing windows table) and **L2** (six numeric thresholds).
- **#5 (numerator not restricted to denominator's universe)** → **L5**: one eligible-pixel universe
  (`datamask==1 AND treecover2000≥30`); since `lossyear` is single-valued, numerator ⊆ denominator and
  the ratio is bounded in [0,1] by construction.
- **#6 ("forest at 2020" overclaims)** → renamed `GFC_eligible_forest_2020` throughout, with an explicit
  statement that it is not an independent 2020 forest map.
- **#7 (categorical layers must not be interpolated)** → **L6** resampling table; Hansen rasters are
  never warped.
- **#8 (bootstrap block size selectable after seeing residuals)** → **L7**: deterministic rule
  (threshold 0.1, clamp [2,8]), 1,000 reps, seed 42, **paired resamples across arms**, explicit
  zero-positive handling.
- **#9 (weighting undefined)** → **L8**: estimand is a random *site*; equal site weight in training,
  inner-CV objective is mean held-site AP.
- **#10 (alert-budget horizon/unit wrong)** → corrected to "share of **2021–2024** positive cells
  captured" (4-year cumulative, not "next year"), plus **area-weighted capture** by future-loss pixels.
- **#11 (audit protocol undefined)** → **L9**: 24 strata (8 sites × 3 loss bins), ~96 cells, inclusion
  probabilities retained, before/after imagery, **blinded to risk scores**.
- **#12 (sub-annual claim too categorical)** → softened; not pursued for observation-density and scope
  reasons, not asserted impossible.

No rejections this round.

## Round 3 — Codex

**VERDICT: REVISE.** Four blockers (L4, L5, L7, L8) plus partials on L2/L3/L6/L9.

1. **L4 blocker** — "the ΔAP CI excludes 0" is undefined: eight per-site CIs exist but no locked
   site-aggregate effect or CI; "excludes zero" also fails to require a positive direction.
2. **L5 blocker** — at-risk denominator is wrong: requiring eligible forest ≥25% of `U`, where `U`
   already contains only tree-cover pixels, admits a cell holding one surviving forest pixel.
3. **L7 blocker** — residual-producing arm, moving-vs-fixed blocks, edge handling, random origins all
   still selectable.
4. **L8 blocker** — LR/GBM grids, candidate count, tie-breaking, zero-positive inner-fold behavior
   unspecified.
5. **Reflectance scale** — existing pipeline treats L2A as 0–10,000 DN while L2's offset bounds assume
   0–1 reflectance.
6. **`build_reference` is NOT area-overlap weighted** — it slices a rectangular block and takes an
   unweighted pixel mean. The plan described it incorrectly.
7. **Fixed condition support computationally undefined** — no rule for how 30 m Hansen pixels select
   10 m Sentinel observations.
8. **3 km buffer < 3.2 km contagion radius** (`b_ring5` = 5 × 640 m).
9. Feature formulas (distance cap, ring denominator, tail cutoff, brightness, clear-count summary) tunable.
10. Class-balancing zero-class behavior; sparse audit strata; L1 wording ("before any outcome is
    inspected" is false — they were).

### Claude's response — Round 3

All 12 accepted; no rejections. Added **L0** (reflectance scale), rewrote **L2–L9**, added **L10**
(full feature dictionary with exact formulas and degenerate-case rules) and **L11** (4 km buffer).
Notable: **L5 was genuinely broken** and Codex was right — the denominator is now `datamask==1` valid
**land** area, not `U`. Corrected the false claim about `build_reference`. Locked the Hansen→Sentinel
overlay as pixel-center containment of a boolean mask.

## Round 4 — Codex

**VERDICT: REVISE.** *"The nested ablation, labels, fixed support, weighting, tuning grids,
normalization rule, feature dictionary, and buffer are now implementation-grade."* Five material gaps:

1. **L7 under-blocks ranges of 9–20 cells** — clamps every range to 8 but only flags UNRELIABLE beyond
   20, so a measured range of 15 gets an 8-cell bootstrap and an overconfident CI.
2. **Correlogram undefined** — residual type, correlation estimator, minimum pair count unspecified;
   these change `L`.
3. **Compositing graph still selectable** — no locked `max_cloud_cover`, SCL codes, or dilation kernel.
   These change trajectories *and* which sites pass QC.
4. **L0 self-contradictory** — clips to `[0,1.5]` but then claims features live in `[0,1]`.
5. **`b_density` has no denominator.**

Non-blocking: pin LR solver/package versions; clarify PIF count units; label the site-resampling CI
component as empirical eight-box uncertainty, not population inference; second audit interpreter;
specify the acquisition-metadata robustness model.

### Claude's response — Round 4

All 5 gaps and all 5 non-blocking items accepted. `L7` upper clamp removed (`L = max(2, measured
range)`; >12 cells or never <0.1 → UNRELIABLE; **any UNRELIABLE site now forces the L4 headline to
INCONCLUSIVE**). Correlogram fully specified (Pearson residual, Moran's I, integer cell lags, ≥500
pairs/bin). New **L12** locks the compositing graph (`max_cloud_cover=80` uniform — which also removes
the per-site override in `sites.py`; SCL classes `{0,1,2,3,8,9,10,11}`; single 100 m dilation kernel;
masked median; manual mask rather than unverifiable `mask_scl_dilation` defaults). L0 order of
operations fixed (measure out-of-range → fail >1% → clip to `[0,1]`; the `[0,1.5]` regime is gone).
`b_density` denominator = `datamask==1` valid-land pixels in the circle. Added the 10% duplicate-coded
audit subset and the explicitly-secondary acquisition-metadata robustness check.

## Round 5 — Codex

**VERDICT: APPROVED.**

> *"The plan is now sound enough to implement. The locked protocol closes the material degrees of
> freedom around eligibility, preprocessing, normalization, feature construction, tuning, spatial
> uncertainty, and headline selection. The ablation can now validly estimate history's incremental
> predictive value — within the explicitly restricted eight-box/GFC-detection estimand."*

Non-blocking implementation notes (all applied anyway):
- `b_time_since_loss` must take `max(lossyear)` over prior years `[1,20]` **only** — the literal
  wording could select a *future*-loss year from the same cell. Assert uncensored ∈ `[0,19]`.
- A CI reported `undefined` (not just `UNRELIABLE`) should also force the L4 headline to `INCONCLUSIVE`.
- Re-verify/re-clip reflectance to `[0,1]` **after** each Theil–Sen transform (L0's clip precedes it).
- Clip logistic probabilities away from 0/1 when computing Pearson residuals.
- Record pinned versions, Git commit, openEO backend version, and process graph in the results artifact.

### Claude's response — Round 5

All applied. **The first was not cosmetic — it was a live label leak**: an unrestricted
`max(lossyear)` in `b_time_since_loss` could pull a 2021–24 loss year (the label window) into a
predictor. Now restricted to `[1,20]` with an assertion. The others are defensive-coding fixes, applied
as written.

---

## Outcome

**APPROVED at round 5 of 5.** Codex is read-only throughout and never modified a file.
No code has been written. Awaiting Josh's sign-off.

## Rounds 6–8 — Codex (focused: L13 site expansion to n=20)

Josh chose to resolve the round-3 open question by **expanding the site set to n=20**. Three further
focused review rounds on the new L13 sampling frame and its knock-ons.

**Round 6 — REVISE.** Ten findings. The decisive one: **excluding candidate boxes within 50 km of the 8
legacy boxes indirectly imports outcome-informed selection into the supposedly clean frame** — the legacy
locations were themselves chosen with future GFW knowledge, so letting them carve holes in the frame
smuggles that knowledge back in. Also: "≥2% cumulative loss since 2001" does **not** establish an active
frontier as of 2020 (a box cleared entirely in 2001–03 qualifies); the biome-level compositing-window
rule breaks for basin-wide random sites (northern vs southern Amazon have opposing seasons); and the
"12-site sensitivity" was ambiguous — subsetting 12 test results from a model trained on all 19 others
still lets the purposive legacy sites shape the fitted model.

**Claude's response:** all 10 accepted. L13 restructured into L13.1–L13.8 (temporal firewall with a
pre-download SHA-256 hash of the frame and draw; reproducible lattice/biome universe; a **≥0.5% recent
loss 2016–2020** criterion so "active as of 2020" is actually true; **the frame is now built and drawn
with zero reference to legacy boxes, and where they collide the FRAME box is kept and the LEGACY box
dropped**; replacements fill only the 12 randomized slots; a failed legacy site is dropped, never
replaced from the frame queue; declared equal-group estimand; **two full LOSO analyses**, the frame-only
one trained and tuned on frame sites exclusively). L1's window is now a deterministic algorithm (driest
4 consecutive CHIRPS months, 1991–2020) applied uniformly; L8/Phase 5 parameterized to `n_training_sites`
(19/11, not 7).

**Round 7 — REVISE.** Five knock-ons. Most important: **a combined-vs-frame-only disagreement does NOT
identify selection bias**, since the two also differ in training size (19 vs 11). Also: the frame-only
bootstrap must resample *within* biome groups to match the equal-group estimand; external layers still
said "e.g."; the cross-stratum draw order was unlocked (the ≥50 km constraint spans groups, so biome
order changes the sample); and the legacy boxes had never been screened against L13.3 eligibility.

**Claude's response:** all 5 accepted. Every layer pinned with a version table + SHA-256; deterministic
round-robin draw order; within-group frame bootstrap; disagreement relabelled a
**"cohort-selection / training-composition sensitivity"**; new **L13.5b** applies L13.3 eligibility to the
legacy boxes too, so the combined cohort has one coherent eligibility definition and the cohorts differ
**only in how they were selected**.

**Round 8 — APPROVED.**

> *"L13 is sound enough to implement. The temporal firewall prevents any 2021–2024 outcome from entering
> frame construction, and applying the same pre-2021 eligibility criteria to legacy boxes produces a
> coherent combined cohort."*

Four non-blocking corrections, all applied — including a real logic error of mine: the decomposition I
proposed would have isolated *training composition*, not cohort selection. The plan now states plainly
that **no available comparison holds training fixed while varying only cohort**, and refuses to label
anything "selection bias" on the combined-vs-frame-only gap alone. Also noted: ≥50 km sequential
inhibition does not give equal inclusion probabilities, so the estimand is the distribution induced by
the locked spatially-inhibited design, not uniform over lattice boxes.

---

## Outcome (final)

**APPROVED after 8 total Codex rounds** (5 on the core design, 3 on the n=20 expansion). Codex was
read-only throughout and never modified a file. Proceeding to Act 3 — build.

## Act 3 — Build (Codex writes, Claude verifies)

### Round 1 — Codex build

Implemented the `risk/` package (24 modules + 6 test files) against the frozen PLAN.md. Reported
honestly: refused to fabricate a frame hash, refused to invent results, and explicitly listed what it
could not execute.

**Phase 0 — actually executed, results real:**
- Hansen GFC v1.12 URL pattern works for all three bands on a live Rondônia window:
  `lossyear` (uint8, 0–24), `treecover2000` (uint8, 0–100), **`datamask` (uint8) — confirmed to exist**,
  which the plan had only assumed.
- Live CDSE openEO (API 1.2.0, backend 0.73.0a13): `SENTINEL2_L2A` exposes **SCL, B11, B12**; `mask`,
  `apply_kernel`, `median` all available. All four generated process graphs validated with zero errors.
- **L0 reflectance convention measured: `already_offset_integer_scaled` → ρ = value / 10000.**
  The BOA_ADD_OFFSET of −1000 must NOT be re-applied. This is L0 working exactly as designed — the plan
  refused to guess and made it a Phase-0 measurement.

### Claude's verdict — Round 1: ACCEPTED (with two blockers escalated to Josh)

Verified independently, not taken on trust:
- **Ran pytest myself: 14/14 pass.**
- **No forbidden path touched** — `git status` on `deforestation/`, `paper/`, `config.py` is empty. Only
  `risk/` is new, as required.
- **Read the four load-bearing guards in the source, not just their tests:**
  - *Label-leak guard* — REAL. `prior = values[(values >= 1) & (values <= 20)]` masks **before** `max()`,
    so a 2021–24 year cannot be selected, plus a post-assertion. Correct.
  - *Fixed support* — REAL. `fixed_support_mask` raises `AssertionError` if the mask differs across any
    of the five years. Cannot silently drift.
  - *L13 temporal firewall* — REAL and structural. `read_frame_hansen` returns **only booleans**
    (`prior_loss_2001_2020`, `recent_loss_2016_2020`); raw `lossyear` never escapes it, and `frame.py`
    imports only that reader — never the unfirewalled `read_hansen_window`. The frame code path is
    *incapable* of seeing the label window.
  - *L4 concordance* — all four verdict rows tested, plus UNRELIABLE/undefined → INCONCLUSIVE.
- **Independently re-derived the L0 finding:** with red=884, NIR=2784, ρ=v/10000 gives NDVI=0.518
  (plausible Amazon forest). Re-applying −1000 gives a **negative red band** and NDVI=1.139, which is
  physically impossible. The measured convention is the only possible one. Confirmed.

**Deviations reported by Codex (all judged acceptable):**
1. L13.1 firewall now builds **two** booleans (`[1,20]` and `[16,20]`) rather than one, because L13.3's
   recent-loss criterion needs the second. Both are ≤2020; no future year reaches selection. Faithful.
2. Skew estimator and the "within-composite dispersion" scalar were undefined in the spec; Codex chose
   bias-corrected `scipy.stats.skew` and the median of the per-band temporal-SD raster. Recorded as new
   locked choices.

**BLOCKERS — escalated to Josh, not worked around:**
- The pinned **Miettinen, Shi & Liew (2016) SE-Asia peat extent** is not obtainable from the cited
  source. Codex **rejected an adjacent substitute rather than silently swapping it** — correct behaviour;
  the layer is pinned, and swapping it is a *plan* change requiring sign-off.
- **CHIRPS monthly NetCDF is 7.7 GB** and was not downloaded, so the L1 windows and the L13 draw have not
  run. No frame hash was invented.

Consequence: **the L13 frame draw has NOT run**, so no sites are selected and no composites downloaded.
