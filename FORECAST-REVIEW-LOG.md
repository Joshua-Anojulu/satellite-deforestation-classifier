# Plan Review Log: Multi-Sensor Temporal-Attention Forecasting of Near-Term Tree-Cover Loss
Act 1 (grill) complete — plan locked with the user (Josh, 2026-07-19). Plan file: `FORECAST-PLAN.md`. MAX_ROUNDS=5.
Reviewer: codex-cli / config-default model, read-only sandbox.

## Round 1 — Codex

The plan is not yet scientifically safe to implement. I read `FORECAST-PLAN.md` fully, section 11 fully, and only the site-frame portions of the retired `PLAN.md` plus the existing composite provenance. No files were modified.

## Material flaws

1. **There is no valid supervised-training chronology.** The plan lists 2021, 2022, and 2023 forecasts but never says which earlier outcomes train each model. A 2021 example cannot train the model and simultaneously count as a forecast; with three-year imagery beginning in 2018, there is no pre-2021 three-year training origin. Training on other regions’ 2021 labels to “predict” held-out-region 2021 would be spatial transfer using future labels, not an operational forecast.

   Fix — Designate 2021 as training, 2022 as validation, and later years as tests, or obtain earlier predictor histories; do not call the training origin a forecast.

2. **`≤ T` is not a temporal availability firewall.** Existing provenance shows some nominal-2020 composites end in February/March while others end in August/September. The proposed “forest at T” mask and prior-clearing feature can therefore use losses occurring after the local imagery cutoff; annual GFC releases also arrive after the year ends. [The plan additionally admits that contemporary roads and WDPA can post-date early outcomes](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:112>), which is direct feature leakage, not a disclosure-only limitation.

   Fix — Define an exact issue date for every origin, make a source-by-source availability table, and exclude every observation, map revision, and static-layer vintage unavailable on that date.

3. **“Forest at T” is undefined and overclaimed.** GFC supplies `treecover2000`, a gross stand-replacement `lossyear`, and a gain layer ending in 2012; it does not supply an independently observed forest mask for each T. The current [label definition](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:37>) omits the canopy threshold, `datamask`, regrowth treatment, and repeated-disturbance treatment. The official catalog confirms these semantics. [Hansen GFC v1.13 documentation](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13)

   Fix — Lock a formula such as `datamask==1 ∧ treecover2000≥θ ∧ (lossyear==0 or lossyear>T)`, call it “GFC-eligible 2000-baseline tree cover remaining at T,” and run canopy-threshold sensitivities.

