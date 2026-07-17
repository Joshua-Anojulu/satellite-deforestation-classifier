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

---

# Plan Review Log: AMENDMENT-4 — PIF criterion unsatisfiable in-frontier
Act 1 (grill) complete — plan locked with the user 2026-07-17. MAX_ROUNDS=5.
PLAN_FILE=AMENDMENT-4-PLAN.md (PLAN.md is frozen and is NOT the review target).
Reviewer: codex-cli 0.144.3, model gpt-5.6-sol (config default, reasoning effort xhigh).

## Round 1 — Codex

Not approvable yet. The frozen L4 null is mechanically reachable, but the amendment still permits false confirmation through predictor-dependent attrition and an under-specified patch gate.

1. **The temporal firewall is not structural during final QC.** The amendment promises “no label contact,” but [`prepare_site`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/prepare.py:211>) reads full `lossyear`, builds 2021–2024 labels, and evaluates `loss >= 21` before deciding QC at line 320; even though the support expression is mathematically label-invariant, replacement decisions occur in a process already exposed to outcomes.  
Fix: Complete and hash all QC/replacement decisions in a separate process accepting only ≤2020 masks and imagery, then attach 2021–2024 labels after the cohort is frozen.

2. **The PIF distance calculation does not establish distance from “any” loss pixel.** [`build_pif_mask`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/normalization.py:39>) runs the distance transform only over the downloaded master extent, so actual loss just outside an edge is unknown; this can inflate edge PIF counts and invalidate both the census and patch search.  
Fix: Read a ≥1,920 m plus one-pixel Hansen halo around every counted extent, calculate distance in a metric CRS, and crop only after the global-distance test.

3. **The “outcome-identical accelerator” is not guaranteed geometrically identical.** Full preparation obtains Hansen bounds from the backend-produced raster, while a no-download screen knows only the theoretical buffered box; boundary rounding can change counts near 5,000.  
Fix: Specify one canonical buffered footprint and pixel-center rule for both paths, and conservatively download every candidate whose upper-bound count could cross 5,000 under raster alignment uncertainty.

4. **Multiple cross-stratum replacements have no locked global processing order.** L13.4 locked round-robin order precisely because each retained replacement changes later 50 km decisions, but amendment step 2 only says to work within each stratum.  
Fix: Lock a state machine that removes failed sites, refills vacancies in original round/biome order, immediately adds each accepted candidate to `retained`, and logs every rank and rejection reason.

5. **Real L2 failure handling contradicts L13.5.** The amendment says a downloaded frame site is “dropped” and that 14 may become 13, but the frozen rule requires another queue replacement after every frame QC failure until three sites survive or the queue exhausts.  
Fix: Continue deterministic replacement after every optical, coefficient, or PIF failure; stop only on queue exhaustion, not merely when the provisional cohort falls below 14.

6. **The reported 100%/50%/20%/8% “pass rates” are statistically invalid.** Each denominator is the stopping time needed to observe exactly three successes, and the census omitted separation, so `3/k` is neither an unbiased survival estimate nor evidence that dry-forest survivors are exactly an “8% tail.”  
Fix: Screen the complete frozen candidate frame—or a fixed-size prefix chosen independently of results—and report finite-population survival and covariate distributions separately from spatial-separation attrition.

7. **PIF QC changes the scientific population in a direction that can favor the hypothesis.** Requiring remote high-canopy forest preferentially removes saturated frontiers where prior-loss block B is strongest, potentially making C/D appear more incrementally useful; calling this merely “optical QC” conceals the selection mechanism.  
Fix: Amend L13.7 to target explicitly PIF-feasible frontiers, compare full-frame versus retained ≤2020 S/B covariates, and prohibit generalization to saturated active frontiers.

8. **The seven claimed validation sites are not known PIF passes.** The census excludes clear-observation and coefficient QC and is explicitly only a Hansen upper bound, while the final replacement cohort should contain at least 12 actual in-box PIF passes if L13.6 succeeds.  
Fix: Build validation only after full L2, use every final actual PIF-passing site with biome-stratified reporting, and predefine a minimum validation-site count.

9. **The patch placement rule is not executable as written.** “Search outward,” “first 0.1° window,” and “~the median distance” do not define a lattice, metric, target tolerance, dateline behavior, or what happens when the Hansen-first patch later fails clear-observation PIF QC.  
Fix: Lock a globally anchored lattice, geodesic ranking, exact target-distance rule, non-overlap constraints, and deterministic continuation after full patch QC failure, then hash the ordered patch ledger before labels are accessible.

10. **Sharing a relative orbit does not provide the claimed same-scene control.** The current composite graph loads all qualifying acquisitions without an orbit filter ([`download_timeseries.py`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:68>)); the same relative orbit recurs on different dates, atmospheres, and possibly mixed-orbit composites.  
Fix: Require identical product IDs/acquisition dates and a common valid-observation set for target and patch, or drop all “same-scene atmosphere” validity claims and abandon the inferential gate.

11. **Nearest-patch validation can be circular.** Nothing prevents the validation patch from overlapping the buffered site or being a subset of the “true in-box PIF,” which would make agreement nearly tautological.  
Fix: Require every validation patch and all its PIF pixels to be disjoint from the target buffered extent and from the in-box reference population.

12. **Distance matching cannot validate transport into the saturation regime.** The plan concedes that no validation site represents the land-cover and clearing context of Rondônia-like sites, yet still lets an unsaturated-site gate declare saturated results interpretable.  
Fix: Treat remote-patch outputs as exploratory regardless of gate, or replace them with the simpler unnormalized sensitivity excluding `c_*_tailmass`, the only unnormalized feature that requires PIF.

13. **The feature gate omits the block under test.** It checks only `c_*` features, although patch-derived year mappings directly change every `d_*` slope, delta, and temporal-variation feature that determines the headline history contrast.  
Fix: Require equivalence for every C and D feature in both pipelines, explicitly over every site × patch × year × band/index, with a locked scale and zero-variance rule.

14. **The gate margins are uncalibrated point thresholds.** The 0.05/0.01/0.02 and 0.10/0.25-SD limits were introduced after diagnosing the problem, lack a measurement-repeatability or predictive-tolerance basis, and ignore spatial uncertainty.  
Fix: Calibrate margins outcome-blind from independent repeat/reference measurements and require spatial-block equivalence confidence intervals—not point estimates—to lie wholly inside them.

15. **Gate failure is handled by suppressing evidence.** “Numbers are not reported” can hide the magnitude, direction, and site concentration of patch failure.  
Fix: Always publish every validation diagnostic and attempted-site failure; when the gate fails, report saturated effects as unestimated rather than withholding the failed measurements.

16. **QC-failed tables can currently enter modeling.** [`prepare_site`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/prepare.py:346>) writes cell tables even when `site_qc.passed` is false, and [`models.py`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/models.py:279>) accepts a CSV without checking a frozen QC manifest.  
Fix: Emit model-consumable tables only after QC passes and make model entry verify site IDs against the hashed final-cohort manifest.

