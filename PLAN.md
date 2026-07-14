# Plan: Within-Frontier Deforestation Risk — does forest condition *history* add predictive information beyond prior clearing?

_Locked via grill — by Claude + Josh (2026-07-13). Hardened over 5 adversarial Codex review rounds;
**VERDICT: APPROVED** at round 5. See `PLAN-REVIEW-LOG.md` for the full argument._

**Provenance to record in every results artifact:** pinned package versions (`scikit-learn`,
`rasterio`, `numpy`, `openeo`), the Git commit, the openEO backend version, and the exact process
graph used to build each composite.

## Goal

A **companion paper** to the existing cross-biome detector study. That paper asked *"can we detect
clearing that already happened?"* (answer: no detector dominates — robustness, not peak F1). This one
asks the forward-looking question:

> Within an already-active deforestation frontier, does a forest cell's **condition history**
> (~~5 years~~ **3 years** of spectral trajectory, ~~2016–2020~~ **2018–2020** — see **AMENDMENT-3**)
> carry **incremental predictive information** about Hansen-detected tree-cover loss in 2021–2024,
> **conditional on** what we already know from prior clearing (contagion) and a single 2020 snapshot?

**AMENDMENT-3 (2026-07-14) shortened the history window from 5 years to 3.** The 2016/2017 Sentinel-2
L2A archive is too thin to reach the L2 clear-observation gate at most sites, so the original window
made the study unviable (only 12 of 19 sites survived, against a floor of 14). The shortened history is
**noisier and biased toward the null on exactly the block under test**, so a null result no longer
cleanly separates "history carries no signal" from "three years is too short to see it." See L1.

**The estimand is explicitly predictive, not causal.** Roads, tenure, access, and fragmentation drive
both blocks; a performance delta is evidence of *incremental predictive information conditional on
measured contagion*, and nothing stronger. We will not claim a "condition effect."