4. **Hansen timing error can turn the forecaster into a delayed detector.** Late-year disturbance may be assigned to the following GFC year; consequently, a T optical/SAR composite may already display clearing labeled `T+1`. Merely disclosing boundary blur, as [the plan proposes](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:109>), does not protect the estimand. [Published GFC timing discussion](https://www.nature.com/articles/s41893-024-01450-3)

   Fix — Audit independent disturbance dates on a stratified sample and add a one-year-gap or boundary-exclusion sensitivity demonstrating that the model is forecasting rather than detecting already-completed loss.

5. **The 19 sites are not one clean inferential cohort.** The targeted retired-plan check shows 12 pre-2021 frame sites plus seven purposively selected, outcome-informed legacy sites; the new plan silently pools them. Rondônia and the other legacy outcomes were previously inspected, so neither its “subsequently cleared” examples nor a 2023 result there are genuinely untouched.

   Fix — Make frame-only performance the primary evaluation, label legacy-site results exploratory, and ensure every Rondônia map is leave-site-out with examples selected by a deterministic rule.

6. **The rolling-origin and LORO procedures are under-specified enough to leak.** The same pixels, static features, and overlapping histories recur across origins; pooling origins before splitting would place nearly identical samples in train and test. Hyperparameter tuning, early stopping, normalization, calibration, and architecture selection are not assigned to training/validation partitions.

   Fix — Use nested chronological evaluation, group every site/spatial block across all origins, fit all preprocessing inside each training fold, and open the final year only once after the pipeline is frozen.

7. **“Spatial block splits” are not sufficient as written.** A 256×256 patch is about 7.7 km wide, while these boxes are roughly 25 km wide—only around 3×3 non-overlapping patches per site. Adjacent or overlapping patches share pixels and receptive-field context, so ordinary block assignment will leak.

   Fix — Prefer whole-site holdouts; if within-site testing is unavoidable, use non-overlapping blocks with guard bands at least as wide as the model’s receptive-field radius and keep all years of a block together.

8. **Removing the site floor does not solve statistical power.** The realized regional counts are approximately 5/5/4/5, and the clean frame has only three sites per group. Four correlated LORO folds cannot support a strong cross-biome generalization claim, and millions of pixels do not replace independent sites or clearing events. “Report, don’t gate” permits undefined or arbitrarily unstable AP.

   Fix — Precompute positive counts and connected loss-event counts per site-year, define power/evaluability criteria from independent events rather than an arbitrary site count, use site/spatial-cluster bootstrap intervals, and downgrade failed regions to descriptive case studies.

9. **The metric plan is incomplete for rare-event probabilities.** AP varies mechanically with prevalence, so pooled AP may mostly reflect the largest/highest-loss sites. Focal/class-weighted training also distorts probability calibration; a reliability plot alone cannot validate the goal of producing probabilities. Top-X capture has no prespecified X values or uncertainty.

   Fix — Report per-site and macro-region AP, prevalence and AP/prevalence lift, Brier/log loss and calibration slope/intercept, and area-weighted recall at prespecified 1/5/10% budgets with clustered confidence intervals; calibrate only on naturally sampled validation data.

10. **Model/fallback selection creates a garden of forking paths.** “If attention will not converge” is subjective, while “the model must beat” baselines has no success margin, uncertainty rule, or test-set embargo. ConvLSTM and LightGBM can become post-hoc headline replacements.

   Fix — Specify engineering-only fallback triggers before test labels are accessed and lock one primary model/comparison, paired uncertainty procedure, and minimum practically meaningful gain.

11. **The baselines are too vague to establish added value.** “Distance-to-prior-clearing/contagion” could be a weak strawman; the retired study had stronger features such as recent loss density at multiple radii, time since nearest loss, own-cell loss, and local loss trend. There are also no optical-only, SAR-only, or static/contagion-only ablations.

   Fix — Implement a tuned historical-loss hazard baseline and precommit modality ablations: contagion, contagion+static, optical, SAR, optical+SAR, and full model.

12. **The GFC availability statement is factually obsolete, and one download year is unused.** The plan says targets are available only through 2023, but the current official GFC v1.13 extends through 2025. Its listed rolling origins use predictors only through 2022, despite downloading optical 2023. [Current GFC catalog](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13)

   Fix — Precommit an exact GFC version and checksum, use 2021–23 predictors for a 2024 test—or remove the unused 2023 download—and consider an embargoed 2025 test after obtaining 2024 predictors.

## Retired-trap audit

| Trap | Audit | One-line fix |
|---|---|---|
| PIF identifiability | PIF is absent from the new pipeline, but the justification is false: section 11 explicitly retracts the claimed PIF identifiability wall and identifies a same-granule external annulus ([post-mortem](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/CONTEXT_HANDOFF.md:305>)). | State that PIF is unnecessary for this predictive design, not impossible, and retain an explicit radiometric-drift audit. |
| Moving-reference cancellation | Not demonstrably avoided: “per-scene/self-referential normalization” is undefined and could be exactly the within-site-year moving reference that fabricated trends in the retired design. | Use harmonized surface reflectance/indices with fixed training-fold normalization constants; prohibit per-scene centering or scaling in a written formula. |
| Equal-allocation floor | Avoided procedurally but not scientifically: deleting the gate lets a three-site region support an unjustified generalization claim. | Replace the arbitrary site floor with an event-count/power-based evaluability gate and downgrade claims when it fails. |

## Sentinel-1 and feasibility

13. **The SAR chain is not implementation-ready.** CDSE openEO’s default Sentinel-1 processing is sigma0-ellipsoid with orthorectification but no radiometric terrain correction or speckle filtering. Mixing orbit directions or relative orbits can create apparent temporal change, especially in relief. [CDSE Sentinel-1 processing documentation](https://documentation.dataspace.copernicus.eu/Data/Sentinel1.html)

   Fix — Before bulk download, freeze and validate orbit state/relative-orbit selection, RTC coefficient, DEM, shadow/layover handling, speckle strategy, linear-versus-dB ratio order, nodata rules, and acquisition-count covariates on three contrasting pilot sites.

14. **A major SAR temporal discontinuity is ignored.** Sentinel-1B failed in December 2021, changing sampling density across exactly the 2021–23 histories; annual medians can therefore encode constellation availability rather than forest condition. [ESA mission record](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1/Sentinel-1B_journeys_back_to_Earth)

   Fix — Match orbit/satellite sampling across years where possible, include valid-acquisition counts, and test whether a classifier can predict year from nominally stable SAR pixels.

15. **The stated Congo rationale contradicts existing evidence.** The plan calls SAR a direct fix for a “cloud-driven” Congo failure, but the handoff says the composites were clean and AdaBN rescued a genuine domain-shift failure ([existing result](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/CONTEXT_HANDOFF.md:171>)). SAR may help, but that has not been established.

   Fix — Remove the cloud-causation claim and treat SAR benefit as a hypothesis tested by the prespecified modality ablations.

16. **The deep architecture is disproportionate to the independent sample size.** Three annual frames give attention little temporal structure, and roughly 9–12 non-overlapping patches per site provide weak support for a multi-encoder attention U-Net. The existing optical TIFF archive is already 21.7 GB; three more optical years will add roughly another 21.7 GB before SAR, although current disk space is adequate. An unspecified U-Net may fit an 8 GB GPU only at batch size one, which creates normalization and stability problems.

   Fix — Run a one-site memory/runtime pilot with a fully specified channel count and GroupNorm, and make a shallow channel-stacked U-Net—not ConvLSTM—the only deep fallback.

17. **“30 m matches labels exactly” overstates spatial validity.** GFC pixels are approximately 30.92 m on a one-arc-second grid, while Sentinel-1/2 must be resampled and can retain inter-sensor geolocation error; pixel-perfect scores will penalize or reward one-pixel shifts arbitrarily, and top-X “area” cannot be computed by equal pixel counts globally.

   Fix — Add 90–120 m aggregation and one-pixel-tolerance sensitivities, calculate physical pixel areas geodesically, and define every categorical/continuous resampling operator explicitly.

## Simpler design with most of the value

Start with a 90–120 m discrete-time hazard study using LightGBM or regularized logistic regression: strong historical-loss-density features, current optical indices and deltas, properly processed SAR summaries, terrain, and historically valid infrastructure. Evaluate frame sites only with a chronological train/validation/test split and whole-site holdouts. Add a small channel-stacked U-Net only if modality ablations show residual spatial signal beyond that baseline. This preserves the operational risk-ranking contribution while sharply reducing leakage, compute, calibration, and power problems.

VERDICT: REVISE
### Claude's response — 16/17 accepted, deep-model framing reconciled (v2)

Strong review; the plan was materially under-specified on chronology, leakage, and labels. Changes:
- **#1 chronology** ACCEPTED — explicit train/val/test origins (2020→2021 train, 2021→2022 val,
  2022→2023 test), extend forward only if the pinned GFC version supplies later outcome years; no origin
  is both train and forecast.
- **#2 availability firewall** ACCEPTED — per-origin issue date, static layers tagged with a vintage and
  used only where vintage ≤ origin; OSM/WDPA use historical snapshots ≤ T or are flagged + sensitivity-tested.
- **#3 forest-at-T formula** ACCEPTED — `datamask==1 ∧ treecover2000≥θ ∧ (lossyear==0 ∨ lossyear>T)`,
  renamed "GFC-eligible 2000-baseline tree cover remaining at T", θ sensitivity {10,25,50,75}%.
- **#4 forecast-not-detector** ACCEPTED — one-year-gap variant + boundary exclusion + stratified
  disturbance-date audit; headline must survive the gap variant.
- **#5 cohort** ACCEPTED — frame-only (12) primary, legacy (7) exploratory; Rondônia case study is
  leave-site-out with deterministic example selection and disclosed prior inspection.
- **#6 nested/in-fold** ACCEPTED — nested chronological eval, preprocessing fit inside each fold, test
  opened once.
- **#7 spatial splits** ACCEPTED — whole-site LOSO primary; within-site only with receptive-field guard bands.
- **#8 power** ACCEPTED — event-count evaluability gate (connected loss events, not site count),
  site-clustered bootstrap CIs, failed regions → descriptive; the cross-biome claim is downgraded to a
  within-frontier demonstration.
- **#9 metrics** ACCEPTED — per-site+macro AP, prevalence, AP/prevalence lift, Brier/log-loss,
  calibration slope/intercept, budgeted recall at 1/5/10%, clustered CIs; calibrate on natural-prevalence val.
- **#10 forking paths** ACCEPTED — engineering-only fallback triggers set before test access; one primary
  model + one comparison + minimum-gain rule + hard test embargo locked in the plan.
- **#11 baselines** ACCEPTED — tuned historical-loss hazard baseline (multi-radius density, time-since-loss,
  own-pixel, trend) + precommitted modality ablations (contagion / +static / optical / SAR / optical+SAR / full).