17. **The new screening evidence and execution trail are insufficiently reproducible.** The amendment requires logging but does not lock the census code, input hashes, geometry, retained-set state, actual-vs-upper-bound PIF counts, or an end-to-end `prepare_site` test after discovering that the path had never run.  
Fix: Produce a hashed per-rank ledger and amended manifest, plus synthetic end-to-end tests covering multiple replacements, temporal-firewall isolation, QC failure, and rejection of failed-site tables before any more downloads.

18. **The documentation correction is incomplete.** Step 12 identifies only L3, while the frozen plan still says five years in L6, L10, Phase 4, and the acquisition-cost calculation, leaving implementers conflicting instructions.  
Fix: Append a complete, line-referenced AMENDMENT-3/4 supersession map without silently editing the frozen sections.

No files were modified.

VERDICT: REVISE
### Claude's response

Verified every factual claim against the code before accepting. Codex was right on the material points.

ACCEPTED — changed the plan:
- #2 (halo): CONFIRMED and decisive. Distance ran over the downloaded extent only, so edge forest got
  inflated distances. Re-ran with a 1,980 m halo: every count falls, santa_cruz_bolivia flips PASS->FAIL
  (5,464 -> 3,367). Legacy survivors 2 -> 1. Combined cohort <= 12+1 = 13 < floor 14 => L13.6 stop-and-re-plan.
  The previous draft's "cohort lands at exactly 14" was an artifact of this bug.
- #12 (simpler alternative): premise verified — pif_median is consumed at exactly one line
  (features.py:77, tailmass). The patch/donut arm is WITHDRAWN and replaced by an unnormalized,
  tailmass-free arm needing no PIF, no new locked parameters and no downloads.
- #7 (selection favouring the hypothesis): accepted as the deepest finding. PIF QC deletes saturated
  frontiers where block B is strongest, weakening the baseline C/D is measured against. The restructure
  is adopted specifically because the PIF-free arm removes this mechanism; L13.7 scope amended and
  retained-vs-frame b_* covariate comparison added.
- #6 (invalid rates): accepted. Stopping-time denominators. Re-screened on a fixed 40-box prefix with
  halo: amazon 26/40, congo 25/40, sea_peat 10/40, dry_forest 2/40. "8% tail" withdrawn.
- #5: accepted — verified L13.5; frame L2 failures are REPLACED until 3 survive or the queue exhausts.
- #4: accepted — verified L13.4 locks a cross-stratum round-robin; also noted its 50 km rule can drop
  tshopo_drc, the last legacy survivor.
- #16: accepted — verified prepare_site writes tables regardless of site_qc.passed and models.py checks
  no manifest. Real bug; fix precedes further downloads.
- #1, #3, #15, #17, #18: accepted as written (structural firewall, canonical footprint + 20% download
  margin, publish-don't-suppress, hashed ledger + end-to-end tests, full supersession map).

MOOT (arm withdrawn): #9, #10, #11, #13, #14. #10's substance is conceded — "same relative orbit" never
delivered same-scene control, since composites aggregate acquisitions across a seasonal window.

PARTIAL — #8: the underlying point (the census is a Hansen-only upper bound, not a set of known PIF
passes) is accepted and folded into D/G. The specific fix is moot with the validation arm withdrawn.

NOT CONCEDED: nothing material. Round 2 should attack the two places this plan is weakest, both flagged
in it rather than hidden: (a) whether losing normalization lets radiometric drift FABRICATE d_* trend
signal, which is the mirror-image false-confirmation risk, and whether the acquisition covariates and
L4 concordance are sufficient guards or a prespecified drift test is required; (b) whether retiring the
combined analysis and elevating the frame cohort is principled (PLAN.md:922 already designates the frame
as the cohort carrying generalization claims) or is choosing the analysis that survives.

## Round 2 — Codex

The revision resolves most prior findings in principle: the halo, temporal firewall, stopping-time bias, deterministic replacement, QC-manifest enforcement, audit ledger, documentation map, and all reference-patch objections are addressed. Two earlier issues remain only partially resolved: the geometry safeguard and replacement behavior across the now-distinct cohorts.

The new primary is not yet safe from false confirmation.

1. **A prespecified drift falsification test is mandatory.** Fixed seasons and L2A surface reflectance reduce drift but cannot show that band-specific atmospheric or sensor shifts did not manufacture `d_*`; the existing acquisition variables are proxies, not radiometric controls.  
Fix: Before labels are attached, hash a drift protocol using ≤2020 stable negative-control pixels, actual platform/orbit/product metadata, and equivalence margins derived from within-season repeatability; a failed drift test must bar a positive headline.

2. **The acquisition-covariate robustness arm is too weak as implemented.** [`prepare.py`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/prepare.py:368>) repeats each site-year metadata scalar across every cell, so it cannot represent spatially varying aerosol/path-radiance artifacts; moreover, roughly twelve metadata fields are learned from only eleven training sites in frame LOSO.  
Fix: Estimate site-year common-mode band/index shifts directly from label-blind control pixels and test raw versus common-mode-adjusted `d_*`, rather than relying on metadata columns added to the prediction model.

3. **Current L4 concordance does not isolate normalization.** The proposed comparison is unnormalized/tailmass-free versus normalized/tailmass-included, potentially trained on different sites; any disagreement can be caused by tailmass, cohort composition, or normalization.  
Fix: Add a normalized/tailmass-free pipeline and compare it with the unnormalized/tailmass-free pipeline using exactly the same sites, training sets, folds, tuning, and features.

4. **Even feature-matched overlap concordance cannot validate saturated sites.** PIF-feasible overlap is selected precisely against saturation, and the normalized arm may fail 12/12 altogether, so this guard can disappear where drift risk matters most.  
Fix: Treat matched concordance as supporting evidence only; require the label-blind drift test independently at every primary site, with failure or insufficient control support forcing `INCONCLUSIVE`.

5. **The revised headline decision rule is undefined.** Frozen L4 requires both normalized and unnormalized CIs to agree, while the amendment makes normalization secondary and possibly unavailable; “report disagreement” does not say what headline follows an unnormalized positive, normalized null, or absent normalized arm.  
Fix: Append a complete decision table in which an unnormalized positive becomes “HISTORY ADDS VALUE” only if the drift gate passes and matched concordance does not contradict it; otherwise it is `INCONCLUSIVE`.

6. **Dropping tailmass can weaken only the static baseline and thereby favor D.** `tailmass` is exclusively a `c_*` feature ([`features.py`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/features.py:77>)); no `d_*` feature is removed, so the amendment’s “C/D signal” wording is wrong and a less complete C baseline can inflate D’s incremental AP. Existing quantiles may make it redundant, but that cannot be assumed.  
Fix: Scope the primary claim to “history beyond the prespecified tailmass-free snapshot,” and require a full-C versus tailmass-free comparison on the PIF overlap; positivity appearing only after tailmass removal must be inconclusive.