The hypothesis under test is the user's: **history matters.** The design is built to be able to
*reject* it and — equally important — built so that it cannot **falsely confirm** it. A deflationary
result ("condition history adds no operationally useful signal beyond proximity, at 640 m / annual
resolution, from these bands") is a useful finding and is what we report if we get it.

### Scope claims — stated in the abstract, not buried

- **Within-frontier risk allocation, NOT frontier emergence.** Every box in the combined cohort is an
  already-active frontier *as of 2020* — **established** by the L13.3 eligibility criteria, which
  **L13.5b applies to the legacy boxes as well as the frame boxes**, so this is a screened fact rather
  than an assumption. We cannot claim to predict which intact forest *becomes* a frontier.
- **The target population is NOT "forest-dominated frontiers" (AMENDMENT-1 changed this).** It is
  **active-frontier landscapes containing ≥300 residual at-risk cells — explicitly including advanced,
  heavily-cleared and fragmented frontiers** (the legacy Amazon boxes retain only 35–38% eligible
  forest; Gran Chaco 23.5%). Results are reported both under this population and, as a prespecified
  sensitivity, under the original forest-dominated (≥50%) definition.
- **The FRAME-ONLY analysis is the primary generalization analysis. The combined/legacy analysis is
  SECONDARY**, because legacy cohort inclusion was revised (AMENDMENT-1) with outcome-aware sites in
  view. This is a protocol deviation and is disclosed as one.
- **Two strata, and the distinction is load-bearing.** The **8 legacy boxes** were purposively selected
  and *confirmed on GFW* — outcome-informed, and on their own they would be a case study, not inference.
  The **12 new boxes** are randomly drawn from the L13 pre-2021 frame and are NOT outcome-informed.
  LOSO gives out-of-**site** performance on most folds still train on another site from the same biome. The **12 frame-sampled
  sites (L13)** are free of outcome-informed selection and carry the generalization claim; the **8
  legacy boxes** were purposively chosen and are flagged as such.
- **The outcome is "Hansen-detected tree-cover loss", not "deforestation."** GFC reports gross
  stand-replacement loss; `treecover2000` includes plantations and any vegetation >5 m. Fire,
  harvest, and natural disturbance are positives.
- **Retrospective temporal holdout, NOT a "never-seen future", NOT pre-registered** — **at the eight
  legacy sites specifically**, where the prior study already analyzed the 2024 imagery and 2016–2024
  Hansen outcomes. This statement does **not** extend to the 12 L13 boxes, which have never been looked at.
  The 12 L13 boxes have never been looked at, which is precisely why they carry the generalization
  claim. See §Outcome-informed choices.
- **Any negative claim is bounded by the measured feature space** — annual dry-season composites,
  640 m cells, these bands. It cannot establish that "satellite condition history" is unhelpful
  in general.

---

## §L — LOCKED PARAMETERS (fixed before any download; no post-hoc adjustment)

Everything here is a researcher degree of freedom that could otherwise be tuned to flatter the result.
All values are committed **now**, before data is touched.

### L0 — Reflectance scale (must be settled first; everything else depends on it)

Sentinel-2 L2A ships as integer DN, **not** reflectance. The existing pipeline treats values as
~0–10,000; L2's offset bounds are stated in unitless reflectance. Convert **once, up front**:

`ρ = (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE`

- **RESOLVED BY PHASE 0 (2026-07-13, measured against live CDSE — see `results/phase0.json`):**
  the composites arrive **already offset**. The conversion is **`ρ = value / 10000`**, and
  **`BOA_ADD_OFFSET` must NOT be re-applied.**
  Evidence: measured Rondônia-2016 forest medians were red(B04)=884, NIR(B08)=2784. Under `v/10000`
  this gives NDVI = 0.518 (plausible Amazon forest). Re-applying −1000 gives a **negative red band**
  and NDVI = 1.139, which is **physically impossible** (NDVI ≤ 1). The measured convention is the only
  possible one.
  *This section is why the plan refused to guess: had we assumed the offset applied, every index and
  every QC bound in the study would have been silently wrong.*
- **Order of operations (the round-4 draft was self-contradictory — it clipped to `[0,1.5]` then
  claimed features lived in `[0,1]`):**
  1. Convert DN → ρ.
  2. **Measure** the out-of-range fraction (`ρ < 0` or `ρ > 1`) over the support — *before any clipping*.
  3. **Fail the site-year if that fraction > 1%** (this is the L2 check).
  4. Otherwise **clip to `[0, 1]`.**
- **Every** downstream quantity — QC bounds, Theil–Sen coefficients, NDVI/NDMI/NBR, brightness — is
  computed on `ρ ∈ [0,1]`, never on DN and never on unclipped values. There is no `[0,1.5]` regime.

### L1 — Compositing windows (per site, identical across every feature year)

Set from published monthly-precipitation climatology (CHIRPS/WorldClim), verified and recorded in the
paper **before fitting any risk model**. (Not "before any outcome is inspected" — the prior study
already inspected these outcomes; see §Outcome-informed choices.) Not "Jun–Sep everywhere": that is
not one phenological regime across these biomes.

| Site | Lat | Regime | Window (fixed, all years) |
|---|---|---|---|
| rondonia | 9.9°S | Amazon | Jun 1 – Sep 30 |
| sao_felix_xingu | 6.6°S | Amazon | Jun 1 – Sep 30 |
| mato_grosso | 12.4°S | Amazon | Jun 1 – Sep 30 |
| tshopo_drc | 0.4°N | Congo equatorial | Jun 1 – Aug 31 |
| mai_ndombe_drc | 2.4°S | Congo | Jun 1 – Aug 31 |
| riau_sumatra | 0.4°N | Equatorial peat (weak dry season) | May 1 – Sep 30 |
| santa_cruz_bolivia | 16.8°S | Chiquitano dry forest | May 1 – Sep 30 |
| gran_chaco_paraguay | 22.2°S | Gran Chaco dry forest | May 1 – Sep 30 |

**The table above is now an EXPECTED-VALUE CHECK, not the rule.** A biome-level window rule breaks for
basin-wide random sites — northern and southern Amazon (or Congo) boxes can sit in *opposing* rainfall
seasons, which would recreate the very phenology confound this section exists to prevent. So the window
is **derived per site by a deterministic algorithm**, applied uniformly to **all 20 sites including the
8 legacy ones**:

> **Window = the 4 consecutive calendar months (circular over the year) with the lowest total long-term
> precipitation at the box centre**, from **CHIRPS monthly climatology over 1991–2020 only** (pre-2021,
> pinned and file-hashed). **Tie → the earliest starting month.** Window = day 1 of month 1 → last day
> of month 4.

Fixed 4-month length removes another free parameter. Computed **at draw time, before any imagery is
downloaded**, then frozen. If the algorithm disagrees with the legacy table above for some site, **the
algorithm wins** — the table was hand-set and the algorithm is the locked rule.

#### AMENDMENT-3 (2026-07-14) — the feature window is 2018–2020; 2016–2017 do not exist

**Caught by measuring the live archive after the first composite downloaded, before any model was fit.**
Evidence: `results/product_census.md`.

The plan locked a feature window of **2016–2020** and, in L2, a gate of **median per-pixel
clear-observation count ≥ 8**. Those two are incompatible, and no code change can reconcile them.

A pixel's clear-observation count **cannot exceed the number of Sentinel-2 L2A products that overlap
it** in the window. Sentinel-2B did not launch until **March 2017**, and the early L2A archive is thin.
Measured against the live CDSE catalogue over the locked L1 windows:

| year | sites with ≥ 8 products (of 19) |
|---|---|
| 2016 | 12 |
| 2017 | 16 |
| 2018 | **19** |
| 2019 | **19** |
| 2020 | **19** |

Because L2 drops a **site whole** if **any** of its site-years fails, only **12 of 19** sites survived —
and that is an **upper bound**, since realized clear counts fall further after SCL masking. The frame
needs **12/12** and the combined cohort floor is **14**. **The study as locked was not viable.**

This was not visible before download. Phase 0 verified the reflectance convention and band availability
against live CDSE, but it **never counted acquisitions per site-year** — it checked that the data was
*correct*, not that enough of it *existed*. That is the gap this amendment closes.

**Fix: `FEATURE_YEARS = (2018, 2019, 2020)`.** It is the smallest change that makes the study viable:

- Every one of the 19 sites clears the product floor in every remaining year, so the frame can reach
  12/12 and the cohort floor of 14 is met.
- **Nothing else moves.** Label years stay **2021–2024**. The **≤ 2020 temporal firewall** is untouched.
  The pre-2021 sampling frame is **not redrawn** — its candidate/draw hashes still stand, and the
  cohort, box geometry, strata and CHIRPS seasonal windows are **byte-identical** (verified). The
  surviving 2018/2019/2020 periods are the *same* month-of-year windows as before; only 2016 and 2017
  were removed.
- **Block B is deliberately NOT shortened.** `b_trend` is fit on Hansen lossyear codes 16–20, and Hansen
  covers 2016–2020 regardless of the optical archive. The imagery axis (`FEATURE_YEARS`) and the Hansen
  axis (`HANSEN_TREND_YEARS`) are now separate constants. They were previously one shared implicit axis
  inside `_slope()`, so shrinking the window would have fit 3 x-values against block B's 5 y-values and
  **silently corrupted the contagion baseline** — the very control the headline estimand is measured
  against. Regression test: `risk/tests/test_trend_axes.py`.

**State the cost honestly. This is not a free fix, and it cuts at the question.**

The condition history drops from **5 annual points to 3**. Every trend feature (the block-D `_slope`
features, and the Theil–Sen PIF normalization) is now fit on three points. Consequences that go in the
paper, not in a footnote:

1. The paper **cannot claim "five years of trajectory."** The estimand becomes: does a **three-year**
   (2018–2020) condition history add incremental predictive information beyond contagion?
2. **A null result is now harder to interpret.** "Condition history carries no incremental signal" and
   "three years is too short a history to detect the signal" become **harder to separate**, and the
   design can no longer cleanly distinguish them. The deflationary reading was always an acceptable
   outcome of this study; it is now a **weaker** claim than the one originally planned.
3. The trend features are noisier: a 3-point slope has far less leverage than a 5-point slope, which
   **biases the study toward the null** on exactly the block under test (C/D), while block B (contagion)
   keeps its full 5-point Hansen trend. **The comparison is therefore conservative against the
   hypothesis** — if history still wins, that is strong; if it loses, the shortened window is a live
   alternative explanation and must be named as one.

**Rejected alternatives** (and why):

- *Relax the L2 gate for 2016/2017 only.* Keeps 5 years, but a 2–3 observation median composite is
  noisy, and a per-year gate destroys the "identical treatment in every year" property L1 exists to
  guarantee. A trend fit across years of unequal quality is precisely the artifact this plan was built
  to exclude.
- *Shift the design to 2018–2022 features → 2023–2024 labels.* Keeps 5 years, but collapses the label
  window to 2 years (far fewer positives) and **invalidates the already-drawn pre-2021 frame**, which
  would have to be redrawn — reopening outcome-blindness.
- *Accept a 12-site cohort.* Sits below the locked floor of 14, and 12 is an upper bound.

### L2 — QC gate (per site-year; failing ANY → the **site** is dropped whole, never interpolated)

Sensor-quality variables **only**. Deliberately NOT NDVI-based: rejecting on NDVI anomaly would select
on the predictor of interest and preferentially discard genuine widespread degradation.

**Population for every statistic below (previously undefined — it decides which sites survive):** the
**fixed condition support pixels inside the unbuffered analysis box** (see L6), i.e. exactly the
pixels the features are computed on.

| Check | Threshold |
|---|---|
| Median per-pixel clear-observation count over the support | **≥ 8** |
| Fraction of at-risk cells whose support has median clear-obs ≥3 **in every year** | **≥ 95%** |
| Post-mask nodata fraction over the support | **< 5%** |
| PIF pixel count (buffered extent), **native Hansen 30 m pixels** | **≥ 5,000** |
| Out-of-range reflectance fraction (L0) | **≤ 1%** |
| Normalization gain `a` (per band) | **∈ [0.5, 2.0]** |
| Normalization offset `c` (per band, reflectance units) | **∈ [−0.1, 0.1]** |

Anomalous NDVI is **flagged as a sensitivity, never an exclusion.** Failure handling and floors are
governed by **L13.5–L13.6**: a failed *frame* site is replaced from its pre-drawn queue; a failed
*legacy* site is simply dropped (never replaced from the frame queue); the frame cohort needs 12/12 or
the generalization analysis is not run; the combined cohort floor is 14.

### L3 — Radiometric normalization (complete, deterministic)

- **Reference year: 2020.** All other years are mapped *onto* 2020.
- **PIF population** (≤2020 data only — no label leakage): Hansen pixels with `datamask==1`,
  `treecover2000 ≥ 70`, **no GFC loss 2001–2020**, ≥3 cells (1,920 m) from any 2001–2020 loss pixel,
  and **"clear" = clear-observation count ≥ 5 in every one of the 5 years** (previously undefined).
- **Estimator:** `sklearn.linear_model.TheilSenRegressor(fit_intercept=True, random_state=42,
  max_subpopulation=10000)`. If PIF pixels > 200,000, take a seeded random subsample of 200,000
  (`numpy` default_rng(42)).
- **Fit:** per band `b`, per year `y ≠ 2020`, regress `ρ_{b,y} → ρ_{b,2020}` over PIF pixels →
  `ρ̂ = a_{b,y}·ρ + c_{b,y}`. Applied to **reflectance, before indices** — NDVI/NDMI/NBR are computed
  from normalized reflectance and are never themselves normalized.
- **Post-transform range check.** L0's clip to `[0,1]` happens *before* normalization, so the
  Theil–Sen transform can push values back outside it. **Re-verify and re-clip to `[0,1]` after
  applying each transform**, and record the post-transform out-of-range fraction.
- **Fallback: none.** PIF count < 5,000, or a coefficient outside its L2 bound → the site-year fails
  QC and the **site is dropped**. No silent degradation, no imputation.

### L4 — Headline estimand + concordance decision table

*(Round-2 draft was a blocker: it said "the ΔAP CI excludes 0" but there are eight per-site CIs and no
locked aggregate; and "excludes 0" does not specify direction.)*

- **Primary effect** `θ` = **site-equal mean ΔAP** across evaluable sites (each weight `1/n_eval`),
  for the primary contrast `S+B+C` vs `S+B+C+D`.
- **CI:** **paired hierarchical block bootstrap** — resample **sites** with replacement, then within
  each drawn site resample **spatial blocks** (L7). Both arms are scored on the **identical**
  resample. **2,000 replicates, seed 42.** This propagates within-site *and* across-site uncertainty.
- **Decision table** (evaluated on both pipelines; nothing is chosen post hoc):

| Normalized CI | Unnormalized CI | Verdict |
|---|---|---|
| lower bound > 0 | lower bound > 0 | **HISTORY ADDS VALUE** |
| upper bound < 0 | upper bound < 0 | **HISTORY HARMS** |
| contains 0 | contains 0 | **NULL** |
| any other combination | | **INCONCLUSIVE** — both reported, neither promoted |

- Paired Wilcoxon is reported as a **secondary** statistic, with exact `n_eval` stated. Evaluated on
  the combined cohort (primary) and, separately, via the **frame-only LOSO** (L13.8).

### L5 — Eligible-pixel universe (numerator and denominator share it exactly)

`lossyear` is single-valued per pixel (0 = none; N = year 2000+N), so these sets are disjoint by
construction and the ratio is bounded in [0,1].

- `A(cell)` = count of Hansen pixels with **`datamask == 1`** (valid land) in the cell. **Cells with
  `A == 0` are excluded.**
- `U(cell)` = pixels in `A` with **`treecover2000 ≥ 30`**.
- **Denominator** `GFC_eligible_forest_2020(cell)` = `|{p ∈ U : lossyear == 0 OR lossyear ≥ 21}|`
  (standing at end-2020: never lost, or lost only in the future window).
- **Numerator** `future_loss(cell)` = `|{p ∈ U : lossyear ∈ [21,24]}|` ⊆ denominator.
- **At-risk** iff `GFC_eligible_forest_2020(cell) ≥ 0.25 × A(cell)` — **25% of valid LAND area, not
  25% of `U`.** *(Round-2 draft was a blocker: `U` already contains only tree-cover pixels, so
  "≥25% of `U`" admitted a cell holding one surviving forest pixel.)*
- **Positive** iff `future_loss / GFC_eligible_forest_2020 ≥ 0.25`. Sensitivity at 0.10 and 0.50.

**Naming:** the mask is `GFC_eligible_forest_2020` — *not* "forest at 2020". It is year-2000 tree cover
minus GFC-recorded loss; it omits regrowth and inherits GFC false negatives. **It is not an independent
2020 forest map**, and the paper says so.

### L6 — Resampling and the Hansen→Sentinel overlay rule

| Layer | Native | Rule |
|---|---|---|
| B02/B03/B04/B08 reflectance | 10 m | bilinear (reprojection only) |
| B11/B12 (SWIR) reflectance | **20 m** | bilinear to the 10 m grid; **effective resolution reported as 20 m** |
| SCL (categorical) | 20 m | **nearest neighbour** |
| Clear-observation counts | 20 m | **area-weighted aggregation** (never bilinear) |
| Hansen `lossyear` / `treecover2000` / `datamask` | 30 m | **never warped, never interpolated** |

**Hansen → per-cell counting: pixel-center inclusion.** A Hansen pixel counts toward a cell iff its
**center** falls inside the cell's bounds. *(Correction: the existing `validate_gfw.build_reference`
slices a rectangular window and takes an **unweighted mean** — it is NOT area-overlap weighted, as an
earlier draft of this plan claimed. The new code implements the pixel-center rule explicitly.)*

