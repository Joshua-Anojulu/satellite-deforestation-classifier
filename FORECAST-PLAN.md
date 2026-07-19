# Plan: Multi-Sensor Forecasting of Near-Term Tropical Tree-Cover Loss (v6-final, post-Codex round 5 / cap)
_Locked via grill — by Claude + Josh (2026-07-19). Converged over 5 adversarial Codex rounds (findings 17→11→8→4→4, all conceded); v6 freezes the last statistical parameters (variogram-range block bootstrap, Hájek survey audit, 95% CI decision rules, explicit nested LOSO). Codex has reviewed through v5; v6 is the mechanical incorporation of its round-5 parameter-freezes. See `FORECAST-REVIEW-LOG.md`._

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
+ budget X values; the deep-model **selection procedure** and its numeric step budget.

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
  as a limitation. **Pass rule (Codex r3 #5, r4 #4):** a proper **non-inferiority test** against the gap
  model's **own same-population contagion baseline** — compute paired `Δlift = gap_model − gap_contagion`
  under the spatially-clustered block bootstrap (§10, same 95 % level and 20 %-undefined gate) and pass
  **only if the 95 % paired lower confidence bound of Δlift ≥ −0.10**; without a held-out 2024 gap test the
  diagnostic is reported **inconclusive**, not passed.
  Comparison to the main result stays **descriptive only** (different year/population/prevalence).
- **Boundary / detector audit (Codex r3 #3/#4):** for a stratified sample (~180 confirmed loss pixels
  **per biome group, further stratified by site and origin**), compare the **earliest credible disturbance
  interval** against **that pixel's actual final contributing predictor acquisition date** (not the Jan-1
  calendar boundary); a positive whose disturbance **predates or overlaps** its composite cutoff is a
  detector case, not a forecast. Disturbance dates come from **RADD and GLAD-L alerts treated as
  interval-censored detection evidence** (not exact event dates; RADD is S1-derived so it is *not*
  independent of the SAR predictor), **supplemented by manual time-series image inspection for ambiguous
  cases**, with unmatched alerts recorded. **Headline pass rule (Codex r4 #3):** because ~180 positives/biome
  cannot literally recompute a full-raster metric, estimate the detector-case share with a **Hájek
  (self-normalized Horvitz–Thompson) survey estimator** over **test-origin (2023) positives**, using frozen
  per-site inclusion probabilities (the ~180/biome allocation applies to 2023 positives, not train/val),
  with **stratified (linearized) survey variance** and a **95 % upper confidence bound required ≤ 10 %**;
  apply the same Hájek weights to produce a **weighted-corrected targeting-efficiency** and retain the
  forecasting claim iff that correction stays within the headline's 95 % bootstrap CI half-width.

### 5. Provenance / pinning
Pin GFC version+md5 (at download, verify coverage confirms the **frozen 2023 primary test** and determines
**only which optional embargoed years** are available — it never changes §1), package versions, openEO
backend version, process graphs, Git commit; seed everything; record windows and grid transforms.

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
  it beats the LightGBM backbone at area-weighted recall@5 % by **≥ 0.03 absolute AND the site-clustered
  bootstrap CI of the improvement excludes 0**; else the backbone is the headline and the deep result is a
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
  1/5/10 % budgets**. **Uncertainty (Codex r4 #1/#2, r5 #1):** a **hierarchical spatial block bootstrap**,
  fully frozen: **block edge L = max(variogram range, receptive-field radius)**, where the variogram range
  is the lag at which an **empirical semivariogram of the residual loss field reaches 95 % of its sill**,
  estimated on **training origins (2020/21) and training sites only**, pooled (if it never reaches the
  cutoff, L = the deep-model receptive-field radius). Each site is tiled into **non-overlapping L×L moving
  blocks** (partial edge blocks kept). Resample: **sites with replacement, then blocks within each drawn
  site with replacement until drawn pixels ≥ the site's pixel count**; **1000 replicates**; **paired model
  comparisons use identical block resamples**. Never resample independent pixels (would falsely narrow the
  regional gate and the deep-model gain gate). If the fraction of replicates with undefined AP (no
  positives) exceeds **20 %**, the site/region is **unevaluable**. All CI decision rules (regional gate,
  deep-model ≥0.03 gate, gap non-inferiority) use the **95 %** interval from this bootstrap. Calibration
  fit on **natural-prevalence validation** only.

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
- **GFC coverage/version** verified at download; origin table + embargo set from it.

## Out of scope

- Any causal / "condition-effect" claim; any strong cross-biome generalization claim.
- A deployable tool, web viewer, or near-real-time alerting system.
- Frontier *emergence* prediction.
- Re-attempting the retired PIF / incremental-information / equal-allocation design; any per-scene /
  moving-reference normalization.
- Sub-annual temporal resolution; changing the finished detector paper on `main`.