7. **The primary cohort is internally contradictory.** Section B says the PIF-free cohort is potentially all 19 sites, while section K retires pooling and elevates the 12-site frame; it is therefore unclear which sites define the primary CI.  
Fix: State unambiguously that the primary generalization estimand is the 12-site frame-only PIF-free analysis, with legacy sites excluded from its training and evaluation.

8. **Frame elevation is principled, but not already dictated by the frozen plan.** PLAN line 922 says the frame sensitivity carries generalization claims, but the next line still calls the 20-site analysis primary, and L13.8 explicitly labels combined LOSO primary; this is a defensible protocol amendment, not merely execution of an unambiguous prior hierarchy.  
Fix: Disclose frame elevation as a post-freeze estimand/hierarchy change justified by outcome-informed legacy selection, and explicitly supersede every conflicting “combined primary” statement.

9. **Retiring the PIF-free combined analysis is not justified.** The combined floor is unreachable only for the normalized/PIF arm; removing PIF makes the non-PIF combined cohort potentially 19 and therefore viable. Omitting the frozen combined analysis once a replacement primary survives looks selective.  
Fix: Keep frame-only as the primary generalization analysis, but require the PIF-free combined LOSO as a labeled secondary case-study whenever non-PIF L2 survival is at least 14.

10. **The two arms require separate cohort and replacement manifests.** A PIF-failing original frame site should remain in the PIF-free primary but be replaced only in the normalized cohort; likewise, a normalized replacement’s proximity to a legacy site must not delete that legacy site from a different PIF-free descriptive cohort.  
Fix: Freeze distinct hashed manifests and replacement state for PIF-free and normalized arms, plus a third exact common-site manifest for matched concordance.

11. **The ±20% geometry guard is an unsupported new threshold.** Nothing proves raster-alignment discrepancies cannot exceed 20%, so the claim that they “can never change a verdict” is stronger than the procedure supports.  
Fix: Derive a worst-case pixel-count bound from the canonical geometry and transformations; if no bound is proven, classify every potentially crossing candidate as requiring the real gate.

The frame-only elevation can be defended because it is the only cohort with a prospective sampling basis and was already designated as the basis for generalization. What cannot be defended is presenting that elevation as fully pre-existing while suppressing the now-viable PIF-free combined secondary analysis.

Most importantly, acquisition covariates plus the proposed L4 overlap comparison are not sufficient guards. Without an outcome-blind, prespecified drift test and an explicit failure-to-`INCONCLUSIVE` rule, sensor or atmospheric drift retains a direct path to a false positive primary conclusion.

VERDICT: REVISE
### Claude's response

Verified the factual claims again before accepting. All three checked out.

ACCEPTED — changed the plan:
- #6 (DECISIVE, and a bias this plan introduced): verified d_* = slope_mean/slope_std/slope_p10/
  tstd_mean/delta — none use tailmass; tailmass is exclusively c_{name}_tailmass, i.e. the static 2020
  snapshot baseline. So dropping it weakens the BASELINE and can inflate D's incremental AP. The draft's
  "only tailmass is lost, every d_* survives" was wrong in the direction that favours the hypothesis.
  Added B2: claim scoped to "beyond the tailmass-free snapshot"; full-C vs tailmass-free comparison
  required on the PIF overlap; positivity appearing only after tailmass removal => INCONCLUSIVE.
- #8/#9 (accepted, and they resolve each other): verified L13.8 says "Combined LOSO ... Primary" — my
  PLAN.md:922 citation was selective. But elevation is also unnecessary: the floor is unreachable only
  for the PIF arm, and the PIF-free combined cohort can reach 19 >= 14. So L13.8 is kept UNCHANGED and
  only the pipeline changes. No hierarchy change to defend; the selectivity objection disappears.
- #1/#2/#4 (drift): accepted in full. Verified prepare.py:368-370 broadcasts site-year scalars to every
  cell — proxies, not radiometric controls, and ~12 site-constant columns fit on 11 LOSO training sites.
  Added D2: mandatory, hashed-before-labels, label-blind control-pixel drift gate at EVERY primary site,
  common-mode shifts estimated from controls (not metadata), margins from within-season repeatability,
  failure or insufficient controls => INCONCLUSIVE. m_* covariates demoted to diagnostics.
- #3: accepted — added a normalized/tailmass-free pipeline so concordance varies ONE thing
  (normalization) on identical sites/folds/features; matched concordance is supporting evidence only.
- #5: accepted — added the F2 decision table covering unnormalized-positive/normalized-null/absent-arm.
  Note it is built so drift failure yields INCONCLUSIVE rather than a null, so the gate cannot
  manufacture the deflationary result either.
- #7: accepted — primary cohort stated unambiguously (B).
- #10: accepted — F3 separate hashed manifests per arm + common-site manifest; a normalized-arm
  replacement's 50 km rule must not delete a legacy box from the PIF-free cohort.
- #11: accepted — the invented +-20% guard is withdrawn and replaced by a DERIVED bound
  B = 2*(H+W) (one-pixel Hansen ring from master-vs-canonical extent), with [5000-B, 5000+B] going to
  the real gate, and unconditional real-gate referral where B cannot be proven.

NOT CONCEDED: nothing material in round 2.

Remaining self-flagged weakness for round 3: D2 is now the study's load-bearing assumption, and
label-blind control pixels are scarcest exactly at saturated sites — if controls are insufficient there,
those sites go INCONCLUSIVE and the primary narrows back toward the PIF-feasible population the
restructure exists to escape. This is testable from <=2020 data before any download.

## Round 3 — Codex

The hierarchy, tailmass, matched-concordance, manifest, and patch findings are now addressed. Round-2 findings #1/#2/#4 remain only asserted: D2 has the right failure direction, but it is not yet an executable statistical test.

1. **“Stable negative-control pixels” is undefined.** D2 does not identify the land-cover classes, spatial support, clear-observation requirement, fixed-pixel rule, or exclusion criteria; selecting pixels because their 2018–2020 reflectance appears stable would make the gate circular and almost guarantee a pass.  
Fix: Define the control mask entirely from independent ≤2020 categorical/history data, prohibit reflectance-stability-based selection, and lock one non-selectable fallback hierarchy before inspecting annual shifts.

2. **Control feasibility at saturated sites remains unknown.** Raw pixel count is insufficient because adjacent 10 m pixels are not independent; Rondônia might contain thousands of nominal controls but only a few effective spatial blocks—or none representing the relevant forest atmosphere.  
Fix: Before approval, run a label-blind census over every prospective primary site and report control pixels, connected components, spatial blocks, land-cover classes, and clear observations against a prespecified effective-support floor.

3. **The insufficient-control rule contradicts the risks section.** [D2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/AMENDMENT-4-PLAN.md:144>) and F2 make any site failure bar the global positive headline, while line 261 says those sites become inconclusive and the primary “narrows,” implying site exclusion. Excluding them would recreate saturation-driven attrition and change the estimand.  
Fix: State explicitly that D2 never excludes or replaces a site: all frozen sites remain in the primary estimate, but any site lacking adequate controls makes the overall headline `INCONCLUSIVE`.