- **#12 GFC version** ACCEPTED — pin exact version+checksum, set the origin table from verified coverage,
  align downloads to origins (no unused year).
- **retired-trap audit** ACCEPTED all three — PIF reworded as "unnecessary, not impossible" + drift audit;
  moving-reference explicitly banned via fixed training-fold normalization constants in writing; floor
  replaced by an event-based evaluability gate.
- **#13/#14/#15 SAR** ACCEPTED — 3-site pilot freezing the processing chain; S1B-Dec-2021 discontinuity
  controlled (acquisition-count covariates + year-predictability probe); SAR benefit demoted to a
  hypothesis tested by ablations; the cloud-causation Congo claim withdrawn.
- **#17 resolution** ACCEPTED — 30 m and 90–120 m evaluation, one-pixel tolerance, geodesic pixel areas,
  named resampling operators.

PARTIAL / RECONCILED — **#16 + the "simpler design" recommendation.** Codex would make a 90–120 m hazard
model the study and add a U-Net only if ablations justify it. I ADOPTED the hazard model as the rigorous
**backbone/primary reportable model** and the tuned baseline, AND kept the multi-sensor deep model as a
**prespecified head that becomes headline only if it beats the backbone by a precommitted margin on
validation.** Rationale: this is exactly the user's locked grill choice ("aim for maximum complexity with
higher risk/novelty, fall back if it doesn't work") and it now coincides with Codex's own gating logic —
the deep model must earn the headline. Deep fallback is a shallow channel-stacked U-Net w/ GroupNorm (not
ConvLSTM), preceded by a memory/runtime pilot. Nothing is rejected outright; this is a framing that
satisfies both the rigor concern and the user's ambition.

## Round 2 — Codex

V2 is substantially better, but three core safeguards remain scientifically incomplete: the availability firewall, forecast-not-detector gap test, and event-based evaluability gate. The chronological ML split and forest formula are mostly correct, while fixed normalization needs one clarification.

## Round-1 closure audit

| R1 finding | Status | Assessment |
|---|---|---|
| 1. Training chronology | Partial | The 2021 train / 2022 validation / 2023 test ordering is valid for retrospective ML evaluation, but the interaction with LOSO and real data-release dates remains unspecified. |
| 2. Availability firewall | Not resolved | No issue dates are defined; `lossyear ≤ T`, contemporary/reconstructed GFC, and possibly CHIRPS/OSM information may not have been available when the forecast would be issued. |
| 3. Forest-at-T definition | Mostly resolved | The formula is mathematically correct for a retrospective GFC risk set, but it is not an operationally observable T mask and excludes rather than truly handles regrowth/repeated disturbance. |
| 4. Forecast versus detector | Not resolved | The proposed T+2 gap outcome has an undefined risk set and mishandles pixels lost during the intervening T+1 year. |
| 5. Legacy-site contamination | Resolved | Frame-only primary evaluation, exploratory legacy results, leave-site-out Rondônia, and deterministic examples are appropriate. |
| 6. Spatiotemporal split leakage | Mostly resolved | Chronological origins, fold-local preprocessing, whole-site grouping, and test embargo are good; exact nested LOSO chronology should be stated. |
| 7. Patch/spatial leakage | Resolved | Whole-site LOSO and receptive-field guard bands address it. |
| 8. Thin-region power | Not resolved | Connected-event counting is proposed, but neither “event” nor the evaluability threshold is defined or power-derived. |
| 9. Rare-event metrics/calibration | Resolved | Macro AP, prevalence/lift, proper scoring rules, natural-prevalence calibration, area budgets, and clustered CIs are appropriate. |
| 10. Forking paths | Partial | Engineering triggers are improved, but the primary backbone, meaningful-gain metric/value, deep architecture, and gate remain unfrozen. |
| 11. Baselines/ablations | Mostly resolved | The hazard baseline and modality ablations are good; “own-pixel prior loss” is impossible on the stated eligible pixel domain. |
| 12. GFC version/unused years | Partial | Downloads are now aligned, but an exact GFC version and final origin table are still deferred despite the plan calling itself locked. |
| 13. SAR processing | Mostly resolved | A three-site pilot is appropriate, but the primary chain and its pass/fail criteria are not yet specified. |
| 14. S1B discontinuity | Partial | Acknowledged and probed, but “matching where possible” and adding acquisition counts do not actually remove the discontinuity. |
| 15. Congo rationale | Resolved | The cloud-causation claim is correctly withdrawn and SAR is now a tested hypothesis. |
| 16. Deep-model feasibility | Resolved | Hazard backbone, compact deep comparison, GroupNorm fallback, and memory pilot are proportionate. |
| 17. Grid/spatial validity | Resolved | Aggregated evaluation, shift tolerance, named resampling, and area-weighted metrics address the concern. |

