# Plan: Multi-Sensor Forecasting of Near-Term Tropical Tree-Cover Loss (v11, post-Codex rounds 6-10 + two Claude reviews)
_Locked via grill — by Claude + Josh (2026-07-19/20). 5 design rounds (17→11→8→4→4 findings) then 4 verification rounds on the frozen parameters (7→7→2→0, **APPROVED** at round 9); all 30 findings conceded, none rejected. v10 adds one gap found by Claude's own read AFTER Codex approved: the detector-audit retention gate compared a survey point estimate against a tolerance without its sampling error, so it could pass or fail on audit noise — now conservative by 1.96·SE_survey. See `FORECAST-REVIEW-LOG.md`._

## Goal

Build and honestly validate a **forward-looking risk model** predicting, per pixel of standing tropical
forest, the probability of **Hansen-detected tree-cover loss in the following year**, from a short
multi-sensor history plus landscape context.

**Framing is a retrospective, pseudo-operational evaluation** (Codex r2 #1): not a live system. Using a
single pinned GFC version, we ask whether the risk ranking *would have* targeted next-year loss, under
strict, explicitly-dated leakage controls. **Scope is deliberately modest** — a within-frontier
risk-ranking study demonstrated on a set of active frontiers, NOT a strong cross-biome generalization
claim (~3–5 sites/biome cannot support one). Target venues: student research journals. A deflationary
result (no gain over a tuned contagion baseline) is a publishable, honest finding.

## §F — FROZEN vs VALIDATION-TUNED (Codex r2 #10/#11, r3 #8)

**Frozen NOW** (changing any = logged protocol deviation): GFC version+md5 rule; the concrete origin
table (§1); **per-origin issue date = 31 December of T**; θ=30 % + grid; the population formula;
normalization protocol; nested LOSO; modality-ablation set; the event algorithm + dual gate; the
minimum-gain rule; the SAR primary chain + probe; the gap + boundary-audit definitions; the metric suite
+ budget X values; the deep-model **selection procedure** and its numeric step budget; **and (v7 #7) the complete uncertainty machinery — the block-bootstrap range estimator, block geometry and resampling rule (§10a-c), the percentile interval algorithm and half-width definition (§10d), and the detector-audit sampling design, Hájek estimator, variance formula and UCB (§4).**

**Selected on the validation origin (2022 outcome), before the test embargo lifts:** hyperparameters,
early-stopping point, probability calibrator, and — by **validation competition** — which of the two deep
architectures is carried, using one prespecified selection metric (area-weighted recall at the 5 % budget
on validation). **Test origin (2023 outcome) opened once**, after all §F items are frozen.

## Approach

### 1. Temporal design — one concrete, self-consistent chronology (Codex r1 #1, r3 #1)
Three-year history ⇒ earliest origin T is **2020**. Frozen origin table (issue date = 31 Dec T):

| Origin T | Predictors | Outcome (`lossyear`) | Role |
|---|---|---|---|
| 2020 | 2018,2019,2020 | 2021 | **train** |
| 2021 | 2019,2020,2021 | 2022 | **validation** |
| 2022 | 2020,2021,2022 | **2023** | **test (opened once)** |

**Primary test outcome year = 2023 (frozen).** The earlier "second-most-recent released year" rule is
**deleted** (it caused the contradiction). If the pinned GFC covers later years, **optional embargoed
extra out-of-time tests** at origin 2023→2024 and 2024→2025 may be added (requires downloading predictor
years 2023[/2024]); they never alter the primary 2023 result. Downloads are aligned to origins; no
predictor year is fetched that no origin uses. Earlier origins are not attempted (2016–17 archive too thin).

### 2. Predictor archive (reuse + extend)
Reuse `ml-data/deforestation-risk/composites/` (230 verified GeoTIFFs, 19 sites, 2018–20). Extend forward
(2021, 2022; 2023[/2024] only if an embargoed extra test is run) on the frozen per-site windows via the
hardened openEO pipeline. Add **Sentinel-1 SAR** (§7). Resample all dynamic layers to a **30 m grid
aligned to the pinned GFC raster**, operator named per layer (bilinear continuous, nearest categorical).
Evaluate at **both 30 m and 90 m** (two fixed scales, not one chosen later), with a **one-pixel shift
tolerance** and geodesic pixel areas.

### 3. Issue-date firewall + static drivers (Codex r2 #2, r3 #2)
**Issue date for origin T = 31 December T (frozen).** Every acquisition, map release, and layer vintage
used by the primary model must carry a timestamp **≤ that date**. One explicit, disclosed exception: the
**final-version GFC data through T — covering BOTH the `lossyear` eligibility mask AND every GFC-derived
hazard predictor (§8) — is a retrospective product**, not information published on 31 Dec T. This is
inherent to the pseudo-operational framing and is stated as such, not hidden.

Primary static layers (each with a valid ≤-issue snapshot): **roads** — OSM full-history / dated Geofabrik
≤ T; **rivers** — HydroBASINS; **protected areas** — WDPA historical monthly release ≤ T; **terrain** —
Copernicus DEM; **peat** — PEATMAP; **ecoregion**; **climate** — CHIRPS 1981–2010 normal (pre-period);
**historical-loss hazard features** from GFC loss ≤ T (§8). Any layer lacking a clean ≤-issue snapshot is
**excluded from the primary model** and may appear **only in a labeled exploratory sensitivity**.

### 4. Label, population, and forecast-not-detector safeguards (Codex r1 #3/#4, r2 #3/#4/#5, r3 #3/#4/#5)
Population (frozen): **"2000-baseline GFC tree-cover pixels with no detected loss through T"** =
`datamask==1 ∧ treecover2000 ≥ θ ∧ (lossyear==0 ∨ lossyear>T)`; θ=30 % default, θ∈{10,25,50,75}%
sensitivity; regrowth-after-2000 and repeat-disturbance pixels excluded (stated). **Positive** =
`lossyear==T+1`.

- **Gap diagnostic (conditional):** pixels **eligible(T) ∧ eligible(T+1)**, predict `lossyear==T+2` from
  features **≤ T**; own shifted table (train 2020→2022, val 2021→2023, test 2022→2024 only if GFC covers
  2024, else train/val, disclosed); T+1-lost pixels removed + reported; conditioning on T+1 survival stated
  as a limitation. **Pass rule (Codex r3 #5, r4 #4; v7 #6):** a proper **non-inferiority test** against the
  gap model's **own same-population contagion baseline** — compute paired `Δlift = gap_model − gap_contagion`
  under the §10 block bootstrap (same tiles, same 1000 paired replicates, same 20%-undefined gate) and pass
  **only if the one-sided 95% percentile lower bound q0.05 of Δlift ≥ −0.10**; without a held-out 2024 gap
  test the diagnostic is reported **inconclusive**, not passed.
  Comparison to the main result stays **descriptive only** (different year/population/prevalence).
- **Boundary / detector audit (Codex r3 #3/#4; v7 #4/#5):** compare each sampled positive's **earliest
  credible disturbance interval** against **that pixel's actual final contributing predictor acquisition
  date** (not the Jan-1 calendar boundary); a positive whose disturbance **predates or overlaps** its
  composite cutoff is a **detector case**, not a forecast. Disturbance dates come from **RADD and GLAD-L
  alerts treated as interval-censored detection evidence** (not exact event dates; RADD is S1-derived so it
  is *not* independent of the SAR predictor), **supplemented by manual time-series image inspection for
  ambiguous cases**, with unmatched alerts recorded.

  **Sampling design (frozen).** Frame = **test-origin (2023) positives only** (train/val positives are never
  used to correct the 2023 headline). Strata = **site**, grouped by biome; a site with **N_bs = 0 is not a
  stratum**. Per biome group **n_b = 180**, allocated in this exact order (v8 #4):
  (i) any site with **N_bs ≤ 5** is a **census** (n_bs = N_bs) and is removed, with its count, from the pool;
  (ii) if Σ N_bs over the remaining sites ≤ the remaining budget, **every remaining site is a census too**;
  (iii) otherwise **each remaining site is first given a floor of n_bs = 2**, and the budget left after those
  floors is apportioned by **largest-remainder proportional to REMAINING CAPACITY (N_bs − 2)** — not to
  N_bs, which overflows small strata (v9 #2: N = (6, 175) at budget 180 would hand the 6-pixel site ~8
  samples). Any site whose allocation would still exceed N_bs is **capped at N_bs (census) and its excess
  redistributed proportional to the remaining capacities of the uncapped sites, iterating until no site
  overflows**; ties broken by **ascending site id**; (iv) if the floors alone exceed the remaining budget, the budget is raised to cover them and the
  overage is disclosed. This guarantees **n_bs ≥ 2 in every non-census stratum** — n_bs = 0 would give a zero
  inclusion probability and invalidate the Hájek estimator outright, n_bs = 1 leaves within-site variance
  undefined. Within each site: **simple random sampling without replacement**, so **π_bs = n_bs / N_bs**,
  frozen before any audit label is read.

  **Estimator + decision (frozen).** With weights `w_i = 1/π_b(i)s(i)` and `d_i ∈ {0,1}` (detector case),
  the detector share is the **Hájek ratio** `D̂ = Σ w_i d_i / Σ w_i`, computed on a **pixel-count basis at
  30 m** (not geodesic area — the audit unit is the pixel). Variance = **stratified Taylor-linearized ratio
  variance** with finite-population correction: `V̂(D̂) = (Σ w_i)⁻² · Σ_s (1 − n_s/N_s) · (N_s²/n_s) ·
  s²_{e,s}`, where `e_i = d_i − D̂` and `s²_{e,s}` is the within-site sample variance of `e_i`. **Census
  strata (n_s = N_s) contribute exactly zero**, as their FPC term is 0.

  **95% upper confidence bound (frozen, boundary-safe; v8 #5).** The earlier v7 wording was contradictory —
  it printed a probability-scale Wald bound while claiming a logit-scale computation. Frozen replacement,
  with **Kish effective sample size `n_eff = (Σ w_i)² / Σ w_i²`**:
  - **0 < D̂ < 1:** `UCB = expit( logit(D̂) + 1.645 · √V̂(D̂) / (D̂·(1 − D̂)) )` — the delta-method transformed
    standard error, explicitly.
  - **D̂ = 0 or D̂ = 1:** the logit bound is undefined, so use the **Clopper–Pearson one-sided 95% upper
    bound** at `round(D̂ · n_eff)` successes in `round(n_eff)` trials; at D̂ = 0 this is `1 − 0.05^(1/n_eff)`.
    (D̂ = 0 is a plausible audit outcome and must not yield a falsely degenerate bound.)

  **The study requires UCB ≤ 0.10.**

  **Corrected headline (frozen; v8 #6).** The target set is frozen **before** the audit: `z_i ∈ {0,1}` is
  membership in the **top 5% of predicted risk selected GLOBALLY over the pooled 12 frame sites by geodesic
  area, taken from the uncorrected 30 m test-origin map, and never recomputed** after detector cases are
  removed. `TE_corr` is then computed **over sampled positives only** — the only pixels for which `d_i` and
  `w_i` exist:

      TE_corr = Σ_sample a_i · w_i · (1 − d_i) · z_i  /  Σ_sample a_i · w_i · (1 − d_i)

  where `a_i` is pixel geodesic area. Detector cases carry zero weight; the surviving forecast positives are
  reweighted to the full 2023 positive population. **Retention gate (frozen; v10).** `TE_corr` is a survey estimate from the ~180/biome audit and therefore
  carries its own sampling error, which must enter the decision — comparing a bare point estimate against a
  tolerance would let the gate pass or fail on audit noise alone, in either direction. Retain the
  forecasting claim **iff**

      |TE_headline − TE_corr| + 1.96 · SE_survey(TE_corr)  ≤  TOL,
      TOL ≡ min( half-width , 0.05 )

  where the half-width is the headline's bootstrap CI half-width, defined in §10(d) as `(q0.975 −
  q0.025)/2`. **The absolute cap 0.05 is frozen and is the operative half of the rule whenever the study is
  imprecise (v11 #1).** Using the bootstrap half-width ALONE — as v10 did — makes the tolerance scale with
  the study's own noise, so a thin, wide-CI study would earn a MORE permissive detector-integrity gate than
  a precise one. That is backwards, and it is self-serving in exactly the direction that flatters the
  headline claim, so the tolerance is now the stricter of the two. 0.05 is the largest absolute shift in
  area-weighted recall@5% we are willing to call immaterial to the forecasting claim; it is a prespecified
  judgement, disclosed as such, not estimated from these data. and `SE_survey(TE_corr)` is the square root of the **same stratified Taylor-linearized ratio
  variance already frozen above for D̂** — FPC included, census strata contributing exactly zero — applied to
  the `TE_corr` ratio with `e_i = a_i·(1 − d_i)·(z_i − TE_corr)`. **The ratio's OWN denominator is used, not
  D̂'s:** `V̂(TE_corr) = X̂⁻² · Σ_s (1 − n_s/N_s) · (N_s²/n_s) · s²_{e,s}` with
  **`X̂ = Σ_sample w_i·a_i·(1 − d_i)`** — substituting D̂'s `(Σ w_i)⁻²` here would be wrong. `TE_headline` is computed from the full
  raster and contributes no sampling term. This is deliberately conservative, matching the one-sided-UCB
  idiom used for the `D̂ ≤ 0.10` rule: audit imprecision makes the gate **harder** to pass, never easier.

### 5. Provenance / pinning
Pin GFC version+md5 (at download, verify coverage confirms the **frozen 2023 primary test** and determines
**only which optional embargoed years** are available — it never changes §1), package versions, openEO
backend version, process graphs, Git commit; **seed everything explicitly (v7 #3, v8 #3): global seed = 42;
RNG = NumPy `Generator(PCG64)`. Streams are instantiated DIRECTLY, never by sequential `spawn()` — order of
execution must not change any draw — via `Generator(PCG64(SeedSequence(42, spawn_key=(analysis_code, unit_index,
replicate))))`. **The `unit_index` coordinate is required (v11 #3):** with only `(analysis_code,
replicate)`, any analysis that runs once per FOLD — notably code 6, model weight init and training shuffles,
which runs per outer fold and per competing architecture — would draw from a single shared stream, so
execution order across folds would change the draws. That is exactly the order-dependence the direct-
`spawn_key` rule was adopted to eliminate, left open for training. `unit_index` is frozen as: the **outer
LOSO fold index** (0-11, ascending by held-out site id) for codes 1-6, times two plus the architecture index
(0 = temporal-attention U-Net, 1 = channel-stacked U-Net) for code 6 specifically; **0** for code 0, which
is drawn once globally. Frozen numeric analysis codes: `0` = detector-audit survey sampling, `1` = headline
block bootstrap at 30 m, `2` = headline block bootstrap at 90 m, `3` = gap-diagnostic bootstrap, `4` =
deep-model gate bootstrap, `5` = variogram-range estimation, `6` = model weight init / training shuffles;
`replicate` is the 0-based replicate index (0 for non-replicated analyses). Canonical ordering before any
draw = sites ascending by site id, tiles row-major from the raster origin, pixels row-major, survey records
by (site id, pixel index)**; record windows and grid transforms.

### 6. Normalization — fixed per LOSO fold (retired moving-reference trap; Codex r2 #7)
**For each LOSO fold, fit normalization constants from origin-2020 pixels of the 11 frame training sites
only; apply unchanged to that fold's validation and held-out-site test data.** No per-scene / per-site-year
centering or scaling. Prefer self-normalizing indices (NDVI/NBR/NDMI). Any drift audit is **diagnostic
only** and never triggers test-dependent renormalization. PIF dropped as **unnecessary**, not "impossible."

### 7. Sentinel-1 SAR — S1A-primary, piloted, leakage-safe probe (Codex r1 #13/#14, r2 #10, r3 #7)
**Primary SAR = Sentinel-1A only, fixed orbit direction + relative orbit** (S1A spans the whole period ⇒
immune to the S1B Dec-2021 gap). Mixed A/B + acquisition-count adjustment are sensitivities only. Freeze
and validate the chain on **3 pilot sites** (RTC coeff + DEM, shadow/layover, speckle, linear-vs-dB ratio
order, nodata). **Artifact-screen probe (frozen, leakage-safe):** select **stable pixels using
training-period (≤2020) loss-free, non-edge** pixels only; compare **the same pixels across years**; a GBM
predicting acquisition-year, **validated grouped by site with balanced site-years**, must score
**macro one-vs-rest ROC-AUC < 0.60** (a conservative artifact screen, not proof of radiometric invariance)
for SAR to enter the primary model; else SAR is exploratory-only. SAR benefit is a hypothesis the ablations test; the cloud-causation
Congo claim is withdrawn.

### 8. Baselines + prespecified ablations (Codex r1 #10/#11, r2 #9)
- **Tuned historical-loss hazard baseline** (number to beat): multi-radius recent-loss density,
  time-since-nearest-loss, **windowed neighbour-loss fraction excluding the focal pixel**, local loss
  trend. ("Own-pixel prior loss" removed — identically zero on eligible pixels.)
- **Prevalence null**, an **NDVI-trend heuristic**, a **logistic** sanity model.
- **Modality ablations (frozen):** contagion / contagion+static / optical / SAR / optical+SAR / full.

### 9. Models — hazard backbone + prespecified deep head (Codex r1 #16, r2 #10, r3 #8)
- **Primary reportable backbone: LightGBM** discrete-time hazard model on per-pixel tabular features.
- **Deep head:** **both** a temporal-attention U-Net **and** a shallow channel-stacked U-Net (GroupNorm)
  are trained and **compete on the validation origin** (selection metric: area-weighted recall@5 %); the
  winner is the reported deep model. A **one-site memory/runtime pilot** fixes batch size/norm on the 8 GB
  GPU first. **Engineering guard (frozen numeric budget):** a run is abandoned only on hard OOM or
  divergence, or if validation metric fails to improve for **20 epochs** (hard cap **200 epochs**) — this
  is a safety trigger, **separate from** the architecture selection above (they no longer conflict).
- **Minimum-meaningful-gain rule (frozen):** the deep head becomes the headline **only if**, on validation,
  it beats the LightGBM backbone at area-weighted recall@5 % by **≥ 0.03 absolute AND the §10(d)
  hierarchical spatial block bootstrap CI of the improvement (paired, identical resamples) excludes 0**; else the backbone is the headline and the deep result is a
  comparison.

### 10. Evaluation (Codex r1 #6–#9, r2 #6, r3 #6, r5 #2)
- **Whole-site LOSO** primary. **Exact nesting (frozen):** for each outer held-out frame site, **every**
  hyperparameter, calibration, deep-architecture-competition, and ≥0.03 headline-gate decision uses **only
  the other 11 frame sites** — train on their 2021 outcomes, select/tune/calibrate on their 2022 outcomes —
  and the held-out site contributes **predictors only at final 2023 inference**; no held-out-site data
  (including normalization constants) enters training or model selection. Within-site (case study only):
  non-overlapping blocks, guard bands ≥ receptive-field radius, years kept together.
- **Frame-only (12 sampled sites) primary; 7 legacy sites exploratory.** All preprocessing in-fold.
- **Event algorithm + dual gate (frozen, fully computable):** positives grouped into **mapped loss
  components** by **8-connectivity** (4-conn sensitivity), **min size ≥ 2 px (~0.18 ha)**, per site-year.
  An **evaluable site** = a frame site with **≥ 5 mapped loss components** in the test origin. A region
  yields a **per-region generalization estimate** only if **≥ 3 evaluable sites AND ≥ 30 mapped loss
  components AND** the AP-lift bootstrap CI half-width ≤ 0.10; else descriptive. "Components," not
  "independent events" (spatial independence not claimed).
- **Metrics (frozen):** per-site + macro-region **AP**; prevalence; **AP-lift ≡ AP / prevalence** (ratio,
  fixed definition); **Brier / log-loss**; **calibration slope/intercept**; **area-weighted recall at
  1/5/10 % budgets**.

**Uncertainty — hierarchical spatial block bootstrap (Codex r4 #1/#2, r5 #1; v7 #1/#2/#3/#6).** Frozen in
four parts. Never resample independent pixels (it would falsely narrow the regional gate and the
deep-model gain gate).

*(a) Range estimation (v8 #1, v9 #1).* **Prediction artifact, named exactly:** the residual field is
`outcome − p̂`, where `p̂` is the **contagion baseline's PRE-CALIBRATION (raw) predicted probability**,
generated by **INNER cross-fitting (v9 #1)**: within outer fold *h*, the residual for each of the 11
non-held-out sites *j* comes from a model fit on the **other 10 non-held-out sites only** — never from
the ordinary 12-site LOSO predictions, which are contaminated because site *h* participated in training
them and would thereby influence its own L. The inner fits **preserve the exact temporal roles** (train
on 2021 outcomes, select/calibrate on 2022 outcomes). Residuals are computed **only over
eligible-population pixels** (§4) at the origin in question; ineligible and nodata cells contribute to no
pair. Domain = **training origins (2020, 2021) and, for outer fold *h*, the 11 non-held-out frame sites
only** — so **L is recomputed per outer fold** and the outer held-out site is causally absent from it.

**Estimator.** Classical **Matheron** semivariogram over those residuals. **Lag bins are defined in metres,
not pixels:** bin *k* covers separation `((k−1)·g, k·g]` metres where `g` is the grid spacing of the scale
being evaluated (30 m or 90 m), for `k = 1..200`; **maximum lag = 200·g metres**. Computed **per
site-origin**, then pooled across site-origins as a **pair-count-weighted mean per bin**. **Empty bins
(zero pairs) are dropped from the pooled curve and from the crossing scan** — they are not interpolated and
not treated as crossings.

**Sill ≡ mean pooled semivariance over the non-empty bins among k = 151..200**, subject to a frozen
**plateau check (v11 #2)**: fit an OLS line to the pooled semivariance over those same bins and require
`|slope| · (50·g) ≤ 0.05 × sill` — i.e. the curve rises by ≤5% of the sill across the tail window. **If the
check FAILS the variogram has not plateaued, the sill is UNDERESTIMATED, and the 0.95-of-sill crossing
would fire spuriously early — yielding a too-small L, too-small blocks, and CIs that are too NARROW.** That
is the anti-conservative direction and it silently inflates confidence in the regional gate and the
deep-model gain gate at once. On failure, therefore, the estimated range is DISCARDED and
`L = ceil(max(RF_radius_m, 200·g) / g)` — fall back toward LARGER blocks, never smaller — and the failure
is reported per fold and scale. **Range ≡ the upper edge, in
metres, of the first non-empty bin whose pooled semivariance ≥ 0.95 × sill**; no interpolation. If no bin
crosses, the range is **undefined** and L falls back to the receptive-field radius. **Both the range and the
RF radius are recorded in metres**, and `L = ceil( max(range_m, RF_radius_m) / g )` **integer pixels**,
computed **separately and independently at g = 30 m and g = 90 m**.

*(b) Block geometry.* Each site raster is partitioned into **grid-aligned, strictly non-overlapping L×L
tiles anchored at that raster's top-left origin**. The phrase "moving block" is **withdrawn** — this is a
non-overlapping tile bootstrap, one design, not two. **Partial edge tiles are kept as-is** (never padded,
never merged into neighbours) and are candidates on the same footing as full tiles.

*(c) Resampling (v8 #2).* **The counting population is frozen: throughout the bootstrap, "pixels" means
eligible-population pixels (§4) at the origin under evaluation — never all raster cells, never nodata.**
A site's pixel count is its eligible-pixel count; a tile's contribution is its eligible-pixel count; and
metrics are computed over exactly those cells. **Tiles containing zero eligible pixels remain candidates**
and may be drawn (contributing 0 toward the stopping total), so tile-selection probabilities stay uniform
and independent of the outcome — dropping them would condition the geometry on the data.

Draw **exactly S sites with replacement** (S = sites in the unit). Within each drawn site, draw tiles
**uniformly with replacement** — uniform over tiles, **not** pixel-proportional — **until cumulative drawn
eligible pixels ≥ that site's eligible-pixel count**; the **final overshooting tile is retained in full** and
**all duplicate pixels are retained**. **1000 replicates.** Paired model comparisons reuse **identical
site+tile resamples**.

*(d) Interval algorithm (v8 #7).* **Percentile bootstrap throughout** — no BCa, no basic, no normal
approximation. **Undefined replicates (no positives ⇒ undefined AP) are DROPPED before any quantile is
taken; the undefined FRACTION is computed against all 1000 attempted replicates.** Quantiles are then
`numpy.quantile(defined_replicates, q, method="linear")` — the interpolation convention is frozen because
competing conventions differ at n≈1000 by enough to move a borderline gate.

Two-sided 95% = **(q0.025, q0.975)**; one-sided 95% **lower** bound (gap non-inferiority) = **q0.05**;
one-sided 95% **upper** bound = **q0.95**. Wherever a **"CI half-width"** is used as a threshold it means
**(q0.975 − q0.025) / 2**. If the undefined fraction exceeds **20%**, that site/region is **unevaluable**
and no interval is reported for it. All CI decision rules (regional gate, deep-model ≥0.03 gate, gap
non-inferiority) use this bootstrap at the levels above. Calibration fit on **natural-prevalence
validation** only.

### 11. Real-world wrapper — Rondônia case study
Leave-site-out 30 m risk map at the test origin, targeting-efficiency curve, deterministic examples of
high-risk pixels subsequently cleared; Rondônia's prior inspection disclosed. No deployable tool (out of scope).

### 12. Prespecification
Freeze §F before validation/test; deviations logged.

## Key decisions & tradeoffs

- **Retrospective pseudo-operational framing** with a **concrete 31-Dec-T issue date** and a single
  disclosed retrospective-label exception — honest about label-release timing.
- **One self-consistent origin chronology** (2020/21/22 → 2021/22/23), embargoed extras optional — no
  internal contradiction.
- **Modest within-frontier claim**, pooled headline + per-site reporting + clustered CIs.
- **Fixed per-fold normalization**, strict pre-issue static vintages — temporal/moving-reference leakage closed.
- **Hazard backbone + validation-gated deep head** — Josh's "max complexity with a fallback," the deep
  model must earn the headline by ≥0.03 recall@5 % with CI excluding 0.
- **S1A-only SAR + leakage-safe year-probe (AUC<0.60)** — S1B gap removed by construction; SAR refused if it
  encodes acquisition artifacts.
- **Detector audit against the composite acquisition cutoff** (not the calendar boundary), alerts treated as
  interval-censored + manual check — tests the right quantity.
- **Fully-computable dual gate + gap non-inferiority rule** — reproducible validity safeguards.

## Risks / open questions

- **Thin origins/regions** — 3 origins, ~3 frame sites/region: hazard-backbone-primary, pooled headline,
  honest CIs, evaluability gate; a deep temporal model has little temporal structure (accepted, gated).
- **Static-driver history** — OSM full-history and dated WDPA ≤ each origin should be obtainable; if not for
  some layer/origin, that layer is exploratory-only.
- **Data volume / time** — ~19 sites × up to 6 years × (optical+SAR); ~21.7 GB optical on disk, comparable
  forward, plus SAR. No deadline; staged; SAR piloted first.
- **SAR probe may fail** → SAR exploratory; study stands on optical+static+contagion.
- **Manual audit effort** — the detector audit needs some manual image inspection for ambiguous alerts
  (bounded by the ~180/biome sample).
- **GFC coverage/version** verified at download; coverage confirms the frozen 2023 primary test and
  determines only which optional embargoed years are available — it never sets §1.

## Out of scope

- Any causal / "condition-effect" claim; any strong cross-biome generalization claim.
- A deployable tool, web viewer, or near-real-time alerting system.
- Frontier *emergence* prediction.
- Re-attempting the retired PIF / incremental-information / equal-allocation design; any per-scene /
  moving-reference normalization.
- Sub-annual temporal resolution; changing the finished detector paper on `main`.