4. **The gate cannot yet be computed from the stored artifacts as described.** Current downloads retain annual medians, temporal dispersion, clear counts, and median solar zenith—not per-acquisition reflectance or per-pixel platform/orbit membership ([`download_timeseries.py`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:99>)); genuine within-season repeatability and platform-specific shifts may therefore require split composites or new downloads.  
Fix: Specify exactly how repeatability and platform/orbit effects are estimable from existing files, or add label-blind S2A/S2B and split-half composite downloads to sequencing and cost.

5. **A common-mode scalar does not test the most dangerous D features.** Spatially varying aerosol or BRDF effects can fabricate `d_*_slope_std`, distort `p10`, and affect indices nonlinearly even when the site-wide median shift is zero.  
Fix: Estimate control shifts by prespecified spatial blocks, test both common-mode and spatial-heterogeneity drift, correct bands first, and recompute indices and every D feature from the corrected bands.

6. **The estimator and equivalence test remain placeholders.** “Derived from within-season repeatability” does not specify the split, estimator, reference year, confidence level, uncertainty propagation, multiple-feature rule, or whether noisy sites receive wider—and therefore easier—margins.  
Fix: Lock formulas for repeatability, shift estimation, spatial-block confidence intervals, familywise pass/fail across sites/bands/D features, and make excessive noise cause insufficient support rather than wider permissive bounds.

7. **“Raw `d_*` vs adjusted `d_*`” has no test statistic or pass rule.** A small median feature change may still be spatially aligned with risk and materially change AP, while a large harmless constant shift may not change ranking.  
Fix: Require both a label-blind feature-equivalence gate and, after labels are attached, identical-cohort raw-versus-drift-adjusted LOSO concordance; raw positivity that does not survive adjustment must be `INCONCLUSIVE`.

8. **The control surface may not transport radiometrically to forest.** Deep water, bare soil, built surfaces, and forest have different BRDF and atmospheric-correction errors; conversely, “no-loss forest” may contain the genuine degradation signal and subtracting its trend can erase real history.  
Fix: Require at least two independently defined control classes—including a vegetation-like control—and fail D2 when their estimated corrections materially disagree instead of choosing the favorable class.

9. **The tailmass guard can disappear without a decision.** B2 requires full-C comparison on the PIF overlap, but the plan acknowledges that overlap may be small or absent; F2 does not say whether an unavailable or underpowered full-C comparison blocks positivity.  
Fix: Lock a minimum evaluable overlap and state that failure to evaluate the mandatory full-C comparison makes any positive headline `INCONCLUSIVE`.

10. **F2 is still incomplete.** It omits `HISTORY HARMS`, unreliable/undefined CIs, and the case where the PIF-free CI excludes zero negatively; “unavailable-and-not-contradicting” also treats absence of evidence as non-contradiction.  
Fix: Add explicit rows for negative, unreliable, undefined, unavailable normalized comparison, and unavailable tailmass comparison, with unavailable evidence described neutrally.

11. **The geometry bound depends on an unproved premise.** `B = 2(H+W)` is valid for a one-Hansen-pixel perimeter difference, but the claim that backend projection/grid snapping changes each edge by at most one 10 m pixel is not derived or asserted in code.  
Fix: Verify and record the canonical-versus-master edge displacement for every raster; where the one-pixel premise fails or cannot be proven, bypass screening exactly as the plan proposes.

The key estimand issue now has a clean resolution available: insufficient D2 controls must not remove saturated sites. They should remain in the combined and frame estimates, with the entire positive claim becoming inconclusive. That preserves the PIF-free population and prevents the drift gate from becoming a new attrition filter.

Until the control definition, effective-support census, stored-data feasibility, spatial-drift test, equivalence statistics, and no-exclusion rule are locked, D2 is a promise of a guard rather than a guard.

VERDICT: REVISE
### Claude's response

Round 3's core judgement is accepted: D2 was intent, not a test. It is now an executable spec (D2.1-D2.8).

ACCEPTED — changed the plan:
- #1: control definition is now categorical-only and reflectance-stability selection is PROHIBITED as
  circular. Two mandatory independent classes: (a) vegetation = Hansen datamask==1 & tree>=70 & no
  2001-2020 loss (crucially NO distance rule, so it is abundant where PIF is not — 506,341 px at
  Rondonia); (b) non-vegetation = datamask==2 permanent water. Locked non-selectable fallback: a class
  short on support yields "insufficient controls", never a fallback to the surviving class.
- #8: accepted, and it cuts both ways — class (b) may not transport to forest, while class (a) may
  contain the genuine degradation signal, so subtracting its trend could ERASE real history rather than
  fabricate it. Handled by requiring both classes and FAILING D2 when their corrections disagree beyond
  the locked margin, so the favourable class can never be chosen.
- #2: effective support is now counted in 640 m spatial blocks, not raw pixels, with a pre-approval
  label-blind census (pixels, connected components, blocks, classes, clear obs) required before any site
  enters the primary.
- #3: accepted — this was a genuine self-contradiction. D2.7 now states D2 NEVER excludes or replaces a
  site; all frozen sites stay in the combined and frame estimates and a control shortfall makes the
  OVERALL headline INCONCLUSIVE. The risks section is rewritten to match: the failure mode is a
  study-wide stall, not a narrowing estimand.
- #4: verified — composites are temporal reductions only (median/sd/sum over t), so per-acquisition
  reflectance and platform membership are NOT in the rasters. Resolved without new downloads where
  possible: the stored `dispersion` band IS a within-season per-pixel per-band SD (a real repeatability
  estimate), and provenance retains all product_ids per site-year (90 for rondonia/2020), so the S2A/S2B
  mix is recoverable by catalogue metadata lookup. Split composites are required ONLY at sites whose
  platform mix shifts beyond a locked tolerance — cost incurred only where triggered.
- #5: accepted — shifts estimated per spatial block per band; both common-mode AND spatial-heterogeneity
  drift tested; bands corrected first, then indices and every D feature recomputed from corrected bands.
- #6: accepted — margins are a locked function of a POOLED cohort-wide repeatability reference, so a
  noisy site gets "insufficient support" rather than wider, easier bounds.
- #7: accepted — two gates: label-blind spatial-block bootstrap CIs (not point estimates) inside the
  margins with a locked familywise rule, plus post-label identical-cohort raw-vs-adjusted LOSO.
- #9: accepted — F2b locks a minimum evaluable overlap; a non-evaluable full-C comparison makes any
  positive INCONCLUSIVE (table row 5).
- #10: accepted — F2 rebuilt with 9 rows including HISTORY HARMS, unreliable/undefined CI, and
  unavailable comparisons. "Unavailable-and-not-contradicting" is removed: absence of evidence is no
  longer scored as agreement (row 8).
- #11: accepted — the one-pixel premise is no longer assumed. Canonical-vs-master edge displacement is
  MEASURED per raster from the composites already on disk; B = 2*(H+W)*e; unmeasurable geometry bypasses
  screening entirely.

NOT CONCEDED: nothing material in round 3.

## Round 4 — Codex