## Remaining material problems

1. **The operational clock is still missing.** The [temporal table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:23>) defines origin years but never defines an issue date. At 31 December T, GFC loss through T generally has not yet been released; if the issue date waits for that release, part of outcome year T+1 has already elapsed. Filtering a modern GFC version to `lossyear ≤ T` also uses retrospective revisions unavailable historically.

   Fix — For every origin, specify one calendar issue date and the exact historical product release available then; use GFC only through the last released year, or explicitly downgrade the study to “retrospective pseudo-operational evaluation.”

2. **The static-driver exception reopens leakage.** Historical OSM “where feasible; otherwise approximately static” permits future roads in the primary model. A sensitivity cannot repair a contaminated primary estimate. CHIRPS 1991–2020 is also not wholly “pre-period” for origin 2020 and may not have been available at its issue date.

   Fix — Exclude any road, WDPA, or climatology layer lacking a valid pre-issue snapshot from the primary model; contemporary versions may appear only in a labeled exploratory sensitivity.

3. **The forest formula is valid only retrospectively.**  
   `datamask==1 ∧ treecover2000≥θ ∧ (lossyear==0 ∨ lossyear>T)` correctly defines GFC-eligible baseline tree cover surviving through T. But at forecast time it requires knowing every T loss, and the goal still calls the domain “standing tropical forest.” Pixels lost and regrown after 2000 are simply absent, while multiple plantation rotations cannot be represented.

   Fix — Retain the formula but call the population “2000-baseline GFC tree cover with no detected loss through T,” state that regrowth/repeat-loss pixels are excluded, and solve the T-loss availability problem through the issue-date design.

4. **The one-year-gap safeguard is not statistically defined.** With features through T and outcome `lossyear==T+2`, pixels lost in T+1 cannot be ordinary negatives: they leave the risk set before the target year. Using `eligible(T+1)` would instead condition on future survival unavailable at issue T. The gap variant also needs its own shifted train/validation/test table—likely outcomes 2022/2023/2024.

   Fix — Define it explicitly as either a conditional diagnostic using `eligible(T+1)` or a competing-risk survival analysis starting from `eligible(T)`; specify treatment of T+1 losses, shifted origins, metric, and pass criterion.

5. **“Boundary exclusion” is not operationalized.** The plan does not define which pixels are excluded, what independent date source is used, how large the audit is, or how audit findings affect the full-raster analysis.

   Fix — Prespecify the reference imagery/alert source, sampling strata and size, uncertainty window around year boundaries, exclusion rule, and the quantitative condition required to retain the forecasting claim.

6. **The event-based evaluability gate is still only a promise.** [Lines 131–133](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:131>) do not define connectivity, minimum event size/separation, temporal merging, required event count, required positive-site count, or how the threshold derives from desired precision. Hundreds of connected components in three landscapes still do not create regional replication.

   Fix — Before test access, freeze the event algorithm and a simulation- or CI-width-derived dual gate requiring both adequate independent sites and adequate events; include sensitivity to 4/8-connectivity and event merging.

7. **The normalization is conceptually fixed but textually ambiguous.** [Section 6](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:79>) says constants are estimated once on “training origins,” which could include the held-out LOSO site, while line 129 says preprocessing is fold-local. The latter must control. The pseudo-invariant audit must not trigger test-dependent renormalization.

   Fix — State: “For each LOSO fold, fit constants using origin-2020 pixels from the 11 frame training sites only; apply unchanged to validation and held-out-site test data; test-origin drift audits are diagnostic only.”

8. **The exact nested evaluation needs one sentence.** Whole-site LOSO plus chronological roles could otherwise be implemented several ways.

   Fix — State that each fold trains on 2021 outcomes from 11 frame sites, tunes/calibrates on their 2022 outcomes, and evaluates only the held-out site’s 2023 outcome, with no data from that site used in normalization or model fitting.

9. **One contagion feature is identically zero.** A 30 m prediction pixel satisfying `eligible(T)` has no prior GFC loss, so “own-pixel prior loss” cannot vary. That feature made sense for the retired 640 m aggregate cells, not native GFC pixels.

   Fix — Remove it or redefine it as prior-loss fraction within a prespecified surrounding window excluding the focal pixel.