**Hansen → Sentinel condition support (previously computationally undefined).** Derive the boolean
eligibility mask at 30 m, then rasterize it onto the master 10 m grid by **pixel-center containment**:
a 10 m Sentinel pixel joins the support iff its center falls inside an eligible Hansen pixel.
Implemented as nearest-neighbour sampling of the **boolean** mask (for a boolean, nearest-neighbour
*is* pixel-center containment). `lossyear` itself is never interpolated — only the derived boolean.
**The identical support mask is applied in all 5 years.**

### L7 — Spatial block bootstrap (fully specified geometry)

**Correlogram (fully specified — these choices change `L`):**
- **Residual:** the **Pearson residual** of the logistic regression,
  `r_i = (y_i − p̂_i) / sqrt(p̂_i(1 − p̂_i))`, with `p̂` **clipped to `[1e−6, 1 − 1e−6]`** to avoid a
  divide-by-zero. (Not response/deviance/weighted — locked.)
- **Estimator:** **Moran's I** per lag bin, with a binary weight matrix for that bin.
- **Lag bins:** integer cell lags `k = 1..20`; a pair `(i,j)` joins bin `k` iff its center-to-center
  distance / 640 m falls in `[k − 0.5, k + 0.5)`.
- **Minimum pairs per bin: 500.** Bins with fewer pairs are skipped.
- **Range** = smallest bin `k` (with ≥500 pairs) where Moran's I < **0.1**.
- If **no** bin has ≥500 pairs, or **no** bin drops below 0.1 within `k ≤ 20` → the site's CI is
  **UNRELIABLE**.

**Block size and the over-blocking gap (round-4 blocker):**
- **Which residuals:** the **maximum** range across **both primary-contrast arms** (`S+B+C`,
  `S+B+C+D`) **and both pipelines** (normalized, unnormalized) — conservative, and not selectable
  after the fact.
- `L` = **max(2, measured range)**. **There is no upper clamp at 8.** *(The round-3 draft clamped every
  range to 8 cells but only flagged UNRELIABLE beyond 20 — so a measured range of 15 silently got an
  8-cell bootstrap and an overconfident CI.)*