Most round-3 structural findings are addressed: categorical controls, two-class disagreement, spatial blocks, no site exclusion, band-first correction, adjusted LOSO, expanded F2, and measured geometry are now present. D2 still has several unexecuted degrees of freedom that could be resolved favorably after seeing the drift diagnostics.

1. **The plan’s own pre-approval condition has not been met.** D2.2 requires a census, but neither its results nor the minimum effective-block floor appears in the plan; choosing that floor after seeing water scarcity would be threshold shopping.  
Fix: Lock the floor from a power/equivalence calculation, then append the complete site-by-class-by-year census before approval.

2. **Control support is not explicitly fixed across years.** Requiring support “per site-year” allows different pixels or blocks to contribute in 2018, 2019, and 2020, so changing cloud availability or water extent could masquerade as radiometric drift.  
Fix: Use the identical control pixels and identical block weights in all three years—the intersection with adequate finite observations across every year—and fail support if that fixed intersection is inadequate.

3. **The correction field is undefined.** D2.3 estimates shifts in control-containing blocks but never says how corrections are assigned to target forest pixels in blocks without controls: nearest block, interpolation, site mean, or smoothing would produce different adjusted D features.  
Fix: Lock an explicit spatial estimator, interpolation/extrapolation rule, maximum unsupported distance, edge handling, and failure condition before computing any shifts.

4. **There is no rule for combining the two control classes.** “Fail on disagreement” prevents selecting the favorable class only when they disagree; when they agree within the margin, the plan still does not say whether to use vegetation, water, their mean, or both adjusted pipelines.  
Fix: Construct separate vegetation-adjusted and water-adjusted pipelines and require the raw conclusion to survive both, avoiding any selectable combination rule.

5. **Stored dispersion is not clean repeatability.** [`dispersion`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:100>) is the temporal SD of observations across a four-month season; it mixes phenology, atmosphere, platform differences, and real surface change and is not the sampling distribution of the annual median. A pooled margin derived directly from it may be overly wide and let drift pass.  
Fix: Validate a prespecified conversion from dispersion and clear-count to median-composite uncertainty against split-half composites, or obtain split-half products for all sites rather than only platform-mix triggers.

6. **`product_ids` do not identify actual pixel contributors.** Provenance lists every qualifying product intersecting the bounding box, while SCL masking determines contributions separately at each pixel; equal catalogue-level S2A/S2B counts can hide a strongly changing platform mix over the control or analysis support.  
Fix: Produce per-platform valid-observation count rasters over the fixed control and analysis supports, or treat catalogue mix as diagnostic and require split-platform composites universally.

7. **Several “locked” D2 quantities remain unspecified.** There is no formula or value for the pooled-margin function, excessive-dispersion multiple, platform-mix tolerance, bootstrap confidence level, block resampling scheme, per-cell feature summary, familywise procedure, or minimum bootstrap success rate.  
Fix: Put every formula, constant, and conjunction rule into D2 before the census or drift outputs are inspected.

8. **The feature-equivalence statistic is incomplete.** D features are cell-level, but “CI for `|raw d_* − adjusted d_*|`” does not say whether the estimand is the mean, median, maximum, or upper quantile across cells; a small mean can hide a risk-aligned spatial tail.  
Fix: Require both a signed block-weighted mean and a prespecified upper quantile of absolute cell-level differences to pass equivalence for every D feature and control class.

9. **Post-label “survives adjustment” is not a decision rule.** It could mean positive point estimate, overlapping CIs, unchanged sign, or adjusted lower bound above zero.  
Fix: Define survival as the drift-adjusted hierarchical ΔAP CI independently satisfying the same positive classification as the raw CI under identical folds, with either control-class adjustment failing to do so forcing `INCONCLUSIVE`.

10. **The full-C minimum overlap is still an unlocked threshold.** F2b invokes a “locked minimum” without specifying it, leaving room to declare an inconvenient comparison underpowered.  
Fix: Lock the site, biome-coverage, positive-count, and at-risk-cell requirements before computing full-C results.

11. **F2 preserves directional disagreement only for a positive raw result.** Row 3 declares `NULL` and row 4 declares `HISTORY HARMS` regardless of a contradictory normalized/tailmass-free result on the identical overlap, whereas frozen L4 treated any pipeline disagreement as inconclusive.  
Fix: Add normalization-contradiction rows for null and harm, or explicitly justify and scope the asymmetric veto.

12. **The measured geometry rule disables screening for undownloaded replacements.** Those candidates have no backend master raster from which to measure `e`, so the literal fallback sends every one to the real gate; in dry forest that could mean dozens of full downloads and invalidates the stated ~84-file cost.  
Fix: Derive and validate a conservative geometry-specific bound before download from the backend grid specification, or revise sequencing and cost to assume no accelerator for new candidates.

The central feasibility question is still unanswered: whether every frozen site has both vegetation and permanent-water controls in enough fixed 640 m blocks. Raw vegetation abundance at Rondônia does not answer water availability or effective support. Because the plan explicitly makes that census a pre-approval prerequisite, approval before its floor and results are frozen would leave the most consequential threshold selectable.

VERDICT: REVISE
### Claude's response

Round 4's central charge is upheld: the plan made the D2.2 census a pre-approval prerequisite and had
not run it. It is now RUN, and it broke the design as written — which is exactly why it mattered.

CENSUS RESULT (label-blind, <=2020 Hansen, read-only). Blocks >=53 control px:
  vegetation 19/19 sites; WATER only 10/19 (zero px at F3_M020.720 and F4_M002.900_P0105.500;
  4 px at santa_cruz, 6 at gran_chaco, 8 at F2_M002.900). With D2.1 requiring BOTH classes and D2.7
  never excluding a site, the headline would have been INCONCLUSIVE BY CONSTRUCTION — the study could
  return no finding at all, not even the publishable null. Approving before this census, exactly as
  round 4 warned, would have hidden that until after the downloads were spent.

ACCEPTED — changed the plan:
- #1: census run and appended (D2.2). The floor is deliberately NOT set from it; it must come from a
  power/equivalence calculation before any drift diagnostic is inspected. The binding consequence is
  stated: veg_far at F4_M002.900_P0105.500 has 11 blocks, so a floor above ~11 stalls the whole headline.
- Water class WITHDRAWN, but NOT by dropping the guard round 3 demanded. Replaced by two DISJOINT
  vegetation controls split at 640 m from loss (veg_near / veg_far), which probe the real concern behind
  r3#8 — degradation contamination — rather than surface-type transport. Feasibility re-censused: 19/19
  sites on both classes. Forest threshold is the study's OWN universe (tree>=30, eligible30,
  prepare.py:222) because a control must match the population it corrects; PIF's 70% exists for
  pseudo-invariance, which does not apply to a drift control. Justified on principle and fixed before any
  drift is inspected. Note for the record: no other categorical class works — bare/built are near-absent
  in moist tropical frontiers, and grassland/shrubland/cropland ARE the post-clearing state.
- #2: accepted — control masks are time-invariant by construction; the year-varying conjunct is now an
  explicit fixed clear-observation intersection with identical pixels and block weights in all 3 years.