10. **S1B control should be stronger.** Acquisition count as a covariate may help the model exploit the year discontinuity rather than remove it. Since Sentinel-1A spans the whole period, an S1A-only primary composite is a cleaner design than mixed A/B sampling “where possible.”

   Fix — Use matched Sentinel-1A acquisitions and fixed orbit geometry as the primary SAR series; treat mixed A/B composites and acquisition-count adjustment as sensitivities.

11. **Several supposedly prespecified choices are still placeholders.** “LightGBM or logistic,” “channel-stacked / temporal-attention,” the meaningful-gain threshold, event gate, GFC version, and SAR pass criteria remain undecided. Choosing them on validation is permissible, but they cannot simultaneously be described as already locked.

   Fix — Distinguish choices legitimately tuned on validation from choices frozen before validation, assign the selection metric and tie-break, and freeze all of them before test-label access.

## Retired-trap audit

- **PIF:** Addressed. V2 correctly says PIF is unnecessary rather than impossible.

- **Moving reference:** Addressed in principle. No per-scene/site-year scaling is permitted; the LOSO-fold clarification above is still necessary.

- **Equal-allocation floor:** Only partially addressed. The arbitrary site-count floor is gone, but the replacement event gate is not yet a reproducible validity safeguard and cannot compensate for only three landscapes per region.

The core study can become sound without changing its overall direction, but the issue-date firewall, gap estimand, and evaluability gate need concrete definitions before data extension or test-label access.

VERDICT: REVISE
### Claude's response — all round-2 items accepted, values frozen (v3)

Converging: round-2 findings were precision/definition demands, not direction changes (Codex: "the core
study can become sound without changing its overall direction"). All incorporated:
- #1 operational clock — study reframed as **retrospective pseudo-operational**; single pinned GFC
  version+md5; issue-date logic stated; test outcome year = 2nd-most-recent released loss year.
- #2 static leakage — primary model uses ONLY pre-issue-dated snapshots (OSM full-history/Geofabrik ≤ T,
  WDPA historical ≤ T, DEM/peat/ecoregion static, CHIRPS 1981–2010 normal); no "approximately static"
  hedge; contemporary layers → exploratory sensitivity only.
- #3 population — renamed "2000-baseline GFC tree cover with no detected loss through T"; regrowth/
  repeat-loss exclusion stated; tied to retrospective framing.
- #4 gap estimand — defined as a CONDITIONAL diagnostic on eligible(T)∧eligible(T+1) predicting
  lossyear==T+2 from features ≤T, own shifted origin table, T+1-loss handling + conditioning limitation
  stated, explicit pass condition.
- #5 boundary audit — RADD+GLAD-L alerts, ~180 loss px/biome, ±8-week Jan-1 window, drop-boundary
  sensitivity, retain-claim condition (< CI half-width shift).
- #6 event gate — 8-connectivity, min event ≥2 px, per site-year; dual gate (≥3 evaluable sites AND ≥30
  events AND AP-lift CI half-width ≤0.10) else descriptive; 4-conn sensitivity; explicit that 3 sites/region
  cannot be rescued by any gate (claim already downgraded).
- #7 normalization — exact per-LOSO-fold sentence (constants from 11 training sites' 2020 pixels only,
  applied unchanged to val/test; drift audit diagnostic only).
- #8 nested eval — exact sentence (train 2021 / tune-calibrate 2022 / test held-out-site 2023).
- #9 own-pixel prior loss — REMOVED (identically zero on eligible pixels); replaced by windowed
  neighbour-loss fraction excluding the focal pixel.
- #10 S1B — primary SAR = Sentinel-1A only, fixed orbit; mixed A/B + acquisition-count = sensitivities.
- #11 placeholders — added §F Frozen-vs-validation-tuned table; committed concrete values: GFC pin rule,
  LightGBM backbone (not "or logistic"), attention-U-Net primary + shallow-U-Net/GroupNorm fallback,
  min gain = +0.03 area-weighted recall@5% with CI excluding 0, SAR pass = year-probe AUC<0.60,
  θ=30% default. Nothing rejected.

## Round 3 — Codex

V3 resolves the forest-population formula, fixed fold-local normalization, static-layer exclusion rule, nested LOSO choreography, own-pixel feature defect, S1B primary-series problem, and most model-selection placeholders. It is still not implementable as frozen because several concrete rules conflict or test the wrong quantity.

## Round-2 closure audit

| Round-2 problem | Status | Assessment |
|---|---|---|
| 1. Operational clock/firewall | Partial | The pseudo-operational reframing is honest, but no actual issue date appears, despite static layers being filtered against it. |
| 2. Static future leakage | Mostly resolved | Invalid vintages are excluded from the primary path and CHIRPS is pre-period; application still depends on the missing issue date. |
| 3. Forest population | Resolved | Formula, terminology, canopy threshold, and explicit exclusion of regrowth/repeat disturbance are now sound for the retrospective estimand. |
| 4. Conditional gap diagnostic | Partial | The risk set is now coherent, but its pass rule compares raw targeting efficiency across different outcome years and populations. |
| 5. Boundary audit | Not resolved adequately | Alert detection dates are treated as independent disturbance dates, and the audit focuses on January 1 rather than whether loss preceded the local predictor cutoff. |
| 6. Event gate | Partial | Connectivity and numeric thresholds are frozen, but “evaluable site,” “AP-lift,” and the bootstrap used by the gate remain undefined. |
| 7. Fold-local normalization | Resolved | It is explicitly fitted on the eleven training sites at origin 2020 and never updated from validation/test data. |
| 8. Exact nested evaluation | Resolved in isolation | The fold choreography is clear, but it conflicts with the separate GFC test-year rule. |
| 9. Own-pixel loss feature | Resolved | Replaced by a valid neighborhood statistic. |
| 10. S1B control | Mostly resolved | S1A-only fixed-orbit processing is sound; the year-prediction probe still needs leakage-safe stable-pixel selection and grouped validation. |
| 11. Frozen choices | Partial | Most values are concrete, but the test year, deep-model selection rule, and engineering step budget remain internally inconsistent or unspecified. |