- **If the measured range exceeds 12 cells (≈7.7 km, ~30% of a site's linear extent), the block is too
  large for a meaningful within-site bootstrap → that site's CI is UNRELIABLE.**
- **Usable-block-placement rule (added by AMENDMENT-1).** Cell *count* does not establish block-bootstrap
  adequacy: 300 at-risk cells with `L=12` is ~2 block-equivalents, and a **fragmented** support yields
  fewer usable placements than a compact one. So compute, per site, the number of **distinct block
  origins whose L×L window contains ≥1 at-risk cell** (`usable_placements`). **If
  `usable_placements < 20`, that site's CI is `UNRELIABLE`.** Report `usable_placements` for every site
  alongside at-risk area and support dispersion.
- **Any evaluable site whose CI is `UNRELIABLE` *or* `undefined` (zero-positive resamples) forces the
  L4 headline verdict to `INCONCLUSIVE`.** Locked now, so it cannot be waived later.
- **Inferential adequacy is decided HERE, not by AMENDMENT-1's ≥300 support floor**, which makes no
  bootstrap or AP guarantee whatsoever.

**Geometry:**
- **Moving-block bootstrap** on the 2-D cell grid — `L × L` cell squares at **random origins** (overlap
  permitted), drawn until resampled cell count ≥ the site's cell count; partial blocks at site edges
  are retained.
- **Paired:** both arms of a contrast are scored on the **identical** block draws.
- **1,000 replicates, seed 42** (per-site); **2,000** for the hierarchical L4 estimand.
- **Zero-positive replicate** → AP undefined → discard and redraw, up to 10× the target draw count.
  If >20% of draws are zero-positive, the site's CI is **undefined**, not fudged.
- **Interpretation:** the site-resampling component of the L4 hierarchical CI is **empirical
  uncertainty over the realized site set, NOT population-level inference.** For the **8 legacy** boxes
  it is empirical only; the **12 frame-sampled** boxes (L13) are a random draw from a defined pre-2021
  frame, so their site-resampling component does support a modest generalization claim — bounded by
  that frame.

### L8 — Models, grids, weighting, tie-breaks

- **Weighting (estimand is a random SITE, not a random cell):** each of the `n_training_sites` training
  sites carries **equal total weight** (site weight ∝ 1/n_cells); within a site, class-balanced weights.
- **Inner-CV:** leave-one-training-site-out over the training sites only (**`n_training_sites` folds** —
  **19** for the combined LOSO and **11** for the frame-only LOSO, subject to actual QC survival; *not*
  the 7 the n=8 design assumed). This does **not** leak. **Objective: mean held-site AP.**
- **LR grid (primary):** L2 penalty, standardized features, `max_iter=5000`,
  **`C ∈ {0.001, 0.01, 0.1, 1, 10}`** (5 candidates).
- **GBM grid (sensitivity):** `HistGradientBoostingClassifier`, `random_state=42`, early stopping off.
  **5 candidates — identical budget to LR**, ordered simplest/most-regularized first:

  | # | learning_rate | max_leaf_nodes | min_samples_leaf | l2_regularization | max_iter |
  |---|---|---|---|---|---|
  | 1 | 0.05 | 7  | 100 | 10.0 | 400 |
  | 2 | 0.05 | 15 | 50  | 1.0  | 300 |
  | 3 | 0.10 | 15 | 50  | 1.0  | 200 |
  | 4 | 0.05 | 31 | 20  | 1.0  | 300 |
  | 5 | 0.10 | 31 | 20  | 0.1  | 200 |

- **Deterministic tie-break:** favour the **simpler / more regularized** model — for LR the smallest
  `C`; for GBM the candidate **earliest in the table** (it is ordered for exactly this purpose).
- **Zero-positive inner fold** → excluded from the tuning mean; **the number of valid folds is
  reported.** If **< 4** valid folds remain, fall back to the most-regularized candidate (LR `C=0.001`
  / GBM #1) and record that this happened.
- **One-class training site** → balanced within-site weighting is undefined; assign the site's full
  weight to its observed class and record it.
- **Missing values:** GBM handles NaN natively. **LR: median-impute using the `n_training_sites`
  training sites only**
  (fit on train, applied to the held-out site), **plus a binary missingness indicator** per imputed
  feature.

### L9 — Manual label audit

- **Strata:** **surviving sites only** × 3 GFC future-loss bins (`0`, `(0, 25%)`, `≥25%`); **2 cells per
  stratum ≈ 120 cells** at 20 sites. **Weighted label-validity estimates are reported SEPARATELY for the
  legacy and frame-sampled cohorts** — a pooled estimate could not reveal whether label validity differs
  between purposively-chosen and randomly-drawn sites, which is exactly what we need to know. Inclusion probabilities retained for weighted estimates.
- **Sparse stratum (< 2 eligible cells, matching the 2-cell target): census it** (take all), and **do
  not redistribute** the unused
  allocation to other strata. Weighted estimates use the retained inclusion probabilities.
- **Imagery:** high-resolution before (≤2020) and after (≥2024); source and acquisition dates recorded
  per cell.
- **Blinded:** the interpreter does not see model risk scores.
- **Coded as:** land-use conversion / fire / harvest-plantation cycle / natural disturbance / apparent
  GFC false positive.
- **Reliability:** a **10% duplicate-coded subset**, re-interpreted by the same blinded interpreter
  after a ≥2-week gap, to report intra-rater agreement. (A second interpreter would be better; one may
  not be available, and this is the honest substitute.)

### L10 — Feature dictionary (exact formulas; no tunable leftovers)

Units: metres. Cell = 640 m. All features use data ≤ 2020 — **assert this in code.** Spatial features
are computed on the **buffered** grid (L11) and read out only for interior cells.

`L20(c)` = prior-loss fraction of cell `c` = `|{p ∈ U(c) : lossyear ∈ [1,20]}| / |U(c)|` (0 if `|U|=0`).

**S — stock/context** (in every non-null arm)
| Feature | Definition |
|---|---|
| `s_forest_frac` | `GFC_eligible_forest_2020(cell) / A(cell)` ∈ [0,1] |
| `s_treecover_mean` | mean `treecover2000` (0–100) over eligible pixels |
| `s_clearobs` | **median** clear-observation count over the cell's 10 m support, year 2020 |

**B — contagion** (Hansen only; no imagery)
| Feature | Definition |
|---|---|
| `b_own_prior_loss` | `L20(cell)` |
| `b_ring{1,2,3,5}` | mean of `L20` over cells at **Chebyshev radius exactly r**; denominator = ring cells with `|U|>0`; NaN if none |
| `b_dist_nearest_loss` | Euclidean distance (m), cell center → center of nearest cell with `L20 ≥ 0.25`. **Capped at 4,000 m** (= buffer width = largest fully observed distance) |
| `b_dist_censored` | 1 if no such cell within 4,000 m, else 0 |
| `b_time_since_loss` | `2020 − max(lossyear)` in that nearest-loss cell, **taken over prior years `lossyear ∈ [1,20]` ONLY**, in years; **25** if censored. **⚠ LABEL LEAK GUARD:** an unrestricted `max(lossyear)` could select a *future* (2021–24) loss year from the same cell, pulling the label into a feature. **Assert every uncensored value ∈ [0,19].** |
| `b_density_{1,3,5}` | **numerator:** pixels within a **1,920 m circular radius** of the cell center with `lossyear` in the last `w` years (w=1 → `==20`; w=3 → `∈[18,20]`; w=5 → `∈[16,20]`). **Denominator: `datamask==1` valid-land pixels in that same circle.** Empty neighbourhood (no valid-land pixels) → NaN → L8 missing rule. |
| `b_trend` | OLS slope of the annual loss-pixel count within the 1,920 m radius over 2016–2020 (5 points), pixels/yr — is the local frontier accelerating? |

**C — condition-static** (2020 only, fixed support, normalized reflectance)
`NDVI=(B08−B04)/(B08+B04+1e−6)`; `NDMI=(B08−B11)/(B08+B11+1e−6)`; `NBR=(B08−B12)/(B08+B12+1e−6)`
| Feature | Definition |
|---|---|
| `c_{X}_{mean,std,skew}` | for X ∈ {NDVI, NDMI, NBR}, over support pixels |
| `c_{X}_{p10,p25,p50,p75,p90}` | percentiles over support pixels |
| `c_{X}_tailmass` | fraction of support pixels with `X < (site-year PIF median of X) − 0.20` |
| `c_brightness` | mean of `(B02+B03+B04)/3` over support, reflectance units [0,1] |

**D — condition-HISTORY** (2016–2020, **change terms only** — no levels; levels are C's job)
| Feature | Definition |
|---|---|
| `d_{X}_slope_mean` | OLS slope of the 5 yearly `mean(X)` vs year (per year) |
| `d_{X}_slope_std` | OLS slope of the 5 yearly `std(X)` vs year — heterogeneity rising (the EWS-flavoured term) |
| `d_{X}_slope_p10` | OLS slope of the 5 yearly `p10(X)` vs year — low tail deepening |
| `d_{X}_tstd_mean` | temporal std (n−1) of the 5 yearly `mean(X)` |
| `d_{X}_delta` | `mean(X)_2020 − mean(X)_2016` |

**Degenerate cases (locked):** support < **20** pixels → the **cell is excluded** from the study and
recorded. `skew` undefined at `std=0` → set 0 and flag. Ring with no valid cells → NaN → L8 missing-value
rule.

### L13 — Site set: n=20 via a PRE-2021 SAMPLING FRAME (supersedes the n=8 design)

**Why this exists.** The 8 legacy boxes were purposively chosen and *confirmed on GFW* — selection used
outcome knowledge. Adding 12 more hand-picked frontiers would only give tighter error bars around the
same bias. The 12 new sites are therefore drawn **at random from a frame whose eligibility uses only
data available at t0 (≤2020)**, so selection cannot depend on the 2021–24 outcome.

#### L13.1 — Temporal firewall (auditable)

The frame-building script reads Hansen `lossyear` and **immediately reduces it to the binary mask
`lossyear ∈ [1,20]`**. Years 21–24 are never exposed to any code path that touches site selection.
**The candidate frame and the full ordered draw are written to disk and SHA-256 hashed BEFORE a single
composite is downloaded**, and the hash is recorded in the results artifact. This is what makes the
"pre-2021" claim checkable rather than merely asserted.

#### L13.2 — Candidate universe (reproducible)

- **Lattice:** origin `(lon = −180.000, lat = +23.500)`, step **0.25° lon × 0.22° lat**, tiling east and
  south. **Membership by box CENTRE** falling inside a target biome polygon. Bounded to `|lat| ≤ 23.5°`.
- **Biome layer:** RESOLVE Ecoregions 2017 (`Ecoregions2017.shp`) — **version pinned and file-hashed**.
  The four groups (note "SE-Asian peat/palm" is **not** a RESOLVE class — it is a defined intersection):

| Group | Definition |
|---|---|
| Amazon moist | `BIOME_NAME = Tropical & Subtropical Moist Broadleaf Forests` ∩ `REALM = Neotropic` ∩ **HydroBASINS v1.0 level-3 Amazon basin polygon** |
| Congo moist | same BIOME ∩ `REALM = Afrotropic` ∩ **HydroBASINS v1.0 level-3 Congo basin (`HYBAS_ID = 1030020040`)** — **basin-restricted, symmetric with Amazon (AMENDMENT-2)** |
| SE-Asian peat/palm | same BIOME ∩ `REALM = Indomalayan` ∩ **PEATMAP (Xu, Morris, Liu & Holden 2018) Asia peat extent** |
| Tropical dry forest | `BIOME_NAME = Tropical & Subtropical Dry Broadleaf Forests` ∩ `REALM = Neotropic`, **plus the Gran Chaco ecoregion explicitly** (it straddles the dry-forest/savanna boundary in RESOLVE) |

**Every external layer is pinned — no "e.g.", no substitutions at build time.** Phase 0 downloads each,
records **file name, version, source URL, and SHA-256** in the results artifact, and **fails loudly** if
a hash does not match on a later run:

| Layer | Pinned version |
|---|---|
| Ecoregions | RESOLVE Ecoregions 2017, `Ecoregions2017.shp` |
| Amazon basin | HydroBASINS v1.0, level 3 — **record the exact feature IDs** composing the polygon, not just the dataset version |
| SE-Asia peatland | **PEATMAP** (Xu, Morris, Liu & Holden 2018, *Catena*), `Asia.zip` → `EA_Peatland.shp`, SHA-256 `8767e9ba8250770420cc555250f80b79b67410d00ae13ac629f4fe2ae9b8724e` |
| Precipitation climatology (L1) | CHIRPS v2.0 monthly, **1991–2020 only** |

- **Geodesic distances:** WGS84 geodesic (`pyproj.Geod.inv`), centre-to-centre. Not Euclidean degrees.

#### AMENDMENT-2 (2026-07-13) — the Congo stratum was not actually the Congo

**Caught by inspecting the first draw, BEFORE any imagery was downloaded.**

L13.2 restricted the **Amazon** group by an explicit basin polygon (HydroBASINS `6030007000`) but
defined the **Congo** group as merely `BIOME = moist broadleaf ∩ REALM = Afrotropic` — **with no basin
restriction at all.** That set spans West Africa, East Africa, Madagascar and the Seychelles, not the
Congo Basin. (The one HTTP-404 candidate in the screen was a box at 55.5°E — the *Seychelles*.)

The first draw therefore returned, in a stratum the paper would label "Congo Basin":
- `F2_P005.680_P0006.250` at **6.25°E — Ghana** (Upper Guinean forest)
- `F2_P008.320_M0012.250` at **−12.25°E — Guinea**

Both are ~3,000–4,000 km from the Congo Basin. The draw machinery was correct; **the stratum
definition was wrong**, and the asymmetry with the Amazon group was mine.

**Fix:** `congo_moist` = Afrotropic moist broadleaf **∩ HydroBASINS level-3 Congo basin
`HYBAS_ID = 1030020040`** (3.7M km²; verified to contain both legacy Congo sites, Tshopo and
Mai-Ndombe, and to exclude the Ghana and Guinea boxes). The four strata are now definitionally
consistent: two basin-restricted, one peatland-restricted, one ecoregion-defined.

**Integrity of the redraw.** The restricted Congo universe is a strict **subset** of the previous one,
so every box in it was already screened under the frozen L13.3 rule — no re-screen, no new
information. The candidate frame and ordered draw are re-hashed and re-frozen, still **before any
imagery is downloaded and with no 2021–24 data touched**, so the draw remains outcome-blind. The
superseded frame hashes are recorded below for audit.

- Superseded candidate_frame sha256: `3fbebc8bb2804b4b11ffc933ad1d66098336e2571f1c0a73fde2264f2d25b33e`
- Superseded ordered_draw    sha256: `e23c2bca4e92cf37874d4e8c435553ca57170e743185ca2e7f8710119e6cc9f6`

#### L13.3 — Eligibility (every criterion from ≤2020 data ONLY)

| Criterion | Threshold |
|---|---|
| Valid land (`datamask == 1`) share of box | **≥ 95%** — excludes coastal/water boxes |
| **At-risk cells in the box (per L5)** | **≥ 300** — a permissive **operational support floor** (see AMENDMENT-1). *Replaces the original `eligible forest ≥ 50% of valid land`.* |
| **Cumulative** loss 2001–2020 / valid land | **≥ 2%** — the box has a clearing history |
| **Recent loss 2016–2020 / valid land** | **≥ 0.5%** — **the box is still active as of 2020** |

*The recent-loss criterion is not optional garnish.* Cumulative loss alone does **not** establish an
active frontier: a box cleared entirely in 2001–2003 and quiet ever since would have satisfied the
round-1 draft. The 2016–2020 window is what makes "active as of 2020" true, and it uses no future data.

**Acknowledged frame bias (stated, not hidden):** these criteria select for **persistent, mapped,
stand-replacement clearing regimes**. They under-sample diffuse degradation, brand-new low-rate fronts,
and smallholder mosaics that GFC resolves poorly. That is a property of the generalization population
(L13.7), not a bug we can threshold our way out of.

#### AMENDMENT-1 (2026-07-13) — the box-level forest criterion was changed AFTER seeing data

**This is a protocol deviation, disclosed as such. It is NOT prespecified, and the paper will not
present it as though it were.**

**What was originally locked:** `GFC_eligible_forest_2020 / valid land ≥ 50%`.

**What triggered the change.** L13.5b requires the 8 legacy boxes to pass L13.3. Running that screen,
**5 of 8 failed, every one of them on that single criterion:**

| Site | eligible forest % | at-risk cells | cumulative loss % | recent loss % |
|---|---|---|---|---|
| gran_chaco_paraguay | 23.5 | 632 | 12.67 | 1.08 |
| riau_sumatra | 28.9 | 1100 | 34.03 | 8.86 |
| sao_felix_xingu | 35.1 | 1086 | 31.14 | 7.49 |
| mato_grosso | 37.8 | 1053 | 36.73 | 2.01 |
| rondonia | 38.1 | 1000 | 15.37 | 4.55 |
| tshopo_drc | 62.2 | 1978 | 37.32 | 12.84 |
| santa_cruz_bolivia | 87.9 | 1779 | 9.04 | 4.61 |
| mai_ndombe_drc | 94.4 | 2186 | 5.36 | 2.80 |

All 8 clear the activity criteria comfortably. The ≥50% bar was excluding precisely the **most
advanced** frontiers — all three Amazon sites, the peat/palm site, and the Chaco — and it would have
biased the 12 unseen frame boxes the same way, producing a "deforestation frontier" study that
systematically avoids active frontiers.

**What the change actually is — stated honestly.** It is **NOT** a redundancy fix. L5 governs which
*cells* are evaluated; L13.3 governs which *landscapes* constitute the study population. Removing the
50% rule therefore **changes the estimand**:

> from **forest-dominated frontiers** → to **active-frontier landscapes containing at least 300
> residual at-risk cells, including advanced and fragmented frontiers.**

Every scope claim in the paper must use the new wording. "Forest-dominated" is no longer true.

**On the ≥300 figure — what it does and does NOT justify.** It is a **permissive operational support
floor only.** It carries **no** claim to guarantee bootstrap or AP viability:
- L7 has **no upper clamp** on block size, so a site with `L=12` has 144-cell blocks and 300 cells is
  ~2 block-equivalents, not the ~5 an earlier draft of this amendment wrongly claimed.
- `N/L²` is a crude ratio anyway; a **fragmented** at-risk support yields fewer usable block
  placements than a compact one with the same count.
- Cell count says **nothing** about future positive prevalence, so it cannot guarantee AP is defined.

**Inferential adequacy is decided by L7/L4, not by this floor** — see L7's added
usable-block-placement rule. And **300 was chosen after observing the legacy count range** (min 632).
No threshold chosen now can honestly be called prespecified; its credibility rests on disclosure and
on being frozen *before* the frame is drawn.

**Outcome-awareness — the honest position.** No 2021–24 value was used computationally: both
eligible-forest share and at-risk-cell count are ≤2020 quantities, and the criterion counts **at-risk**
cells, never **positive** cells. **But the project cannot claim outcome blindness for the legacy
cohort**, because these 8 sites and their outcomes were analyzed in the prior paper — the site
identities themselves carry remembered outcome information.

**Consequences, locked:**
1. The **amended rule is frozen and SHA-256 hashed BEFORE any frame candidate, candidate count, or
   spatial distribution is inspected.** This is what keeps the 12-site frame prospectively clean.
2. **The frame-only analysis is the PRIMARY generalization analysis.** The combined/legacy analysis is
   **SECONDARY**, because legacy inclusion was revised with outcome-aware sites in view.
3. **Prespecified sensitivity: re-run everything under the ORIGINAL ≥50% rule.** This distinguishes
   conclusions about forest-rich frontiers from conclusions driven by admitting advanced, fragmented
   landscapes.
4. Report **candidate counts and exclusions by biome under BOTH the original and amended rules.**
5. Report per site: at-risk **area, connectedness/dispersion, and usable block placements** — not the
   raw count alone.
6. **São Félix's valid-land failure (94.9% vs 95%) is NOT revisited.** Moving a second threshold by
   0.1 pp immediately after observing a failure would be indefensible. It fails the primary screen on
   the locked, unrounded calculation and may appear only in a labeled sensitivity. If 94.9% proves to
   be a rasterization defect, the *measurement* is fixed universally — the threshold is not lowered.
7. **Box-level activity does not prove the residual at-risk forest itself sits on an active edge**
   (prior loss can lie away from the remaining forest). Stated as a limitation and checked
   descriptively using pre-2021 data only.
8. Cohort size is now **at most 19** (12 frame + 7 legacy, São Félix excluded). Every hard-coded
   "20 sites" / "19 training sites" / fold count / floor must use **actual surviving counts**.

#### L13.4 — The legacy-contamination fix (the frame must not be shaped by outcome-informed boxes)

**The frame is built and drawn with NO reference to the 8 legacy boxes.** Legacy locations do not
filter, exclude, buffer, or otherwise shape the candidate universe — *because those locations were
themselves chosen using future GFW knowledge, and letting them carve holes in the frame would smuggle
that knowledge back in.*

- **Separation is enforced among the 12 frame sites only**, at **≥ 50 km** geodesic.
- **The 50 km constraint is cross-stratum, so the biome processing order changes the sample** — it must
  therefore be locked. **Deterministic round-robin:** biome groups in the fixed order
  `amazon_moist → congo_moist → dry_forest → sea_peat`; for `round in 1..3`, for each group in that
  order, take the next box in that group's seeded permutation that is ≥50 km from **every frame box
  retained so far, across all groups**. No optimization, no reshuffling.
- **Replacements obey the same cross-stratum check:** a replacement is accepted only if it is ≥50 km
  from **all currently retained frame sites**, not merely from its own group's.
- **If a drawn frame box lands within 50 km of a legacy box: KEEP the frame box and DROP the legacy box**
  from the combined analysis (and record it). **The clean cohort has priority; the contaminated one
  yields.** Never the reverse.

#### L13.5 — Draw and replacement

- Stratify by the four groups; **3 boxes per group = 12**. Order each stratum's eligible boxes by a
  `numpy.default_rng(42)` permutation → an **ordered list**, written and hashed per L13.1.
- The first 3 boxes passing the L13.4 greedy separation are selected; **the rest of that stratum's
  ordered list is the pre-drawn replacement queue.**
- **QC failure (L2) → take the next box in that stratum's queue.** Never a re-roll, never by hand.
- **A failed LEGACY site is simply DROPPED — never replaced from the frame queue.** Replacing a
  purposive slot with a random box would launder one cohort into the other.
- **Report candidate counts, QC failures, and replacements *by biome group*.** QC survival selects for
  optically observable sites and may differ systematically by biome — that attrition must be visible,
  since deterministic replacement prevents cherry-picking but does **not** prevent attrition bias.

#### L13.5b — Legacy boxes must ALSO pass L13.3 eligibility

The scope claim "every box is an active frontier as of 2020" was asserted for *all* boxes but only
*established* for frame boxes — the 8 legacy boxes were never screened for ≥50% eligible forest or
≥0.5% recent loss. **Apply the L13.3 eligibility criteria to the 8 legacy boxes too.** A legacy box that
fails is **dropped from the combined analysis and reported.** This gives the combined cohort a single
coherent eligibility definition, so the two cohorts differ **only in how they were selected** — which is
the one thing we actually want to vary.

#### L13.6 — Floors

- **Frame cohort: all 3 QC-passing sites required in every biome group (12/12).** If any group falls
  short, **the frame-only generalization analysis is NOT run**, and the study reports the combined
  analysis as a case study only.
- **Combined cohort: ≥ 14 surviving sites**, else stop and re-plan. *(Supersedes the old "n<6 of 8".)*

#### L13.7 — Estimand and generalization population (locked)

Equal allocation (3 per group) means the frame-only estimand is an **equal-weighted four-biome-group
average** — *not* an average over the full candidate universe, whose groups have unequal frame sizes.
Declared here, not inferred later.

**Further: the ≥50 km sequential inhibition does NOT give every eligible lattice box an equal inclusion
probability** (accepting a box suppresses its neighbours). So the target is **the distribution induced
by this locked, spatially-inhibited sampling design** — treating it as uniform over every eligible
lattice box is an *approximation*, and we say so rather than quietly assuming it away.

The defensible generalization population is **not "active deforestation frontiers" in general.** It is:

> spatially separated (≥50 km), GFC-loss-affected-by-2020 (≥2% cumulative **and** ≥0.5% in 2016–2020),
> optically QC-passing 0.25°×0.22° boxes containing **≥300 residual at-risk cells**, in the four target
> biome groups. **(AMENDMENT-1: the original "high-remaining-forest ≥50%" clause is removed; the
> population now includes advanced and fragmented frontiers.)**

Every generalization sentence in the paper is bounded by that definition.

#### L13.8 — Two analyses, both full LOSO, both prespecified

1. **Combined LOSO** — all surviving sites (≤20); `n_eval` outer folds. **Primary.**
2. **Frame-only LOSO** — **12 outer folds, each trained AND tuned on the other 11 frame sites only.**
   Legacy sites **never enter training**. *(Merely subsetting the 12 test-site results out of models
   trained on all 19 others would still let outcome-selected legacy sites shape the fitted model — that
   is not a clean sensitivity, and it was the round-6 draft's mistake.)*
3. **Frame-only CI must match the equal-group estimand (L13.7).** Resampling all 12 sites together
   would let a replicate distort the biome composition and would no longer estimate an equal-weighted
   four-group average. So: **resample 3 sites with replacement WITHIN each biome group, compute the four
   group means of ΔAP, and average those four means equally** (nested with the L7 block bootstrap inside
   each drawn site). 2,000 replicates, seed 42.
4. **A disagreement between the combined and frame-only LOSO does NOT by itself identify selection
   bias** — the two also differ in **training size (19 vs 11 sites) and training-domain composition**, so
   model variance or training support could produce it. It is reported as a
   **"cohort-selection / training-composition sensitivity"** — and we do **not** decompose it into a
   clean selection-bias term, because **no available comparison holds training genuinely fixed while
   varying only cohort.** (An earlier draft claimed comparing combined-trained vs frame-only-trained
   predictions on the same 12 sites would isolate cohort selection. It would not — it isolates
   *training composition*.)
   The closest honest diagnostic, reported as such: **within the single combined LOSO, compare mean ΔAP
   on the 8 legacy held-out sites against mean ΔAP on the 12 frame held-out sites.** The training
   *procedure* is identical across those folds and only the evaluation cohort changes — though each
   fold's training set still differs by one site, so even this is suggestive, not dispositive.
   **We will not label anything "selection bias" on the strength of the combined-vs-frame-only gap alone.**
5. The frame-only analysis is the one that carries any generalization claim.

**Cost.** 20 sites × 5 years = **100 composites** (60 beyond the original 40), buffered per L11.

### L12 — Compositing graph (locked; these choices change both trajectories AND which sites pass QC)

- **Tile-level filter: `max_cloud_cover = 80`, uniform across every site and year.** Deliberately
  *permissive*: per-pixel SCL masking now does the real work, and a tight tile filter would discard
  granules that still hold usable clear pixels, lowering the clear-observation counts that L2 depends
  on. **This removes the per-site `max_cloud` override in `sites.py`** — one less free parameter.
- **SCL classes masked: `{0, 1, 2, 3, 8, 9, 10, 11}`** = nodata, saturated/defective, cast shadow,
  cloud shadow, cloud medium-prob, cloud high-prob, thin cirrus, snow/ice.
  **Kept: `{4, 5, 6, 7}`** = vegetation, not-vegetated, water, unclassified.
- **Dilation: a single 100 m square kernel (5 × 5 at 20 m SCL resolution) applied to the union mask**,
  identically for every class, every site, every year. One number, no per-class variation.
- **Masked median:** per pixel, the temporal median over **unmasked observations only**. A pixel with
  **zero** clear observations in a year → **NaN (nodata)**, and counts toward the L2 nodata fraction.
- **Implementation:** build the SCL mask **manually** rather than relying on `mask_scl_dilation`, whose
  default kernel semantics we cannot verify from the docs. Phase 0 confirms SCL availability and
  **records the openEO backend and process versions in the results JSON.**
- **Reproducibility:** pin and record `scikit-learn`, `rasterio`, `numpy`, and `openeo` versions;
  LR solver is **`lbfgs`**.

### L11 — Extent

**4 km buffer** beyond each analysis box (*not* 3 km — `b_ring5` reaches 5 × 640 m = **3.2 km**, so a
3 km buffer would have censored the outermost contagion ring, biasing arm B exactly where it matters).
The nearest-loss cap (4,000 m) is set to the fully-observed buffer distance. Spatial features are
computed on the buffered extent; **only the unbuffered interior is evaluated.** Hansen is mosaicked
across tile boundaries (Rondônia sits near one).

---

## Approach

### Phase 0 — Verify assumptions (before any downloads)
1. Confirm Hansen band URL patterns against the `lossyear` one in `sites.py`: `treecover2000`,
   `lossyear`, **`datamask`**. Read one window of each; confirm `treecover2000` is 0–100.
2. Confirm openEO exposes **SCL** and **B11/B12** for `SENTINEL2_L2A`, and an SCL mask/dilation
   process. The plan depends on this.
3. Cheap metadata query: clear-observation availability 2016–2020 at all 20 sites (L13), under the **L1**
   windows. **2016 is the thin year, not 2017** — Sentinel-2A flew alone all of 2016; 2B began
   acquisitions Mar 2017. Budget for 2016 being the binding constraint.

### Phase 1 — Data acquisition (regenerate ALL years, including 2016)
4. `risk/download_timeseries.py`. **Do not reuse the existing 2016/2024 composites** — different
   processing graph (no per-pixel cloud masking), therefore not radiometrically comparable.
   Regenerate **2016–2020 × 20 sites = 100 composites** (L13) with one identical graph.
5. **Bands: B02, B03, B04, B08, B11, B12** (+ SCL). SWIR added deliberately: it carries canopy
   **moisture (NDMI)** and **burn (NBR)** information NDVI cannot see, and degradation appears in
   moisture before greenness. *A null on a feature set that omitted SWIR would be worthless* — we
   must give the hypothesis its best shot before we are entitled to reject it.
6. **Per-pixel cloud masking (was missing entirely).** `max_cloud_cover` is a **tile-level metadata
   filter**; it does not remove cloudy pixels from the composite. Mask and **dilate** SCL cloud
   (high/med prob), cirrus, shadow, snow, saturated/defective, nodata **before** the temporal median.
   Retain a **per-pixel clear-observation count** raster per site-year.
7. **Buffered extent — 4 km, per L11** (not 3 km: `b_ring5` reaches 3.2 km). Mosaic Hansen across
   tile boundaries (Rondônia sits near one). Spatial features are computed on the buffered extent;
   **only the unbuffered interior is evaluated.** Otherwise ring fractions and nearest-loss distances
   are silently censored at the box edge — biasing the contagion arm exactly where it matters.
8. Record per site-year: median acquisition DOY, clear-obs count, solar zenith, within-composite
   dispersion. These become covariates in a robustness check (differing acquisition dates alone can
   manufacture an annual trend).
9. Apply the **L2** QC gate.

### Phase 2 — Grid, mask, labels
10. **Master grid.** One master 10 m grid per site; warp every annual composite onto it per **L6**;
    **assert identical CRS, transform, shape, pixel alignment** before feature extraction.
    (`ndvi_baseline.py` currently reads the second raster and *discards its transform and CRS*,
    assuming matching indices — survivable for 2 dates, fatal for a 5-year trajectory.)
    Patchify at `PATCH=64, STRIDE=64` (non-overlapping, ~1,600 cells/site).
11. Build `GFC_eligible_forest_2020`, at-risk set, and labels per **L5**.
12. Generalize `validate_gfw.build_reference()` to accept an arbitrary `(year_lo, year_hi]` window
    and an arbitrary Hansen band instead of hardcoding lossyear / 2016–2024 — **and replace its
    unweighted rectangular-block mean with the explicit pixel-center inclusion rule (L6).**

### Phase 3 — Normalization
13. Apply **L3**; interpret via **L4**. Residual per-cell trends are **potentially** ecological —
    never *proven* ecological. An additive offset cannot prove a residual trend is real, and we will
    not claim it does.

### Phase 4 — Feature blocks (all from data ≤2020; no 2021–24 imagery is ever read)

**Fixed pixel support (the single most important fix from review).** All condition features (C, D)
are computed over **one fixed pixel set per cell** — pixels in `GFC_eligible_forest_2020`, **the same
pixels in all 5 years**. Without this, a cell sitting just under the at-risk threshold (e.g. 24% prior
loss) would have its NDVI slope dominated by *that past clearing*, so the "condition trajectory" arm
would silently be measuring contagion and would appear to confirm the hypothesis for entirely
circular reasons. **Sensitivity:** re-run restricted to cells with **zero** prior loss.

| Block | Contents |
|---|---|
| **S — Stock/context** (in every non-null arm) | `GFC_eligible_forest_2020` area; mean `treecover2000` over eligible pixels; cell clear-observation count. Forest *stock* is not contagion and does not belong in B. |
| **A — Null** | Intercept only. AP ≈ test base rate. The floor every arm must clear. |
| **B — Contagion** (Hansen only, **no imagery**) | With **recency**, which the straw-man version omitted: loss fraction in rings r=1,2,3,5; distance to nearest prior loss (**capped, + censoring indicator**); **time since** nearest loss; loss density in **1-, 3-, 5-year** windows; **neighborhood loss trend** (is the local frontier accelerating?); own-cell prior loss fraction. Hobbling this baseline would make "condition helps" trivially and meaninglessly true. |
| **C — Condition-static** (2020 only, fixed support) | Per-cell distribution of **NDVI, NDMI, NBR**: mean, std, skew, p10/p25/p50/p75/p90; low-tail mass; mean brightness. A single look — no history. |
| **D — Condition-HISTORY** (2016–2020, **change terms only**) | OLS slope of mean NDVI / NDMI / NBR; OLS slope of **std** (heterogeneity rising — the EWS-flavoured term); OLS slope of p10 (tail deepening); temporal std of the mean; Δ(2020−2016). **No level terms** — levels are C's job; mixing them would let D win on snapshot information and fake a history effect. |

**Arms (nested, so incremental value is estimable):**
`A` · `S+B` · `S+C` · `S+B+C` · `S+B+C+D`

- **PRIMARY prespecified contrast: `S+B+C` vs `S+B+C+D`** → *does history add anything beyond
  contagion and a snapshot?* The user's hypothesis, properly nested. (The earlier `C vs D` was
  non-nested and could not estimate incremental value at all.)
- **Secondary: `S+B` vs `S+B+C`** → does condition add beyond proximity?

**Not lag-1 autocorrelation.** At 5 annual points a lag-1 AC estimate is noise. Features in D are
"EWS-inspired"; we make **no claim to test critical-slowing-down theory**. Sub-annual analysis is
**not pursued because observation density and project scope do not support a defensible sub-annual
design at these sites** — not because it is impossible in principle.

### Phase 5 — Model & evaluation
14. **Models.** **Regularized logistic regression (L2, standardized) is the simple primary.** GBM
    (`HistGradientBoostingClassifier`) is the capacity sensitivity, tuned in an **inner site-grouped
    CV over the `n_training_sites` training sites only** (19 combined / 11 frame-only) — which does
    *not* leak. Arbitrary fixed hyperparameters were
    the real risk: they could manufacture a **false null**. Identical tuning budget for both. Seed 42.
    Weighting per **L8**. Caveat stated: model capacity alone can never *prove* absence of signal.
15. **Protocol.** **Two full LOSO analyses per L13.8** — combined (all surviving sites, primary) and
    **frame-only (12 outer folds, trained and tuned on the other 11 frame sites only; legacy sites never
    enter training)**. Every number is out-of-site. **Leave-one-biome-out**
    as a descriptive secondary (most LOSO folds still see the same biome in training, so LOSO
    overstates transfer).
16. **Metrics.**
    - **Primary: paired within-site ΔAP** between nested arms. Not "lift" — unstable at tiny
      prevalence, undefined at zero. Report every site's base rate and positive count.
    - **Operational: precision & recall at a fixed alert budget** (top 1%, 5%, 10% of at-risk cells
      by risk score). Stated correctly as **"share of 2021–2024 positive cells captured"** — a
      **4-year cumulative** horizon, *not* "next year". **Additionally report area-weighted capture**:
      the fraction of all future-loss *pixels* falling inside alerted cells, which is what a
      practitioner actually cares about.
    - Class-weighted model outputs are **uncalibrated** → called **risk scores**, not probabilities.
    - **Zero-positive held-out site** → AP undefined; excluded from the paired test, reported
      explicitly, never silently dropped.
    - **No arbitrary "0.02 AP" success threshold** — it had no constant operational meaning. The
      headline is written from ΔAP CIs (per **L4**) and the alert-budget curves.
17. **Uncertainty.** Spatial block bootstrap per **L7** — non-overlapping cells are **not**
    independent; loss and residuals are autocorrelated over kilometres, so an i.i.d. cell bootstrap
    would be invalid. Distinguish **within-site map uncertainty** (block bootstrap) from
    **across-site generalization uncertainty**. Across-site: paired **Wilcoxon signed-rank on ΔAP**,
    reported as a **secondary** statistic with the **exact `n_eval` stated separately for the combined
    and frame-only analyses**. `n_eval` is *not* automatically 20 — QC failures and zero-positive sites
    reduce it, so no unconditional power claim is made. We lead with effect sizes and CIs.
18. **Attribution.** **Grouped/conditional permutation importance by feature family** (permuting one
    of several correlated percentiles assigns importance arbitrarily), plus **coefficient stability
    across folds**. Reported as **associations, not drivers**.
18b. **Acquisition-metadata robustness (explicitly SECONDARY, never the headline).** Add the per
    site-year acquisition covariates (median DOY, clear-obs count, solar zenith, within-composite
    dispersion) to **both** arms of the primary contrast and confirm ΔAP is materially unchanged. If
    ΔAP collapses once acquisition geometry is controlled, the "history" signal was an artifact of
    *when the scenes were taken*, and we report that.
19. **Label-validity audit** per **L9**. Where it cannot resolve the Hansen-to-Hansen confound, the
    claim is **restricted** to "predicting future GFC detections from earlier GFC detections + imagery."

### Phase 6 — Reporting
20. Results JSON + figures: per-site base rates and positive counts; ΔAP by nested contrast with
    block-bootstrap CIs; alert-budget precision/recall curves (cell and area-weighted); risk maps vs
    actual 2021–24 loss at 2 sites; grouped-permutation importance; normalized-vs-unnormalized
    concordance (**L4**); zero-prior-loss sensitivity; the audit table.
21. Draft the companion paper. **Reporting rule fixed before fitting**: the headline follows the
    primary contrast under the **L4** three-way rule, whatever it shows — positive, null, or
    inconclusive. The 25% label threshold is primary and will not be swapped post hoc.

---

## Outcome-informed choices (disclosed — this is not a clean pre-registration)

- The **8 legacy sites** were selected as *confirmed* deforestation frontiers using GFW (outcome-informed).
  The **12 new sites** are randomly drawn from the L13 pre-2021 frame and are NOT outcome-informed.
- The 2024 imagery and 2016–2024 Hansen outcomes at these sites were already analyzed in the prior paper.
- Kalimantan was excluded on data-quality grounds after inspecting its composites.
- The analysis plan is fixed *before fitting any risk model* — the most we can honestly claim.

## Key decisions & tradeoffs

| Decision | Chosen | Rejected & why |
|---|---|---|
| Paper | Separate companion paper | Bolting on would dilute the detector paper's thesis. |
| Backbone | **No ResNet50** — features + LR/GBM | The prior paper *already proved* the CNN fails out-of-biome (F1≈0.000 at 2 sites) and loses to NDVI at 5/8. Forecasting on the proven-weakest component would be self-inflicted. |
| Bands | RGB + NIR + **SWIR** | NDVI-only would make a null meaningless — moisture shows degradation before greenness. |
| Cloud handling | **Per-pixel SCL mask + dilation** | `max_cloud_cover` is tile-level metadata only; residual cloud manufactures 5-year trends. Fixes an existing pipeline flaw. |
| Condition support | **Fixed `GFC_eligible_forest_2020` pixels** | Whole-cell stats let past clearing masquerade as "condition trajectory" → **false confirmation**. |
| Contagion block | **With recency** | Pooled 2001–2020 loss is a straw man; beating it proves nothing. |
| Primary contrast | **`S+B+C` vs `S+B+C+D`** (nested) | `C vs D` is non-nested; cannot estimate incremental value. |
| Normalization | Primary=normalized, **concordance required** (L4) | "With and without" alone leaves two candidate headlines to choose between post hoc. |
| At-risk mask | Per-**pixel** treecover≥30, `datamask==1` | `mean(treecover2000)≥30%` is not "30% forested". |
| Label | Loss ≥25% of **remaining 2020 eligible forest** | "% of cell area" makes the estimand depend on initial stock. |
| Model | **Regularized LR primary**, nested-tuned GBM sensitivity | Fixed arbitrary hyperparameters risk a **false null**; inner site-grouped tuning does not leak. |
| Uncertainty | **Spatial block bootstrap** (L7) | Non-overlapping ≠ independent. |
| Metric | Paired ΔAP + **alert-budget (cell + area-weighted)** | Lift unstable at low prevalence; ROC-AUC flatters. |
| Covariates | Imagery + Hansen only; **no roads/tenure/PA** | Known-strong predictors would swamp the comparison of interest. Stated as a scope limit. |
| Extent | **4 km buffer** (L11), evaluate interior | Ring/distance features censored at box edges otherwise; `b_ring5` alone reaches 3.2 km. |
| Reflectance | **Converted to ρ∈[0,1] up front** (L0) | L2A ships as 0–10,000 DN; QC bounds stated in reflectance units are meaningless on DN. |
| Headline rule | **Site-equal mean ΔAP + hierarchical block-bootstrap CI, concordance table** (L4) | Eight per-site CIs with no aggregate rule leaves the headline selectable post hoc. |

## Risks / open questions

1. **[HIGHEST] Radiometric/phenological drift manufacturing a fake history signal** → false
   confirmation. Mitigated by SCL masking, fixed site-specific seasons (L1), acquisition-metadata
   covariates, PIF normalization (L3), and the **L4 concordance rule**. Residual risk stated.
2. **Normalization could remove the real signal** (stable forest may itself be degrading). The two
   failure modes point in opposite directions — hence L4's three-way rule, where discordance is
   reported as **inconclusive** rather than resolved in whichever direction we prefer.
3. **Hansen supplies both contagion features and labels** → correlated errors may inflate arm B
   ("predicting Hansen from Hansen"). Partially addressed by the L9 audit; otherwise the claim is
   restricted to predicting future *GFC detections*.
4. **RESOLVED (Josh, 2026-07-13): expanded to n=20** via the L13 pre-2021 sampling frame. Residual
   risk: the 8 legacy boxes remain outcome-informed, so the **12-site frame-sampled sensitivity** is
   the one that carries any generalization claim. If the 20-site primary and the 12-site sensitivity
   disagree, that disagreement is reported as a selection-bias finding, not resolved by preference.
5. **640 m cells / annual steps may be too coarse** to see a degradation precursor at all (selective
   logging is tens of metres, sub-annual). A null could be a **resolution** result, not a
   **no-such-signal** result. We must not conflate the two.
6. **2016 is the thin acquisition year** (S2A alone) → risk of dropping sites at the L2 gate.
7. **Prespecified edge cases** (assert in code): empty PIF population; no prior-loss cell in a site
   (distance → cap + indicator); zero-variance skew; nodata-heavy cells; tied year-of-minimum;
   held-out site with zero positives. Assert all feature years ≤ 2020.

## Out of scope

- Roads / socioeconomic / tenure / protected-area covariates.
- The ResNet50 land-cover CNN (deliberately unused).
- Near-real-time alerting or operational deployment.
- Predicting **frontier emergence**.
- Any modification to the existing detector paper or its results.