- #3: accepted — correction field locked: own-block shift; else inverse-distance-weighted mean of k=4
  nearest control blocks; unsupported beyond 1,920 m => insufficient support. No smoothing, no site-mean.
- #4: accepted — no combination rule. Separate veg_near-adjusted and veg_far-adjusted pipelines; the raw
  conclusion must survive BOTH.
- #5: accepted — dispersion is NOT clean repeatability (verified: temporal SD across a ~4-month season,
  not the sampling distribution of the annual median). Split-half composites now required for ALL sites
  to validate the conversion; accepted as a cost item rather than argued away.
- #6: accepted — product_ids list bbox-intersecting products while SCL masking decides contribution per
  pixel, so catalogue mix is demoted to a diagnostic. No gate depends on platform attribution, which is
  sound because the correction is estimated from controls sharing the target's acquisitions and masking,
  so it absorbs common-mode shift whatever its cause.
- #7/#10: accepted — added register U listing every unlocked quantity with its derivation, explicitly
  stating approval should be conditional on the register being filled by derivation, not by numbers
  chosen to fit the census.
- #8: accepted — equivalence now requires BOTH a signed block-weighted mean AND the 95th percentile of
  absolute cell-level differences, per feature/band/class.
- #9: accepted — "survives adjustment" defined as the drift-adjusted hierarchical dAP CI independently
  satisfying the same positive classification as raw under identical folds; either class failing => INCONCLUSIVE.
- #11: accepted — F2 rows 3b and 4b added; the normalization veto is no longer asymmetric to positives.
- #12: accepted — the ~84-file/~16h cost estimate is WITHDRAWN as unreliable. New candidates have no
  master raster from which to measure e, so absent a validated pre-download bound there is no
  accelerator, and dry_forest at 5% survival could mean dozens of full downloads. The plan now refuses
  to quote a total until the complete-frame screen reports the count.

NOT CONCEDED: nothing material in round 4.

## Round 5 — Codex (FINAL, MAX_ROUNDS)

The round-4 findings are mostly addressed, but the central feasibility claim is still not established. D2.2 demonstrates that both control classes exist; it does not demonstrate that D2.3 can construct a valid correction over every evaluated block. Two additional false-confirmation paths remain.

1. **The census does not test the correction-field support rule.** Reporting 11 `veg_far` source blocks does not show that every at-risk target block has adequate nearby sources for IDW; with such sparse support, large parts of `F4_M002.900_P0105.500` may be unsupported.  
Fix: Append a site-by-class census of the percentage and count of evaluated target blocks satisfying the complete D2.3 neighborhood rule after the fixed cross-year clear intersection; approval requires 100% if one unsupported block fails the site.

2. **The 1,920 m IDW rule tests the wrong neighbour.** D2 uses `k=4` but declares failure only when the *nearest* control block exceeds 1,920 m, allowing the other three contributors to come from arbitrarily far away.  
Fix: Require the fourth-nearest control block to be within 1,920 m, or lock a maximum distance and minimum contributor count explicitly.

3. **The completed census is Hansen-only, not the required effective optical census.** The table counts blocks with categorical controls, while D2 requires identical pixels with finite observations in all three years; the binding 11 far blocks can only decrease after that intersection.  
Fix: Re-run and append the census using the actual fixed 2018–2020 finite/clear pixel intersection and the final block-occupancy definition.

4. **The unexplained “≥53 control pixels” is itself an unlocked threshold.** It materially determines the reported 19/19 feasibility but is absent from register U and has no derivation.  
Fix: Add the per-block occupancy threshold to U, derive it independently of the observed census, and regenerate the census after locking it.

5. **D2 corrects offsets but does not specify or test gain drift.** “Per-band shifts” implies additive correction; a year-specific multiplicative gain can fabricate `slope_std`, p10, and nonlinear index trends while additive correction leaves `std` unchanged—so raw and adjusted pipelines can agree falsely.  
Fix: Define an affine per-band correction or separately estimate and equivalence-test both gain and offset using fixed control pixels, then recompute all indices and D features.

6. **The correction estimator remains underspecified.** The plan does not state the per-block reference statistic, reference year, robust fitting method, minimum reflectance spread for gain estimation, IDW exponent, or how uncertainty in the correction field enters feature CIs.  
Fix: Add these formulas and failure rules to U; they are structural estimator choices, not implementation details.

7. **The split-half validation is still selectable.** The partition rule—chronological halves, odd/even acquisitions, random split, or platform-stratified split—is not locked, and each estimates a different mixture of phenology and measurement noise.  
Fix: Add a deterministic, platform/DOY-balanced split algorithm, seed, minimum observations per half, and failed-half rule to U.

8. **The near/far distance split needs its own halo rule.** Section D applies the 1,980 m halo to PIF calculations, but D2’s 640 m loss-distance classification is not explicitly covered; truncated edge loss would move edge forest from `veg_near` into `veg_far` and inflate the already fragile far census.  
Fix: Compute the D2 near/far mask with an explicit ≥640 m Hansen loss halo—preferably the existing 1,980 m halo—and crop after classification.

9. **Post-label survival is defined only for positive findings.** D2.6 requires adjusted CIs to preserve raw positivity, but a raw `HISTORY HARMS` result can still be reported when either adjusted pipeline becomes null or positive.  
Fix: Require the same raw-versus-both-adjusted concordance for every directional conclusion; disagreement makes harms inconclusive too.

10. **Register U is not yet exhaustive.** It omits the 53-pixel occupancy threshold, split-half construction, gain model, correction-field estimator, control-distance halo, and IDW contributor-distance rule; filling the current register would not close these choices.  
Fix: Add every item above to U before granting conditional approval.

11. **The risks section is stale.** It still says the census has not run and discusses water availability, contradicting D2.1–D2.2; earlier claims of “no new downloads” also conflict with mandatory split-half products.  
Fix: Update the supersession map and risks/cost language so only the final protocol can guide implementation.

Replacing water with disjoint near/far vegetation is defensible and conservative, but class existence is not correction coverage. More importantly, an additive-shift gate has a concrete blind spot for multiplicative sensor drift—the exact kind of drift that can manufacture `d_*_slope_std` while passing raw-versus-adjusted concordance. Conditional approval cannot cure that unless the estimator and register are expanded first.

VERDICT: REVISE
### Claude's response — DEADLOCK DECLARED, NOT CONVERGENCE

MAX_ROUNDS=5 reached WITHOUT VERDICT: APPROVED. Recording this as a deadlock rather than manufacturing
agreement. Note the deadlock is NOT a disagreement: I concede all 11 round-5 findings. The pattern across
five rounds was not two models arguing to a standstill — each round I fixed real defects and Codex found
deeper specification gaps beneath them. The plan is far stronger than round 1 and still not
implementation-ready. A flagged disagreement beats a false approval; so does a flagged incompleteness.