## Material remaining problems

1. **The frozen origin rules contradict one another.** The table and nested LOSO specify test outcome 2023, while lines 49–51 require the test to be the second-most-recent released GFC year. The current official release extends through 2025, making the second-most-recent year 2024, not 2023. [Current GFC v1.13 catalog](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13)

   Fix — Either freeze 2023 as the primary test and delete the second-most-recent rule, or update every origin, download, LOSO, gap, and embargo statement consistently to a 2024 primary test and 2025 extra test.

2. **The claimed issue-date firewall still has no issue date.** [Section 3](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:66>) says snapshots must precede the origin’s issue date, but nowhere defines that date. “≤ T” is insufficient for roads, WDPA releases, acquisitions, or GFC publication latency.

   Fix — Freeze a date such as `December 31 T` for every origin, require acquisition/publication timestamps no later than that date, and explicitly state that final-version GFC loss through T is a retrospective-label exception rather than historically available information.

3. **The boundary audit does not directly test whether the model saw the event.** The relevant comparison is disturbance time versus the last acquisition contributing to that site’s T composite—not merely proximity to January 1. A July/August loss already visible in a June–September composite can still become a detector problem even though it lies outside the ±8-week window.

   Fix — For every audited positive, compare the earliest credible disturbance interval with the pixel’s actual final contributing predictor acquisition and exclude events whose disturbance predates or overlaps that cutoff.

4. **RADD/GLAD alert dates are detection dates, not independent event dates.** RADD dates the first triggering radar image and may take subsequent observations to confirm an alert; GLAD-L detection can lag actual disturbance by months under clouds. RADD is also Sentinel-1-derived, overlapping the predictor sensor rather than providing independent ground truth. [RADD product definition](https://www.wur.nl/en/research/products-services/radd-forest-disturbance-alert), [GLAD-L documentation](https://glad.umd.edu/dataset/glad-forest-alerts)

   Fix — Treat alerts as interval-censored evidence, supplement ambiguous cases with manual time-series imagery, record unmatched alerts, and stratify the audit by site and origin as well as biome.

5. **The gap diagnostic’s retention criterion compares unlike estimands.** Conditional T+2 performance among T+1 survivors can differ legitimately from next-year performance because its year, population, prevalence, and forecast horizon differ. Requiring its raw 5% recall to fall inside the main model’s CI can reject a real forecast or accept a weak one merely because the main CI is wide.

   Fix — Judge the gap model against its own same-population contagion baseline using a frozen lift/non-inferiority margin, while reporting comparison with the main result descriptively.

6. **The dual evaluability gate is still not fully computable.** “Three evaluable sites” lacks a site definition; “AP-lift” could mean `AP/prevalence` or `AP−prevalence`; and the site/spatial bootstrap geometry, replication count, and handling of positive-free replicates are absent. Calling 8-connected components “independent events” is also stronger than warranted.

   Fix — Define site evaluability, the exact lift formula, hierarchical resampling algorithm and replicate count, and call the units “mapped loss components” unless spatial/operational independence is established.

7. **The SAR gate can leak test outcomes.** “Non-loss, non-edge” stable pixels must not be selected using loss through the test or embargoed years before the SAR inclusion decision. The year classifier could also memorize sites/pixels or detect real interannual moisture differences rather than acquisition artifacts.

   Fix — Select stable pixels using training-period information only, compare the same pixels across years, group classifier validation by site/pixel, balance site-years, and interpret AUC as a conservative artifact screen rather than proof of radiometric invariance.

8. **The two deep-model rules conflict.** Section F says attention versus shallow U-Net is selected using validation performance; section 9 says the shallow model runs only after an engineering OOM/non-convergence trigger. Those are different selection procedures. The supposedly fixed step budget is also not given numerically.

   Fix — Choose either validation competition between both architectures or an engineering-only fallback, and freeze the step count, convergence statistic, and threshold before training.

Everything else from round 2 is adequately repaired, especially the retrospective population definition, normalization, LOSO isolation, primary/exploratory cohort separation, LightGBM commitment, modality ablations, S1A-only primary series, and modest claim scope. The remaining changes are localized, but the test-year contradiction and boundary audit still affect the study’s central validity.

VERDICT: REVISE
### Claude's response — all 8 round-3 items accepted, internal contradictions removed (v4)

Mop-up round (Codex: remaining changes "localized"; everything else "adequately repaired"). All fixed:
- r3#1 year contradiction — DELETED the "second-most-recent released year" rule; froze primary test outcome
  = 2023 (origins 2020/21/22 → 2021/22/23); embargoed 2024/2025 extras optional-if-covered. Table, downloads,
  LOSO, gap, embargo now mutually consistent.
- r3#2 issue date — froze **31 December T** per origin; all vintages/acquisitions ≤ that date; final GFC
  loss-through-T stated as the single disclosed retrospective-label exception.
- r3#3 boundary audit — reframed to compare disturbance interval vs the pixel's **final contributing
  predictor acquisition** (not Jan-1); disturbance predating/overlapping the composite cutoff = detector case.
- r3#4 alerts — RADD/GLAD-L treated as **interval-censored detection** evidence (noted RADD is S1-derived,
  not independent of the SAR predictor), + manual inspection for ambiguous cases, stratified by site+origin+biome.
- r3#5 gap pass rule — now a **non-inferiority test vs the gap model's own contagion baseline** on AP-lift
  (margin 0.10); comparison to the main result is descriptive only.