UNRESOLVED AT DEADLOCK (Claude's position on each):
- #5 AFFINE GAIN DRIFT — the most important. CONCEDED, and it is a genuine false-confirmation path I did
  not guard: an additive-only correction leaves a multiplicative year-gain uncorrected, which can
  fabricate d_*_slope_std and p10 trends while raw-vs-adjusted concordance passes. The estimator must
  become affine (gain + offset), separately equivalence-tested, with indices and all D features
  recomputed. No counter-position; this must be fixed before implementation.
- #1/#3 CORRECTION COVERAGE vs CLASS EXISTENCE — CONCEDED. My census proved the classes exist, not that
  every evaluated target block has IDW support under the full D2.3 rule after the fixed cross-year clear
  intersection. The binding 11 far-blocks at F4_M002.900_P0105.500 can only fall under that
  intersection. The required census is label-blind and free; it simply has not been run.
- #4 THE >=53-PX OCCUPANCY THRESHOLD — CONCEDED, and it is my own error of exactly the kind this process
  exists to catch: I invented 53 px, it materially drives the reported 19/19 feasibility, and it is
  absent from register U. It must be derived independently and the census regenerated after locking it.
- #2 IDW CONTRIBUTOR DISTANCE — CONCEDED. k=4 with a failure rule on only the NEAREST block lets three
  contributors come from arbitrarily far. Needs the 4th-nearest inside the cap, or an explicit
  max-distance/min-contributor pair.
- #6/#7/#10 ESTIMATOR + SPLIT-HALF + REGISTER — CONCEDED. Reference statistic, reference year, robust
  fit, IDW exponent, correction-field uncertainty propagation into feature CIs, and a deterministic
  platform/DOY-balanced split with seed are structural choices, not implementation details.
- #9 SURVIVAL DEFINED ONLY FOR POSITIVES — CONCEDED. A raw HISTORY HARMS must face the same
  raw-vs-both-adjusted concordance; otherwise the veto is asymmetric again, which is the same defect as
  r4#11 in the opposite direction.
- #8 NEAR/FAR HALO — CONCEDED in the plan text. The census code did compute the near/far split on the
  haloed array and crop after classification, so the reported numbers are not affected; the PLAN failed
  to state the rule. Text fix, not a numbers fix.
- #11 STALE RISKS/COST TEXT — CONCEDED and FIXED in this revision (risks items 1-2 rewritten; the
  "no new downloads" claim is superseded by mandatory split-half products and the withdrawn cost estimate).

WHAT THE FIVE ROUNDS BOUGHT (all before a single byte was downloaded):
- r1#2: the halo bug — the cohort arithmetic was wrong; santa_cruz flipped PASS->FAIL and the combined
  floor turned out unreachable (13 < 14). This alone invalidated the round-1 plan.
- r1#12 + r2#6: the reference-patch arm was withdrawn as unnecessary AND the replacement I proposed was
  caught inflating D by weakening the C baseline (tailmass is a c_* feature).
- r1#7: PIF attrition preferentially deletes saturated frontiers where block B is strongest — a path to
  false confirmation.
- r4#1 + this session's census: the two-class water rule would have made the study INCONCLUSIVE by
  construction (water at 10/19 sites), discoverable only by running the prerequisite census.
- r5#5: additive-only correction is blind to multiplicative gain drift.
Every one of these would have surfaced after ~2 days of CDSE downloads, or not at all.

HANDED TO THE USER per the skill's deadlock rule.

---

# Plan Review Log: REFRAME (within-site-relative design)
Act 1 partially locked with the user 2026-07-17 (primary/sensitivity hierarchy). MAX_ROUNDS=5.
PLAN_FILE=REFRAME-PLAN.md. Supersedes AMENDMENT-4-PLAN.md. PLAN.md remains frozen.
Reviewer: codex-cli 0.144.3, model gpt-5.6-sol (config default, xhigh).

Pre-review note: before Act 2, Claude EMPIRICALLY TESTED the plan's load-bearing claim
(risk/census/drift_invariance_test.py) and it came back PARTLY FALSE. Uniform gain is a
non-issue (ratio indices cancel it exactly); differential gain is absorbed (0.0003 z); but
additive offset is NOT cancelled (0.0328 z median / 0.1460 p95 on NDVI) and standardization is
no better than raw. The claim 'affine drift cancels to first order' is exact for bands and WRONG
for the offset component on indices. Disclosed in the plan before review rather than found by it.

## Round 1 — Codex (reframe)

Not approvable. The reframe still has direct paths to false confirmation: the proposed offset correction is not identifiable, year-specific scaling can manufacture history from static condition, and the resulting estimand cannot reject the original hypothesis.

1. **The “within-scene” correction has no scene-level offset to estimate.** Each annual composite is a masked four-month median of many acquisitions, with pixel- and band-specific contributors; one low-percentile scalar cannot represent that mixture and may leave artifacts spatially aligned with frontier geometry.  
Fix: Correct individual acquisitions using independent calibration before compositing, or abandon point correction and require positivity to survive a preregistered adversarial offset sensitivity.

2. **The forest dark tail is endogenous to the hypothesis.** Its low values reflect canopy and terrain shadow, gaps, moisture, burn, and SCL/solar-geometry effects; fixed pixel identities do not make their reflectance invariant, so changing shadow or degradation fractions enter the estimated “offset.”  
Fix: Do not estimate atmospheric offset from analysis forest; use an independent invariant target or treat additive offset as unidentifiable and bar a positive headline unless it survives bounded worst-case offsets.

3. **Independent per-band percentiles need not describe the same dark objects.** Subtracting B04, B08, and SWIR quantiles obtained from different pixels constructs an artificial spectral vector, can create negative reflectance, and can severely distort normalized-difference indices through their denominator.  
Fix: If retained, define one independent joint dark-pixel mask, lock the percentile, subtraction order, negative-value rule, and clipping rule, and fail the method when corrected spectra violate physical bounds.

4. **The moving IQR can fabricate “history” from an unchanged cell.** If raw condition is constant, \(x_{it}=x_i\), then changing annual scales gives \(\Delta z_i=x_i(1/IQR_{20}-1/IQR_{18})+\text{constant}\); block D therefore becomes a transformation of static condition whenever site IQR changes.  
Fix: Use one fixed site scale across all years, or add a frozen-value pseudo-history control block and require D to add value beyond that control.

5. **Including at-risk cells is not necessarily conservative.** Mixture medians and IQRs move nonlinearly when a degrading subgroup crosses quartiles; the denominator can shrink, amplify tails, reverse apparent trajectories, or create changes in unaffected cells rather than merely “dampen” contrast.  
Fix: Lock a contamination sweep across reference mixtures and require the sign and CI to survive leave-at-risk-out and whole-support references; otherwise report `INCONCLUSIVE`.

6. **Each cell’s history depends on changes elsewhere in the site.** A cell can acquire a relative trajectory because its neighbours changed while it did not, allowing landscape-wide condition dynamics correlated with clearing contagion to enter D even after controlling for the cell’s own snapshot and block B.  
Fix: Name this explicitly as a peer-relative exposure and include site-reference-motion controls so it cannot be presented as the cell’s own condition history.

7. **“Fixed support” does not ensure fixed observed support.** Annual cloud masks and nodata can change which pixels contribute to the reference median/IQR and to each cell’s p10, mean, and standard deviation, manufacturing trajectories through observation composition.  
Fix: Use the identical finite-pixel intersection across all three years for both reference and cell summaries, with locked effective-support and missingness failure rules.

8. **No IQR stability rule exists.** A small site-year IQR magnifies residual offsets and noise—the measured 0.146 z p95 already demonstrates this—and an arbitrary epsilon would introduce another selectable parameter.  
Fix: Derive a minimum usable IQR from repeatability before inspecting results; violations must make the directional result inconclusive, not trigger a predictor-dependent site deletion.

9. **The drift experiment does not justify the general claims made from it.** It covers one Rondônia composite and apparently NDVI only; it does not test all sites, years, NDMI, NBR, brightness, cell summaries, three-year D features, or ΔAP, while the 0.0405-z p95 contradicts “differential gain is absorbed.”  
Fix: Run the complete feature and model pipeline under independently bounded bandwise and spatial perturbations at every site-year, and require the headline CI to survive the worst admissible case.

10. **The raw-versus-standardized comparison is dimensionally invalid.** A raw index change of 0.0243 and a standardized residual of 0.0328 z are in different units, so their numerical ordering does not establish that standardization is “no better.”  
Fix: Express both effects in baseline-IQR units and report their full distributions, especially upper tails, for every index and site.

11. **Spatially varying drift remains an open fabrication path.** Aerosol, BRDF, topography, solar geometry, and contributor mix can alter low tails and heterogeneity locally while a site-wide median or dark percentile appears stable; these effects directly target `slope_std` and `slope_p10`.  
Fix: Add preregistered blockwise drift perturbations or spatial negative controls and require every directional conclusion to survive them.

12. **The claim that the “full C baseline returns” is undefined.** If `tailmass` remains `X < median−0.20` in raw index units, it is not standardized or offset-robust; if it becomes `z < −0.20`, it is a new feature with a different scale and meaning, potentially changing baseline strength and inflating D.  
Fix: Lock the exact tailmass formula and units now, call it a new construct if changed, and make positivity dependent on the weaker static baseline `INCONCLUSIVE`.

13. **The feature-construction graph is ambiguous.** “Per index/band” does not say whether bands are corrected and standardized before indices, indices are computed before standardization, or how brightness and post-correction clipping are handled; these orders are not equivalent.  
Fix: Specify one executable sequence from reflectance through offset treatment, physical-range checks, index construction, reference statistics, cell summaries, and C/D features.

14. **The reframe substitutes a different scientific question.** Relative position is context-dependent and blind to uniform absolute degradation; consequently, a null cannot reject the original absolute-condition hypothesis, while a positive can reflect neighbours’ change rather than the focal cell’s history.  
Fix: Either re-register the hypothesis as “peer-relative condition history predicts clearing” and state that the original hypothesis remains untested, or obtain an external radiometric anchor and retain the absolute estimand.

15. **“Disagreement is a finding” is not a headline rule.** Whole-support versus `veg_far`, raw versus offset-corrected, and potentially multiple perturbation analyses create several selectable outcomes without a replacement for L4’s formal concordance table.  
Fix: Freeze a complete decision table in which every directional claim must survive all mandatory drift treatments and is scoped to the relevant reference estimand; all other combinations are `INCONCLUSIVE`.

16. **`veg_far` presence at 19/19 sites does not establish a usable sensitivity.** The census does not establish a fixed three-year optical intersection, effective spatial support, adequate IQR, or an explicit loss-distance halo, so disagreement could merely reflect a sparse or misclassified reference.  
Fix: Complete a label-blind optical-support census with fixed pixels, effective blocks, IQR adequacy, and haloed distance classification before treating `veg_far` as interpretable.

VERDICT: REVISE
### Claude's response

VERDICT: REVISE. Finding #4 is decisive and conceded; it is not repairable within this design.

#4 THE MOVING IQR FABRICATES HISTORY. With raw condition constant (x_it = x_i),
z_it = (x_i - m_t)/IQR_t, so dz_i = x_i*(1/IQR_20 - 1/IQR_18) + const. A cell that never changed
acquires a trend whenever the SITE's IQR moves, and the fabricated trend is PROPORTIONAL to the
cell's static condition -- block D becomes a transformation of block C. Where C and D encode static
condition differently, D can appear to add incremental value while adding nothing. Verified by
algebra, not opinion.

THE TENSION THAT KILLS THE REFRAME. Codex's fix (one fixed site scale for all years) DESTROYS the
drift cancellation: with a fixed reference, x -> g*x + o gives z' = (g*x + o - m)/IQR != z. The
cancellation worked only BECAUSE the reference moved with the drift. So:

  moving reference  => cancels drift, fabricates history (#4)
  fixed reference   => preserves history, cancels no drift

This is an IDENTIFIABILITY OBSTRUCTION, not a specification gap: any within-scene reference that
moves with the drift also moves with the signal. Separating them requires a population exposed to
drift but NOT to signal -- i.e. PIF -- which is precisely what does not exist inside a saturated
frontier (measured: 6/19 sites; 0 at Rondonia; median intact-forest-to-clearing distance 168 m).

Every route tried is a face of the same wall:
  PIF                -> absent in-frontier (measured)
  distant patch      -> breaks same-scene transport; error lands on the block under test
  whole support      -> fabricates history via moving IQR (#4)
  veg_far interior   -> endogenous; interior forest is degrading too (#2/#16)
  dark tail (DOS)    -> endogenous; shadow fraction changes with clearing (#1/#2/#3)
And #14 closes it from the other side: relative position is a DIFFERENT question, so a null under it
cannot reject the original absolute-condition hypothesis.

ALSO CONCEDED, and worth recording:
- #10: the raw-vs-standardized comparison in my drift experiment is DIMENSIONALLY INVALID -- 0.0243
  index units vs 0.0328 z units are different scales, so "standardization is no better than raw" is
  not established by that ordering. The offset residual (0.0328 z median / 0.1460 p95) stands; the
  comparative claim does not. My error.
- #9: the drift experiment is one composite, one site, NDVI-focused; it cannot support general claims
  about all sites/years/indices/D features/dAP, and the 0.0405-z p95 does sit awkwardly with
  "differential gain is absorbed" (the MEDIAN is 0.0003; the tail is not).
- #12: "the full C baseline returns" was undefined -- tailmass in raw units is not offset-robust,
  and in z units it is a NEW construct with different meaning. Either way my claim was loose.
- #6: peer-relative exposure -- a cell can acquire a trajectory because its NEIGHBOURS changed, which
  is landscape dynamics correlated with contagion, not the cell's own condition history.
- #7: "fixed support" != fixed OBSERVED support; annual cloud masks change contributors.

NOT CONCEDED: nothing.

CONCLUSION HANDED TO THE USER: the reframe is not salvageable, and the obstruction is general rather
than incidental to it. The recommendation is to elevate the identifiability result to the paper's
central claim -- it is a stronger and more useful finding than the study it replaces.