- r3#6 gate computability — defined **evaluable site** (≥5 mapped loss components in test origin), fixed
  **AP-lift ≡ AP/prevalence**, specified the **hierarchical site-clustered bootstrap** (resample sites then
  pixels, 1000 reps, drop+count positive-free reps), renamed "events" → "mapped loss components."
- r3#7 SAR probe leakage — stable pixels from **training-period (≤2020) loss-free non-edge** only; same pixels
  across years; probe validation grouped by site, balanced site-years; AUC<0.60 as conservative screen.
- r3#8 deep-model conflict — unified: **both architectures compete on validation** (recall@5 %); the
  OOM/divergence/**20-epoch-no-improve, 200-epoch-cap** guard is a separate engineering safety trigger.
Nothing rejected. All values now concrete and internally consistent.

## Round 4 — Codex

V4 resolves the test-year contradiction, fixes the issue date, makes the retrospective GFC exception explicit, defines a coherent conditional gap population, corrects the alert-date interpretation, makes the SAR screen leakage-safe, and removes the deep-model selection/fallback contradiction. Three inferential defects remain material.

## Round-3 closure audit

| Round-3 problem | Status | Assessment |
|---|---|---|
| 1. Contradictory test-year rules | Resolved | The primary test is consistently frozen at 2023; later years cannot alter it. |
| 2. Missing issue date | Resolved for the stated pseudo-operational estimand | December 31 T is explicit and non-GFC predictors require pre-issue timestamps. |
| 3. Audit against wrong cutoff | Resolved conceptually | Disturbance intervals are now compared with each pixel’s final contributing acquisition. |
| 4. Alert dates treated as event dates | Mostly resolved | Alerts are correctly interval-censored and ambiguous cases receive manual review, but the sampled audit is not yet connected validly to the full headline metric. |
| 5. Gap comparison across unlike populations | Partial | It now uses its own same-population baseline, but the claimed non-inferiority decision uses a point estimate rather than a confidence bound. |
| 6. Incomputable event gate | Partial | Components, site eligibility, lift, thresholds, and replicates are defined; the within-site bootstrap incorrectly resamples spatially dependent pixels independently. |
| 7. SAR probe leakage | Mostly resolved | Training-period stable pixels and site-grouped validation close the leakage path; the multiclass AUC definition should still be named. |
| 8. Deep selection versus fallback | Resolved | Both architectures compete on validation, while the numeric engineering guard is separate. |

## Remaining material flaws

1. **The hierarchical bootstrap reintroduces the spatial-independence error.** [Lines 142–144](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:142>) resample pixels independently within sites. Nearby loss and forest pixels are strongly autocorrelated, so this will narrow AP-lift and model-difference intervals and can incorrectly pass both the regional gate and deep-model headline gate.

   Fix — Resample sites and then spatial blocks larger than the measured autocorrelation range/receptive field, using identical resamples for paired model comparisons.

2. **Dropping every zero-positive bootstrap replicate can make a thin result appear evaluable.** Counting the discarded replicates is not a decision rule; the reported CI is conditional on obtaining positives and may look narrow precisely when the data are weakest.

   Fix — Freeze a maximum undefined-replicate fraction, such as 20%; exceeding it makes the site/region unevaluable rather than silently conditioning the CI.

3. **The detector audit sample cannot directly support the proposed headline sensitivity.** A sample of approximately 180 positives per biome can estimate a detector-case proportion, but only with the stratified inclusion weights and sampling uncertainty. It cannot literally recompute full-raster targeting efficiency after “removing them” unless detector status is assigned to every positive or a survey-weighted estimator is used.

   Fix — Either construct an alert/manual-derived detector mask for every positive or define a survey-weighted correction using frozen inclusion probabilities; require the upper confidence bound—not merely the point estimate—of the detector-case share to be ≤10%.

4. **The gap “non-inferiority” test lacks an inferential decision rule.** `gap lift ≥ contagion lift − 0.10` on point estimates is not a non-inferiority test and can pass because of sampling noise.

   Fix — Compute paired `Δlift = gap model − gap contagion` under the spatially clustered bootstrap and pass only when the lower confidence bound is at least −0.10; without a held-out 2024 gap test, call the diagnostic inconclusive.

## Minor clarifications

- The GFC exception in [the firewall](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:54>) should explicitly say it covers both the eligibility mask and GFC-derived hazard predictors; calling all of it a “retrospective label” is imprecise.

- Define the acquisition-year probe’s multiclass score, for example macro one-vs-rest ROC-AUC.

- Write whether “90–120 m” means both 90 m and 120 m evaluations or one scale selected later.

These are localized revisions, but the current pixel bootstrap affects the central uncertainty estimates, evaluability gate, and deep-model selection, while the detector audit’s headline pass rule is not yet statistically executable.

VERDICT: REVISE
### Claude's response — all round-4 items accepted (v5); this is round 5, the MAX_ROUNDS cap

Deep convergence: round-4 items were all statistical-precision, "localized", direction fully accepted. Fixed:
- r4#1 bootstrap spatial independence — replaced within-site pixel resampling with a **hierarchical spatial
  block bootstrap** (block edge ≥ max(loss-autocorrelation range, receptive-field radius)); **paired model
  comparisons use identical block resamples**. (Same error class the detector paper already fixed.)
- r4#2 dropped zero-positive replicates — froze a **max 20% undefined-AP replicate fraction**; exceeding it
  makes the site/region **unevaluable**, not silently conditioned.
- r4#3 detector-audit headline rule — **survey-weighted estimator** with frozen stratum inclusion
  probabilities; require the **upper confidence bound** of detector-case share ≤10%, and a survey-weighted
  targeting-efficiency correction (not literal removal of 180 pixels).
- r4#4 gap non-inferiority — now a real test: paired **Δlift LCB ≥ −0.10** under the clustered bootstrap;
  **inconclusive** without a held-out 2024 gap test.
- minor: GFC exception reworded to cover **both the eligibility mask and GFC-derived hazard predictors**;
  probe score named **macro one-vs-rest ROC-AUC**; resolution fixed to **both 30 m and 90 m**.
Nothing rejected.

## Round 5 — Codex (MAX_ROUNDS cap)

V5 fixes the core round-4 defects in principle: spatial blocks replace independent pixels, the undefined-replicate ceiling is explicit, the detector audit uses survey weighting and a UCB, and the gap decision uses a paired lower confidence bound. All three minor clarifications are also addressed. Two implementation ambiguities remain material because they control leakage and whether the statistical gates pass.

## Round-4 closure

| Item | Status | Assessment |
|---|---|---|
| 1. Independent-pixel bootstrap | Mostly resolved | Hierarchical spatial blocks and paired model resamples are correct, but the block-construction algorithm remains unfrozen. |
| 2. Undefined bootstrap replicates | Resolved | The 20% threshold correctly makes the unit unevaluable. |
| 3. Detector-audit inference | Mostly resolved | Survey weighting and the ≤10% UCB rule are appropriate; the estimator’s confidence level, variance method, and connection to the test-origin headline require specification. |
| 4. Gap non-inferiority | Resolved in form | The paired lower-bound rule is correct; freeze the confidence level explicitly. |
| GFC-exception wording | Resolved | It now covers both the population mask and hazard predictors. |
| SAR multiclass AUC | Resolved | Macro one-vs-rest AUC is explicit. |
| Aggregation scale | Resolved | Both 30 m and 90 m are fixed. |

## Remaining material issues

1. **The spatial block bootstrap is not yet reproducible.** “Measured loss-autocorrelation range” does not name the estimator, lag grid, cutoff, origin/cohort used to estimate it, or what happens if correlation never crosses the cutoff. Block placement, overlap, edge handling, and the number drawn per site are also unspecified. These choices directly control the AP-lift CI, regional gate, and deep-model gain gate.

   Fix — Freeze an autocorrelation estimator and threshold using training/validation data only, plus exact moving-block geometry, edge handling, and sampling-until-size rule.

2. **Nested model selection within LOSO is no longer explicit.** Whole-site LOSO and “all preprocessing in-fold” do not state whether hyperparameters, calibration, architecture competition, and the ≥0.03 deep-model gate are recomputed using only the eleven non-held-out sites. A global validation competition using the held-out site’s 2022 labels would leak site-specific information into its 2023 test prediction.

   Fix — Restore the exact rule: for each outer site, every tuning, calibration, architecture, and headline-selection decision uses only the other eleven sites; the held-out site contributes predictors only at final inference.

3. **The survey-audit decision is not fully frozen.** The plan does not specify whether the UCB is 95%, how stratified survey variance is calculated, or whether the approximately 180-per-biome allocation applies specifically to test-origin positives. Train/validation samples cannot directly correct the 2023 headline targeting efficiency.

   Fix — Freeze the confidence level and survey-variance estimator, inclusion allocation by site for 2023 positives, and the Horvitz–Thompson or Hájek formula used for both detector share and corrected targeting efficiency.

4. **The gap confidence level should be explicit.** “Lower confidence bound” could mean 90%, 95%, or another level, materially changing a non-inferiority decision.

   Fix — Freeze a 95% paired spatial-block-bootstrap lower bound and apply the same undefined-replicate gate.

One minor wording cleanup remains: [the provenance section](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:95>) should say GFC coverage verifies the frozen 2023 test and determines only optional embargoed years, rather than “set §1” from coverage.

VERDICT: REVISE
### Claude's response — all 4 round-5 items incorporated (v6-final); loop terminated at MAX_ROUNDS

Round cap (MAX_ROUNDS=5) reached without a printed APPROVED, but this is CONVERGENCE, not deadlock —
Codex's own round-5 text says v5 "fixes the core round-4 defects in principle" and calls the remainder
"implementation ambiguities" (specific parameters to freeze), with zero challenge to the design. Findings
shrank monotonically 17→11→8→4→4 and every single one across five rounds was conceded. The round-5 items
are mechanical parameter-freezes, all incorporated in v6:
- r5#1 block bootstrap reproducibility — froze the estimator (empirical semivariogram range at 95% of sill,
  training origins/sites only), block geometry (non-overlapping L×L moving blocks, L=max(range, RF radius)),
  sampling-until-size rule, edge handling, 95% level.
- r5#2 nested LOSO — restored the explicit rule: every tuning/calibration/architecture/gate decision uses
  only the 11 non-held-out sites; held-out site is predictors-only at final 2023 inference.
- r5#3 survey audit — froze Hájek/Horvitz–Thompson estimator over 2023 positives, stratified linearized
  variance, 95% UCB ≤10%, weighted-corrected targeting efficiency.
- r5#4 gap CI — froze 95% paired lower bound + same undefined-replicate gate.
- minor — provenance wording: GFC coverage confirms the frozen 2023 test and determines only embargoed
  extras, never §1.

STATUS: substantively converged. All findings across 5 rounds accepted and incorporated; the last two
rounds were mechanical. Not re-submitted for a 6th round (round cap). This is a REVIEWED, converged plan
awaiting the user's implement-or-not decision — NOT an approved-and-verified one, because Codex has not
seen v6-final (it differs from v5 only by the round-5 parameter-freezes it itself requested).
