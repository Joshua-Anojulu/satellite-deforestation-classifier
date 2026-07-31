# Frontier Stratification — Review Log

**Task.** Stratify Specification W's Phase E step-40 metrics by prior-loss distance into
INFILL / EDGE / FRONTIER, so that the project's two differentiators — 36 dated OSM extracts rather than a
static snapshot, and the 30 m grid rather than 400 m — become measurable. Both are frontier-specific by
construction and invisible under aggregate-only reporting.

**Plan file.** `FRONTIER-STRATIFICATION-PLAN.md`
**Supersedes.** `FRONTIER-STRATIFICATION-PROPOSAL.md` (2026-07-31, not adopted)
**Amends.** `ANALYSIS-DRIVER-PLAN.md` (`approved-final`, body `030d78fa`)
**Motivating evidence.** Forest Foresight (WWF-NL), *Environ. Res. Commun.* 2026,
doi:10.1088/2515-7620/ae1f69 — 94 % of new loss is infill; detection 82 % near recent loss vs 7.4 % in
untouched forest; static OSM snapshots named as a limitation.

## Resolved caps

| Var | Value |
|---|---|
| `MAX_ROUNDS` | 5 |
| `MAX_ATTEMPTS` | 8 |
| `PLAN_FILE` | `FRONTIER-STRATIFICATION-PLAN.md` |
| `LOG_FILE` | `FRONTIER-STRATIFICATION-REVIEW-LOG.md` |
| reviewer | resolved at Act 2 |

## Act 1 — Grill (Claude ↔ Josh)

### Measured from the codebase before any question was asked

- **The proposal's two named constraints are structurally satisfied**, because it reuses
  `loss_support_θ,T` verbatim rather than rebuilding it. Raw `loss_code` is inherited from C1.15; and the
  identically-zero-numerator bug required a *density* over `eligible()`, whereas `d_prior` is a distance
  with no denominator, so that class cannot arise.
- **`risk/census/control_census2.py:73` and `annulus_granule_check.py:86` already compute prior-loss
  distance transforms with GEODESIC sampling** — `geod.inv` at the site centre latitude, thresholded in
  metres (`dist_loss >= 1920.0`). So the repo has a metric convention, which contradicted Claude's initial
  "use pixels" instinct and had to be reconciled rather than ignored.
- **GFC pixels are ~27.8 m in y and ~27.8·cos(lat) in x, never larger**, so 1500 m maps to ≥ 54 px at every
  site. The degeneracy result below therefore survives either unit choice — established before choosing.
- **Plan steps 17 and 35 restrict θ ∈ {10,25,50,75} to `full_without_sar` at 30 m, one candidate.** So the
  four sensitivity θ values have **no 90 m scale and no contagion / contagion+static arms**.

### The finding that reshaped the plan

`FRONTIER` is defined as beyond every contagion radius, so at such a pixel **every** contagion feature is
degenerate by construction: all `loss_density_r`, `recent_loss_density_r` and `nbr_loss_frac_w` are exactly
0 (empty numerators), `dist_nearest_loss` is censored, `nearest_loss_age` is NaN,
`loss_absent_within_rmax` is 1, and `loss_trend` is 0. The contagion feature vector is **constant** across
the stratum, so the contagion arm cannot rank within it at all.

**Therefore the proposal's primary — `FRONTIER` AP-lift of `contagion+static` over `contagion` — is
identically AP-lift over the prevalence null.** Not approximately; by construction. It would have produced
an impressive number for a mechanical reason, under a comparative label it does not earn.

### Decisions locked

| # | Decision |
|---|---|
| 1 | **Primary = absolute `FRONTIER` AP of `contagion+static` vs the within-stratum prevalence null**, at θ=30 / 30 m / macro-region. Lift over contagion still emitted, annotated as equal to lift over the null by construction. |
| 2 | **Boundaries in pixels** (5 px, 50 px), so the cut coincides exactly with contagion's support; geodesic metre equivalents emitted per site as metadata using the `risk/census/` convention. |
| 3 | **Merge into `ANALYSIS-DRIVER-PLAN.md` after approval and re-run its full chain.** Editing the body breaks the `030d78fa` binding, and that is accepted openly rather than worked around. `ANALYSIS-DRIVER-PLAN.md` is not edited before then. |
| 4 | **Scope = everything that exists**: θ=30 gets all four arms, both scales, the full metric set; θ ∈ {10,25,50,75} get stratified AP and budget recall for `full_without_sar` at 30 m only, since the primary is not computable there. |
| 5 | **Hard gate on the primary**: suppressed below 100 pooled macro-region `FRONTIER` positives; per-site cells flagged below 25. Frozen blind, and labelled a judgement call like `B₀ = 50 000`. |

### Claude's review findings folded into the plan

1. `d_prior_px` must be a **separate uncensored transform** — `dist_nearest_loss` is censored at `R_max = 50`
   px, exactly the `FRONTIER` boundary, so reuse yields an all-NaN stratum.
2. Exact distance beyond 51 px is **not computable** within the frozen halo; membership *is* decidable.
   The stratifier is therefore a 3-way bucket and never a continuous quantity.
3. **90 m blocks take the minimum** over their 9 native pixels, matching the block-positive union rule.
4. Exporting the stratum label requires amending the **C1.15 allow-list** and the **Phase 0.8 predictor
   transcript projection** — it will pass the noninterference tests, but must be added explicitly.
5. Bootstrap membership is **fixed before resampling**; nothing is re-stratified inside the loop.
6. Per-stratum prevalence is itself a result — it **measures** the imported 94 % premise instead of
   assuming it.

## Round 1 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (PINNED; PATH codex is 0.146.0, outside `verified_versions`) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a
- reviewed body_sha256: e59027fdbbf5e13edc07cf70e67c35f29861001051d2f0a51496676b669b1016
- verdict: REVISE (4 critical, 10 high, 2 medium)

**The central claim of v1 was refuted, and I verified the refutation against the repo rather than taking
it.** v1 asserted that on `FRONTIER` the contagion feature vector is constant by construction, so its
AP-lift is identically lift over the prevalence null. It is wrong three ways:

1. **C1.15 makes densities focal-excluded with "zero denominator → `NaN` plus an `*_undefined` flag."** An
   isolated eligible pixel reads `NaN / undefined=1` where its neighbours read `0 / undefined=0`, varying by
   radius; at 90 m, `valid_count` and `any_missing` vary too. A model can rank on that missingness pattern.
   I had written the caveat "up to `*_undefined` flags" into v1 and then built the headline on constancy
   anyway — the hedge *was* the refutation and I wrote past it.
2. **Per-site LOSO models and fold-specific calibrators** put site scores on different scales, so pooled
   macro-region `FRONTIER` scores rank across sites regardless of within-site constancy — and the primary
   was defined at macro-region.
3. **`FORECAST-PLAN.md:228` freezes `AP-lift ≡ AP / prevalence`** — already null-relative. v1 called the
   proposal's use of the term misleading when the proposal was using it exactly as the schema defines it,
   then "corrected" the primary to something the schema's own notation already meant.

The two standing repo bug classes were confirmed correctly avoided: support in raw `loss_code`, distance
sourced from `loss_support_θ,T` and not `eligible_θ(T)`.

### Critique (verbatim)

## Findings

1. **Critical: the contagion vector is not constant on `FRONTIER`.** C1.15 excludes the focal pixel from density denominators, so isolated eligible pixels produce `NaN + undefined=1`, while others produce `0 + undefined=0`; at 90 m, `valid_count`, `any_missing`, and all-nine-undefined status also vary. [Central claim](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:35>) [C1.15](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:179>)  
   **Fix:** Retract the construction-level constancy claim and compare against actual contagion predictions while reporting all undefined/missingness-pattern frequencies.

2. **Critical: even a constant per-site vector does not imply constant macro-region scores.** Each held-out site is scored by a different LOSO model and fold-specific calibrator, so pooled `FRONTIER` contagion scores can differ by site and rank pixels between sites. [Primary level](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:112>) [LOSO contract](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:336>)  
   **Fix:** Define the macro-region aggregation explicitly and compute contagion and null metrics independently on identical rows and bootstrap resamples.

3. **High: “AP-lift over contagion” conflicts with the governing schema.** §10 freezes `AP-lift = AP / prevalence`; it is not a pairwise model contrast. [Governing definition](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:228>)  
   **Fix:** Reserve `AP-lift` for `AP/prevalence` and name arm comparisons `ΔAP` or `AP ratio`.

4. **High: “absolute AP against the prevalence null” is not a defined comparison.** An AP interval alone is not an interval for improvement over prevalence, and 100 positives does not guarantee any negatives or rank-identifiability.  
   **Fix:** Require both classes and freeze a replicate-wise paired contrast such as `AP − prevalence` or `AP/prevalence`, including one-class and undefined-replicate branches.

5. **High: several promised stratified metrics become undefined or arbitrary.** Calibration slope/intercept are unidentified for constant scores or one-class strata, while budget recall under tied scores depends on raster/row order. [Full metric promise](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:120>)  
   **Fix:** Predeclare metric-specific statuses, suppress unidentified calibration coefficients, and use randomized expected tie handling or label constant-score budget metrics uninformative.

6. **High: bucket-only computation contradicts the promised distance deciles.** A 51-pixel halo decides `>50` but cannot recover exact frontier distances, yet the plan promises per-site `d_prior_px` deciles. [Bucket restriction](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:77>) [Decile promise](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:104>)  
   **Fix:** Remove the deciles or fund a full-distance computation with sufficient spatial support and an explicitly authorized continuous artifact.

7. **High: boundary equality remains underdefined.** “Censored at 50” could mean `>=50`, while `FRONTIER` requires strictly `>50`; exact axial and Pythagorean distances of 5 or 50 can therefore disagree with `loss_absent_within_rmax`.  
   **Fix:** Freeze center-to-center Euclidean closed discs (`d <= r`), define absence iff `d > 50`, and test exact 5/50 boundaries plus prior loss outside the core but inside the halo.

8. **Medium: the halo width itself is sufficient, but the plan overstates what it proves.** Exact edge assignment additionally requires the raw mosaic to extend 51 pixels beyond the site, transform before cropping, and distinguish empty support from SciPy’s finite-array EDT boundary behavior.  
   **Fix:** Bind expansion, seam coverage, empty-support handling, transform-before-crop, and core crop indices into the artifact contract and edge tests.

9. **High: the metre rationale reverses physical comparability.** Fixed pixel cuts align with contagion’s grid support, but physical distance varies by latitude and direction; `risk/census/` emits separate x/y geodesic sizes and uses anisotropic EDT sampling, not one scalar “per-pixel ground size.” [Unit rationale](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:90>) [Existing convention](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/census/annulus_granule_check.py:84>)  
   **Fix:** Describe these as feature-support strata, emit both x- and y-axis metre spans, and withdraw the claim of physical-distance comparability.

10. **High: the 90 m minimum is defensible for preserving `FRONTIER = all nine pixels beyond 50`, not because future positivity also uses a union.** Predictor exposure and outcome aggregation need not share an operator, and the current explanation hides the missingness behavior that breaks constancy. [90 m rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:99>)  
    **Fix:** Justify minimum by the all-native-pixels frontier invariant and specify categorical, eligibility, undefined, `valid_count`, and `any_missing` aggregation together in C2.18.

11. **Critical: the firewall amendment is insufficient.** The current supervisor validates exact names, boolean dtype, shape, and formulas; a three-valued, origin-specific stratum needs a new schema, while predictor projection inclusion does not prevent the model loader from consuming it as a feature. [Firewall proposal](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:149>) [Current validation](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:133>)  
    **Fix:** Define an exact `(θ, site, T)` categorical artifact schema and report-only namespace, then enforce a model-input allow-list that rejects the stratum column.

12. **High: the noninterference projection must be origin-scoped.** A combined transcript containing strata for several origins cannot remain byte-identical when a code is future for one origin but valid prior history for another.  
    **Fix:** Compare separate per-origin predictor projections under erasure, relocation, and recoding strictly after that artifact’s `T`.

13. **High: the LOSO language is wrong and dangerous.** `d_prior_px` must use the held-out site’s pre-origin loss history as a predictor; “never from the held-out site’s outcomes” can be implemented as excluding that history and making the site spuriously frontier-heavy. [Leakage wording](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:144>)  
    **Fix:** State that held-out pre-origin history is required, while only `T+1` labels and fitted state from the held-out site are forbidden.

14. **High: 100 pooled positives does not validate the hierarchical bootstrap.** One hundred positives concentrated in one site or tile can yield more than 20% zero-positive replicates, and the per-site `<25` flag is ambiguous about whether those sites remain pooled. [Hard gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:166>) [Bootstrap failure rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:286>)  
    **Fix:** Add positive-supporting site/tile diagnostics and the existing undefined-replicate gate, while making `<25` presentation-only and retaining those sites in pooled resampling.

15. **High: the stated scientific goal is not identified by this design.** `contagion+static` bundles every static driver, so it cannot attribute frontier performance to dated OSM; likewise 30 m versus 90 m does not measure 30 m versus 400 m and changes the outcome estimand. [Goal](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:18>)  
    **Fix:** Narrow the claim to stratified static-feature predictive utility, or add frozen road-vintage and resolution ablations.

16. **High: the adoption path is circular and materially undercounts edits.** The plan says the driver is not edited until the merged body is approved, although approval requires reviewing that merged body, and “exactly four places” omits C2.18, table schema, proof, audit outputs, risks, and metric terminology. [Adoption path](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:172>)  
    **Fix:** Build a separate merged candidate marked in-progress, enumerate every affected section, approve its exact body hash, then atomically adopt it as the new driver.

The two recurring Hansen bug classes are correctly avoided: support uses raw `loss_code`, and the distance source is `loss_support_θ,T`, not `eligible_θ(T)`. No files were modified.

VERDICT: REVISE
### Claude's response (round 1)

All 16 accepted. Josh chose to **narrow the claim** on #15 rather than add ablations.

| # | Fix in v2 |
|---|---|
| 1 | Constancy claim **retracted**; §3.4 now *measures* degeneracy — `*_undefined` pattern frequencies, distinct score counts, within-stratum variance |
| 2 | Macro-region defined as unweighted mean of per-site AP with contributing-site list; both arms on identical rows and replicates |
| 3 | `AP-lift` reserved to `AP/prevalence`; arm contrasts renamed **`ΔAP`** |
| 4 | Primary is a **replicate-wise paired `ΔAP`**, formed inside each replicate; one-class branch `UNDEFINED_ONE_CLASS` |
| 5 | Per-metric status table: calibration `UNIDENTIFIED` under constant scores; budget recall as **expected value under randomised tie-breaking** |
| 6 | **Deciles withdrawn** — they contradicted bucket-only computation |
| 7 | Closed discs, centre-to-centre, absence strictly `d > 50`, tested at exactly 5 and 50 px |
| 8 | Mosaic expansion, seam coverage, empty-support, transform-before-crop bound into the artifact contract |
| 9 | Reframed as **feature-support strata**; physical-comparability claim withdrawn; both x and y metre spans emitted |
| 10 | Minimum justified by the **frontier invariant** (block `FRONTIER` iff all nine beyond 50), not by analogy to positivity |
| 11 | Categorical `(θ, site, T)` schema, report-only namespace, and a **loader-level allow-list rejecting the column** |
| 12 | **Per-origin** predictor projections, mutation strictly after each artifact's own `T` |
| 13 | Leakage wording inverted: held-out **pre-origin history is REQUIRED**; only `T+1` labels and fitted state forbidden |
| 14 | Undefined-replicate gate added; site/tile support diagnostics; `< 25` made **presentation-only**, sites retained in resampling |
| 15 | **Goal narrowed** to stratified static-driver utility; OSM-datedness and 30-vs-400 m claims removed; ablations named as follow-on |
| 16 | Separate `ANALYSIS-DRIVER-PLAN.candidate.md` approved by hash then atomically adopted; **nine** affected sections enumerated, not four |

Nothing was rejected. #13 was the most dangerous as written — an implementer following v1's "never from the
held-out site's outcomes" could have excluded that site's pre-origin history, making every held-out site
spuriously frontier-heavy and corrupting the primary in the direction that would look like a positive result.

## Round 2 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a (resumed; thread_id echoed and matched)
- reviewed body_sha256: ec7dd5916162b620d4bb8fe4a369bcb0f8580bec8ce2974f7dc2b6607c6e4e93
- verdict: REVISE (3 critical, 4 high, 3 medium)

Trend: 16 -> 10 findings; criticals 4 -> 3. Codex explicitly validated as sound: raw-code protection,
eligible-versus-support separation, closed 5/50 boundaries, the 51 px edge contract, per-origin
noninterference, the narrowed scientific claim, and the complete-block frontier invariant.

**A prior attempt failed before launch** — a shell heredoc quoting error meant no capture directory was
created and no request was sent. Not a round and not an attempt; the prompt was rewritten to a file.

**Two findings were my own internal inconsistencies.** #1: round 1 established that fold-specific models and
calibrators put site scores on different scales, and I then wrote a §3.4 diagnostic that pools score
variance across sites — confounded by exactly that. It also measured *dispersion* rather than ranking
power, which is what the claim needs. #2: I retracted the constancy claim in one section and left "where
loss history is not informative" standing in the Goal.

**#6 was the most valuable, and repo-grounded.** `risk/models.py:54` `columns_for_arm` selects features by
**prefix match** (`column.startswith(prefixes)`), and `fit_predict_outer` accepts caller-supplied
`extra_features`. So a column named `contagion_stratum` would be silently swept into the contagion arm, and
v2's loader-level allow-list would have policed a path that step 29 supersedes anyway.

### Critique (verbatim)

The primary is conceptually salvageable, but v2 still leaves its estimator and firewall enforcement underdefined enough for incompatible implementations.

## Findings

1. **Critical: §3.4 measures score dispersion, not ranking power.** Undefined-pattern frequencies, distinct scores, and variance do not measure association with labels; at 90 m it also omits the varying `valid_count`/`any_missing` signature, while cross-site score variance is confounded by the fold-specific models and calibrators v2 correctly identified. [§3.4](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:154>)  
   **Fix:** Report the complete missingness signature and contagion AP/AP-lift separately per held-out site, for raw and calibrated scores, then summarize site-level diagnostics without pooling raw scores.

2. **High: the primary survives material contagion ranking, but the stated interpretation does not.** `ΔAP(static+contagion, contagion)` remains a valid incremental-performance contrast, yet the Goal still calls `FRONTIER` a place “where loss history is not informative” and contagion features “weak,” neither of which follows from `d > 50`. [Goal](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:29>)  
   **Fix:** Define `FRONTIER` only as beyond the prespecified 50-pixel support and state that the primary estimates incremental static utility regardless of measured contagion strength.

3. **Critical: the point estimator and bootstrap statistic are not fully defined at the same aggregation level.** §3.3 specifies an unweighted mean of per-site AP, but §3.2 only says `ΔAP` is formed “within each replicate”; it never freezes the contributing-site set, the original-sample point formula, duplicate-site treatment, or whether one one-class site invalidates the whole replicate or is silently dropped. [Estimator](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:141>) [Governing resampling](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:280>)  
   **Fix:** Freeze `J` as original-sample two-class sites, define `Δ̂=|J|⁻¹Σj(APstatic,j−APcontagion,j)`, resample `|J|` site instances with replacement, and mark the entire replicate undefined if any instance’s within-site block draw becomes one-class.

4. **High: the 100-positive gate is misaligned with a site-equal estimator.** One hundred positives in one contributing site can pass, while positives in one-class sites that cannot enter per-site AP may inflate the gate; no minimum number of estimable sites protects the claimed macro-region quantity. [Sparse gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:221>)  
   **Fix:** Count positives only over the fixed contributing set `J` and require a predeclared minimum number of two-class sites, in addition to the positive and undefined-replicate gates.

5. **High: macro-region aggregation is explicit only for AP.** The plan does not say whether macro AP-lift is `mean(APj/πj)` or `mean(APj)/mean(πj)`, nor whether Brier, log-loss, calibration, and budget recall are site-mean or row-pooled.  
   **Fix:** Add a per-metric table freezing the site-level functional, eligible site set, macro reduction, weighting, and undefined propagation.

6. **Critical: loader enforcement is not yet attached to the actual model path.** The current wrapper delegates to `risk.models`, whose input construction infers columns by prefix and permits arbitrary `extra_features`; the approved driver says a new LightGBM path will supersede that wrapper, but v2 adds no Phase D loader contract to its affected-section list. [Current selector](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/models.py:54>) [Arbitrary extras](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/models.py:149>) [Planned replacement](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:289>)  
   **Fix:** Prefer a separately stored report artifact joined only after inference, or amend Phase D with exact immutable `FEATURES_BY_ARM` schemas and prohibit caller-supplied extra predictors.

7. **High: the categorical firewall schema remains incomplete.** “Three levels enumerated” does not freeze storage dtype, numeric codes, ineligible/nodata representation, exact filenames, shape/transform checks, or whether object/pickled arrays are forbidden. [Firewall schema](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:199>)  
   **Fix:** Freeze an exact non-pickled `uint8` schema such as `{0: INFILL, 1: EDGE, 2: FRONTIER, 255: NOT_EVALUATED}`, including name, origin, θ, shape, transform, eligibility consistency, and allowed-value validation.

8. **Medium: the 90 m invariant is mathematically correct for complete blocks, but its implementation contradicts bucket-only export.** Downstream code cannot take the minimum of unexported continuous `d_prior_px`, and minimum is not uniquely required because logical AND of native `FRONTIER` labels is equivalent. [90 m rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:122>)  
   **Fix:** Define the block label as the ordered minimum of the nine exported categorical labels, equivalently `FRONTIER iff all nine are FRONTIER`, and explicitly exclude partial or ineligible blocks before aggregation.

9. **Medium: randomized tie-breaking is not computationally frozen.** “Expected value” could mean Monte Carlo randomization or an exact analytic expectation, producing different reproducibility and uncertainty behavior, especially for area-weighted recall. [Tie rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:160>)  
   **Fix:** Freeze the deterministic analytic expectation at the boundary tie group, including fractional expected captured loss area, with no additional RNG.

10. **Medium: the project-specific infill fraction does not measure Forest Foresight’s 94% premise unless definitions match.** A `d ≤ 5 px` feature-support class is not shown to equal that paper’s “inside previously deforested areas” definition. [Prevalence claim](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:173>)  
    **Fix:** Call it the project-defined infill analogue and report the external 94% only as motivation unless an explicit definition crosswalk establishes comparability.

The raw-code protection, eligible-versus-support separation, closed 5/50 boundaries, 51-pixel edge contract, per-origin noninterference, narrowed scientific claim, and complete-block frontier invariant are otherwise sound. No files were modified.

VERDICT: REVISE
### Claude's response (round 2)

All 10 accepted, nothing rejected.

| # | Fix in v3 |
|---|---|
| 1 | §3.4 rewritten to measure **ranking power**: per-site `AP` / `AP-lift` of the contagion arm within `FRONTIER`, raw and calibrated, never pooled; plus the complete `*_undefined` signature and the 90 m `valid_count` / `any_missing` v2 omitted |
| 2 | Goal no longer asserts contagion weakness; `FRONTIER` means **only** "beyond the 50 px support", and the primary is valid regardless of measured contagion strength |
| 3 | Estimator frozen end to end: `J` = original-sample two-class sites, fixed; `Δ̂ = \|J\|⁻¹ Σ (AP_static − AP_contagion)`; resample `\|J\|` site instances with replacement; a one-class draw marks the **whole replicate undefined** rather than dropping a site |
| 4 | Gate realigned to the site-equal estimator: **≥ 100 positives within `J`** (not macro-region-wide), **≥ 6 two-class sites**, and the undefined-replicate gate |
| 5 | Per-metric macro table freezing site-level functional, eligible set, reduction and undefined propagation; `AP-lift` fixed as `mean(AP_j/π_j)`, not `mean(AP)/mean(π)` |
| 6 | **The stratum never enters a feature table** — separate report artifact joined after inference. Removes the hazard rather than policing it |
| 7 | Exact frozen schema: `uint8`, non-pickled, `{0:INFILL, 1:EDGE, 2:FRONTIER, 255:NOT_EVALUATED}`, with shape/transform/eligibility/allowed-value validation |
| 8 | Block label = ordered **minimum of the nine exported labels** (equivalently all-nine-`FRONTIER`), computable from what actually leaves the sandbox — v2's "minimum of `d_prior_px`" contradicted bucket-only export |
| 9 | Tie handling frozen as the **exact analytic expectation** over the boundary tie group, no RNG |
| 10 | Prevalence reported as the **project-defined infill analogue**; the external 94 % is motivation only, with no equality claimed absent a definition crosswalk |

The ordering `INFILL(0) < EDGE(1) < FRONTIER(2)` in #7 is what makes #8's minimum well defined — the two
fixes are linked, not independent.

## Round 3 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a (resumed; thread_id echoed and matched)
- reviewed body_sha256: e9faf6ab5ebf753778a5db5305955bcedf2adf557a30daded74f1b70ab370358
- verdict: REVISE (2 critical, 6 high, 2 medium)

Trend: 16 -> 10 -> 10 findings; criticals 4 -> 3 -> 2. Validated as sound this round: feature-support
geometry, raw-code handling, the 90 m categorical invariant, the site-equal point formula, the
whole-replicate failure principle, and the separate-report-artifact architecture.

**#8 is the sharpest finding of this review.** The gate counted positive *pixels*, but loss is spatially
contiguous: 6 sites × 100 positive pixels can be **one component per site**, and if the bootstrap block
spans each site then every replicate stays defined and all three conditions pass on what is effectively
**six mapped events**. A pixel count is not an event count, and the gate was measuring the wrong thing.

**Repo facts verified before accepting the criticals:**

- `FRAME_GROUP_ORDER = ("amazon_moist", "congo_moist", "dry_forest", "sea_peat")` — **four** macro-region
  groups, so "macro-region" was a fourfold multiplicity the primary never declared.
- Predictions carry `site`, `grid_row`, `grid_col`, `cohort`, `group`, `future_loss_pixels`
  (`risk/models.py:210`) but **not θ, origin or scale** — so v3's join really was many-to-many.
- `specification_w_rng_map.json` allocates analysis codes **0–6**, none for a stratified bootstrap.
- Step 40 **does** list prevalence, which v3's per-metric table omitted.

### Critique (verbatim)

V3 closes most prior defects, but the primary still lacks three dimensions needed for reproducible numbers, and the post-inference join needs relational integrity guarantees.

## Findings

1. **Critical: the primary still does not freeze origin, macro-region multiplicity, or score version.** Specification W has train and validation origins, four macro-region groups, and both raw and calibrated scores; §3.2 specifies none of these, so implementers can produce different `J`, gates, and `ΔAP`. [Estimator](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:162>) [Four groups](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/config.py:125>)  
   **Fix:** Freeze the primary to a named origin, presumably validation `T=2021`, and calibrated or raw scores, then declare whether the result is four region-indexed estimates or one explicitly weighted aggregate.

2. **High: `J` is not indexed for the non-primary strata.** §3.2 defines one frontier-specific `J`, but §3.3 uses “J” for AP within every stratum, θ, scale, origin, and macro-region. [Macro table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:181>)  
   **Fix:** Define `J_{θ,T,scale,region,stratum}` from the full natural-prevalence evaluation population and identify the primary as one exact indexed member.

3. **High: bootstrap edge behavior and reproducibility remain incomplete.** A block draw can contain zero frontier rows, which is neither “one-class” nor defined, and the new `J`-specific resampling universe has no canonical ordering or allocated RNG coordinate in the frozen RNG map. [Undefined rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:170>) [Current RNG map](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/artifacts/specification_w_rng_map.json:2>)  
   **Fix:** Treat zero rows or fewer than two classes in any site instance as whole-replicate undefined, retain §10’s all-eligible-pixel stopping total explicitly, and allocate a canonical RNG stream keyed by the full estimand index and sorted `J`.

4. **High: the per-metric table still has incoherent cells.** Prevalence is omitted despite being a frozen step-40 metric; budget recall admits sites with rows but zero future-loss area, where recall is undefined; and “area-weighted” does not define the macro formula or whether original or resampled area supplies its weights. [Metric table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:185>) [Governing metric list](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:341>)  
   **Fix:** Add prevalence and freeze budget recall as an explicit ratio of summed expected captured area to summed future-loss area over a fixed positive-area site set, with replicate weights and zero-area propagation stated.

5. **High: “site omitted, listed” can change the macro estimand inside bootstrap replicates.** This is especially problematic for Brier/log-loss draws with zero stratum rows and calibration draws that become constant or one-class.  
   **Fix:** Freeze each metric’s site set from the original population and mark a replicate undefined when a selected site instance cannot evaluate that metric, rather than changing the site set mid-replicate.

6. **Critical: the separate artifact closes feature leakage in principle, but the adoption table partially reopens it.** C3.21 still says “stratum column in the report-only namespace,” which can be read as adding it to the existing Parquet feature table, contradicting §4.2’s separate-artifact guarantee. [Separate artifact](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:256>) [Merge list](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:323>)  
   **Fix:** Change C3.21 to an independently named report artifact and require the feature-table schema and hashes to be identical whether or not that artifact exists.

7. **High: the post-inference join key is not a relational contract yet.** “Pixel/block id” is undefined, current predictions do not carry θ/origin/scale, and no uniqueness, cardinality, completeness, or row-preservation checks prevent a many-to-many join from duplicating observations and changing AP. [Join](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:265>) [Current prediction columns](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/models.py:210>)  
   **Fix:** Freeze 30 m `(grid_row,grid_col)` and 90 m anchored `(block_row,block_col)` IDs, stamp every key dimension into predictions, and enforce a complete many-to-one join with unique report keys, unchanged prediction-row count, and no matched `255`.

8. **High: the three-condition gate can still pass with almost no event replication.** Six two-class sites and 100 positive pixels can represent only one contiguous loss component per site; if the bootstrap tile spans each site, every replicate remains defined and all three gates pass despite only six mapped events. [Gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:296>)  
   **Fix:** Add a frontier event-support gate using existing mapped-component labels, such as at least six evaluable sites with five intersecting components each and at least 30 components total, without relabelling components after stratification.

9. **Medium: §3.4 still does not enumerate its claimed “complete” signature.** “Six radii and three window widths” is ambiguous about the separate `loss_density` and `recent_loss_density` flags, while 90 m does not state whether every predictor’s `valid_count` and `any_missing` participate jointly. [Diagnostic](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:198>)  
   **Fix:** List the exact ordered diagnostic columns and state whether distinct-score counts refer to raw scores, calibrated scores, or both.

10. **Medium: two residual claims contradict the accepted 94% limitation.** Risks says the imported premise is measured when §3.7 runs, and Proof still describes comparison “against” 94%, although §3.7 correctly says the constructs lack a crosswalk. [Risk](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:355>) [Proof](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:405>)  
    **Fix:** State consistently that the external premise remains untested and only the project-defined analogue is measured.

The feature-support geometry, raw-code handling, 90 m categorical invariant, site-equal point formula, whole-replicate failure principle, and separate-report-artifact architecture are otherwise sound. No files were modified.

VERDICT: REVISE
### Claude's response (round 3)

All 10 accepted, nothing rejected.

| # | Fix in v4 |
|---|---|
| 1 | Full estimand index frozen: `FRONTIER` / θ=30 / 30 m / **origin T=2021 (validation)** / **calibrated** scores / **one site-equal estimate over all of `J`**, with the four per-group values secondary. Isotonic can introduce ties, so raw and calibrated AP are not identical — the choice had to be made |
| 2 | `J_{θ,T,scale,region,stratum}` defined over the full evaluation population; the primary names exactly `J_{30, 2021, 30m, all, FRONTIER}` |
| 3 | **Zero-row** draws now mark the whole replicate undefined — v3 said only "one-class", leaving zero-row draws undefined in the specification rather than the data. §10's stopping rule restated as unchanged; a **new RNG analysis code** allocated, keyed by estimand index plus sorted `J` |
| 4 | **Prevalence added**; budget recall frozen as a ratio of sums over sites with **> 0 future-loss area**, using **original-sample** weights |
| 5 | Every metric's site set frozen from the original sample; a replicate that cannot evaluate a selected instance is **undefined**. v3's "site omitted, listed" was the same estimand-shifting defect the `ΔAP` rule existed to prevent, left standing in neighbouring rows |
| 6 | C3.21 merge row rewritten: an **independently named report artifact**, with the feature-table schema and hashes required **identical whether or not it exists** — the testable form of the guarantee |
| 7 | Join frozen as a relational contract: full stamped keys at both scales, **many-to-one**, unique report side, **row count preserved**, matched `255` a hard error |
| 8 | **Event-support gate added** as condition 3: ≥ 6 sites with ≥ 5 intersecting mapped components each, ≥ 30 total, using C2.19's existing labels and **not** relabelled after stratification |
| 9 | Missingness signature enumerated as exactly **17** flags at 30 m — v3's "six radii and three window widths" never said the two density families carry separate flags; 90 m includes per-predictor `valid_count` / `any_missing`; distinct-score counts split raw vs calibrated |
| 10 | The external 94 % is stated as **untested**; Risks and Proof no longer imply a comparison §3.7 explicitly disclaims |

## Round 4 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a (resumed; thread_id echoed and matched)
- reviewed body_sha256: c746d75db252238bff31ab5c0feb6beef13ef3c04c6a6a2bc9d4e88cb4e16499
- verdict: REVISE (2 critical, 4 high, 3 medium)

Trend: 16 -> 10 -> 10 -> 9; criticals 4 -> 3 -> 2 -> 2. Validated as coherent: the fully indexed
validation-origin estimator, the fixed-site bootstrap principle, the categorical frontier construction, and
the separate post-inference report artifact.

**#6 is a residual overclaim I should have caught myself.** Step 32 excludes the contagion arm from the
tuning grid and fits it once with frozen hyperparameters, while `contagion+static` is tuned over four
candidates and each arm selects its own calibrator. So `ΔAP` contrasts two pipelines differing in
**features, model selection AND calibration** simultaneously. v4's Goal still called it "incremental
predictive utility of static drivers as a class". It cannot be — the design does not separate those three.

**#4 is the geographic analogue of round 3's #8.** Just as pixel counts are not event counts, a pooled `J`
is not geographic coverage: six evaluable sites and thirty components could sit entirely inside one of the
four `FRAME_GROUP_ORDER` groups while the primary is presented as global.

**#9 was mine again** — I added the event-support condition in v4 and left "all three required" standing
beside four enumerated items, with a matching stale "three" in Proof. Eighth instance this session of a
count or cross-reference surviving its own edit.

### Critique (verbatim)

V4 is close, but several remaining gaps can still change the reported primary or let the gate certify a geographically unrepresentative result.

## Findings

1. **Critical: the “frozen 3×3 tiling” has no frozen anchor.** C2.18 defines complete nine-pixel blocks but never states whether block `(0,0)` starts at the site-core top-left, the source-tile origin, or a global GFC lattice; those choices change 90 m membership, labels, and join IDs. [Join key](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:323>) [C2.18](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:221>)  
   **Fix:** Freeze zero-based `block_row=floor(grid_row/3)` and `block_col=floor(grid_col/3)` relative to one explicitly named site-grid origin, including the treatment of leading and trailing partial blocks.

2. **Critical: the RNG allocation is described but not frozen numerically.** “A new analysis code” does not say `7`, and a variable-length tuple containing strings and sorted `J` cannot directly become NumPy’s integer `SeedSequence.spawn_key`; implementations may hash or encode it differently. [RNG rule](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:210>) [Current map](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/artifacts/specification_w_rng_map.json:2>)  
   **Fix:** Allocate analysis code `7` explicitly and serialize the full estimand plus sorted site IDs into a canonical integer `unit_index` registry used with the existing entropy, bit generator, and spawn-key layout.

3. **High: the join checks only prediction-to-report completeness.** A missing prediction row, duplicated unit within one arm, or arm-specific population difference can pass because every remaining prediction still matches one report row and row count remains unchanged. [Join contract](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:328>)  
   **Fix:** For every model/arm, require prediction-key uniqueness and exact equality with the evaluated report-key set, plus identical unit sets across arms and byte-identical pre-join predictions under report-artifact mutation.

4. **High: the four-condition gate can pass using only one macro-region.** The overall `J` is pooled across groups, but six evaluable sites with 30 components can all come from one of the four groups, allowing a purported all-groups primary with no frontier evidence from the other three. [Primary region](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:177>) [Gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:365>)  
   **Fix:** Require prespecified event-support coverage in every group, preferably the existing ≥3 evaluable sites and ≥30 intersecting components per group, or explicitly redefine the primary as conditional on represented groups.

5. **High: fixed original-sample site sets are coherent only for a conditional estimand.** They avoid bootstrap set drift, but `J` is outcome-conditioned and excludes every zero-positive, positive-only, or otherwise one-class site; the interval therefore says nothing about site-eligibility uncertainty or static utility across the full frame.  
   **Fix:** Name the target “the site-equal mean among original-sample two-class frontier sites,” report exclusions by group and reason, and prohibit broader full-frame interpretation.

6. **High: the design still cannot attribute the entire contrast to static drivers.** The contagion arm is deliberately fixed while `contagion+static` is grid-tuned, and each arm selects its calibrator separately, so calibrated `ΔAP` contrasts two pipelines differing in features, model selection, and tie-inducing calibration. [Claim](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:58>) [Unequal tuning](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:297>)  
   **Fix:** Narrow the claim to incremental performance of the tuned-and-calibrated `contagion+static` pipeline over the fixed contagion pipeline, not utility attributable solely to static features.

7. **Medium: bootstrap budget recall remains arithmetically ambiguous.** “Original-sample area weights” does not specify how duplicated site instances combine original weights with recall computed from resampled rows. [Budget row](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:231>)  
   **Fix:** Freeze the replicate formula explicitly, for example `Σ_k A_orig,j(k)·R*_{j(k)} / Σ_k A_orig,j(k)`, where each duplicated site instance has an independent block-resampled recall.

8. **Medium: the artifact filename is still deferred rather than frozen.** “Frozen pattern, recorded in the allow-list” supplies no actual pattern, despite exact names being part of the firewall trust boundary. [Artifact schema](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:338>)  
   **Fix:** State the exact path/name template, metadata filename, and version now, and bind those literal names into the supervisor allow-list.

9. **Medium: the gate specification contradicts itself about its cardinality.** It says “all three required” while enumerating four, and Proof again says three and omits the event condition from that list before testing it separately. [Gate heading](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:369>) [Proof](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:480>)  
   **Fix:** Replace every stale “three” and three-item proof list with the same canonical four-condition gate.

The fully indexed validation-origin estimator, fixed-site bootstrap principle, categorical frontier construction, and separate post-inference report artifact are otherwise coherent. No files were modified.

VERDICT: REVISE
### Claude's response (round 4)

All 9 accepted, nothing rejected.

| # | Fix in v5 |
|---|---|
| 1 | Block anchor frozen: **`block_row = floor(grid_row/3)`, `block_col = floor(grid_col/3)`**, zero-based on the named site grid origin; leading partials impossible, trailing partials excluded per C2.18 |
| 2 | RNG frozen **numerically**: **analysis code `7`** added; the estimand and sorted `J` are serialised through the existing canonical `unit_index` registry to one integer spawn-key coordinate, since a tuple of strings is not a `SeedSequence.spawn_key` and two implementations would hash it differently |
| 3 | Join integrity made **two-sided and cross-arm**: prediction keys unique per (model, arm) and **exactly equal** to the evaluated report-key set, identical unit sets across arms, pre-join predictions byte-identical under report mutation |
| 4 | Region dimension changed from "all" to **represented groups**, emitted with the estimate; gate condition 4 requires **≥ 2 groups, each with ≥ 3 evaluable sites** |
| 5 | Estimand explicitly named **conditional**: the site-equal mean among original-sample two-class `FRONTIER` sites. Excluded sites reported by group and reason; full-frame interpretation prohibited |
| 6 | Goal narrowed to the **pipeline contrast** — tuned-and-calibrated `contagion+static` over fixed `contagion` — with the three confounded dimensions named |
| 7 | Budget recall replicate formula frozen as `Σ_k A_orig,j(k)·R*_j(k) / Σ_k A_orig,j(k)` |
| 8 | Artifact path frozen literally, with sidecar, bound into the supervisor allow-list |
| 9 | Gate is **five conditions** everywhere — heading, enumeration and Proof |

On #4 I chose **≥ 2 groups** rather than Codex's suggested all-four coverage, and said why in the plan:
requiring all four would almost certainly suppress a sparse `FRONTIER` primary outright, and the
conditional label plus the emitted group list is what keeps a two-group result honest. That is a judgement
call, recorded as one.

## Round 5 — codex (FINAL — MAX_ROUNDS reached)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a (resumed; thread_id echoed and matched)
- reviewed body_sha256: 99478d926af02944d4b56cbab32d4160a0e91760f434126b9e564ac468ad8b6b
- verdict: REVISE (2 critical, 3 high, 1 medium)

**A prior attempt was killed mid-turn** — `thread.started` and `turn.started` fired against the correct
session but no `turn.completed` and **no verdict file was created**, so it was NOT a round and did not
consume `MAX_ROUNDS`. Classified `unknown` (transient), first occurrence on this adapter, so switching was
explicitly not recommended. Josh authorised one unchanged retry into a fresh capture directory.

Full loop: **16 → 10 → 10 → 9 → 6** findings; criticals **4 → 3 → 2 → 2 → 2**.

**The flagged disagreement resolved in the plan's favour, conditionally.** Codex: *"The two-group floor is
defensible for an explicitly conditional exploratory estimate… I do not object to two rather than four
groups provided finding 3 is fixed and the represented-group list remains inseparable from every reported
estimate."* Both conditions are met in v6. It also validated the conditional estimand as "unusually clear"
and confirmed the post-inference join closes the feature-leakage path.

**Two findings verified in the repo before acceptance, and both were sharper than they read:**

- **#2** — `forecast/specification_w.py:339` **regenerates** `analysis_codes` 0–6 from a dict literal, so
  hand-adding code `7` to the JSON would be **erased on the next regeneration**. And v5's Out of scope
  froze the Specification W artifacts blanket while the plan simultaneously required an RNG change — the
  plan forbade its own prerequisite.
- **#3** — `FORECAST-PLAN.md:224` defines an **evaluable site** as one with ≥ 5 mapped components *in the
  test origin*, with no reference to `FRONTIER`. Condition 4 borrowed that governing term while condition 3
  required frontier-intersecting components, so the two gate conditions silently meant different things and
  a second group could qualify with almost no frontier evidence.

**#5 was mine again** — v5 corrected the Goal to a pipeline contrast and left Key decisions still asserting
"stratified static-driver utility". Ninth instance this session of a claim surviving its own correction in
a neighbouring section.

### Critique (verbatim)

Material defects remain. The two-group floor is defensible for an explicitly conditional exploratory estimate, but parts of its implementation are still ambiguous.

1. **Critical — RNG determinism is still not implementable as written.** The plan sends `(θ,T,scale,region,stratum,sorted J)` through an “existing canonical `unit_index` registry,” but step 28 only defines a `(θ,site,origin,scale)` mapping; it provides no encoder or ordering for a variable-length site set ([frontier plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:245>), [driver plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:286>)).  
   Fix: Define and persist an explicit canonical key table—field encodings, sort order, integer assignment, and collision rule—for every stratified estimand before any draw.

2. **Critical — adoption does not authorize the RNG changes it requires.** The affected-section list omits step 28, `specification_w_rng_map.json`, and its generator, while Out of scope still freezes Specification W artifacts; moreover, the current generator would recreate codes 0–6 and erase an independently edited code 7.  
   Fix: Add step 28, the RNG map, and its generating code to the merge list and carve precisely those changes out of the frozen-artifact prohibition.

3. **High — the geographic gate can still pass with weak evidence in its second group.** The governing definition of “evaluable site” means five components anywhere in the test origin, whereas condition 3 requires five components intersecting `FRONTIER`; condition 4 reverts to the unqualified term ([frontier gate](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:415>), [governing definition](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:222>)). A second group could therefore contribute three nominally evaluable sites with almost no frontier event support.  
   Fix: Define `FRONTIER-event-supported site` once as `j∈J` with at least five distinct existing components intersecting `FRONTIER`, and require at least three such sites in each qualifying group.

4. **High — the 3×3 anchor still points to a nonexistent definition.** V5 says the site-grid origin is “named in C3.21,” but current C3.21 only defines the Parquet path; it does not say whether `grid_row=0` is the cropped site array, source tile, or global GFC lattice ([frontier anchor](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:162>), [current C3](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:233>)).  
   Fix: Define `grid_row/grid_col` as zero-based indices into one explicitly named site array and transform, require block IDs to be computed before core tiling, and give the exact trailing-row/column exclusion formula.

5. **High — one static-feature attribution claim survived.** The Key decisions section still summarizes the result as “stratified static-driver utility,” directly contradicting the newly correct pipeline-level qualification ([stale claim](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:477>)).  
   Fix: Replace it with “stratified performance contrast between the tuned/calibrated contagion+static pipeline and the fixed, separately calibrated contagion pipeline.”

6. **Medium — edge-exactness provenance has no destination in the frozen schema.** Section 1.5 requires recorded crop indices, halo coverage, and seam handling, but the frozen sidecar contains none of them; consequently, production artifacts cannot later demonstrate that edge assignments met the contract ([edge contract](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:139>), [sidecar schema](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:379>)).  
   Fix: Add source-grid identity/hash, core window, per-edge halo widths, seam-coverage evidence, and empty-support status to the sidecar or another literally named provenance artifact.

The conditional estimand itself is now unusually clear, and the post-inference join closes the identified feature-leakage path. I do not object to two rather than four groups provided finding 3 is fixed and the represented-group list remains inseparable from every reported estimate.

VERDICT: REVISE
### Claude's response (round 5) — all 6 accepted, applied in v6, UNREVIEWED

| # | Fix in v6 |
|---|---|
| 1 | A **new persisted key table** `specification_w_stratified_keys.json` with frozen field encodings, lexicographic site ordering, sequential integer assignment and a fail-closed collision rule. Step 28's `(θ, site, origin, scale)` mapping genuinely cannot encode a variable-length site set |
| 2 | Merge list gains **step 28**, **the RNG map JSON**, and **the generator at `forecast/specification_w.py:339`**; Out of scope now freezes Spec W artifacts **with exactly those three carve-outs** |
| 3 | **`FRONTIER-event-supported site`** defined once — `j ∈ J` with ≥ 5 distinct C2.19 components intersecting `FRONTIER` — and used by **both** conditions 3 and 4 |
| 4 | `grid_row`/`grid_col` defined as zero-based indices into the **site's pinned GFC window array and recorded transform**; block IDs computed **before** core tiling; trailing exclusion given as `3·block_row + 2 ≥ n_rows` |
| 5 | Key decisions restated as the pipeline contrast |
| 6 | Sidecar carries source-grid identity/hash, core window, per-edge halo widths, seam evidence and empty-support status, so §1.5's edge contract is demonstrable rather than merely required |

**These six fixes are unreviewed.** `MAX_ROUNDS` is exhausted; two attempts remain.

## Round 6 — codex (FINAL — both caps exhausted)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb801-5928-7271-add9-781dff680d8a (resumed; thread_id echoed and matched)
- reviewed body_sha256: 8957a5db4c39175335b7b32d47c84e529f4d0e50b5fe4ff42ac9508ba6c37fe5
- verdict: REVISE (2 critical, 2 high, 2 medium)

**CAP EXTENSION, recorded.** `MAX_ROUNDS` was 5 and was raised to **6** by Josh's authorisation, to review
the six round-5 fixes rather than ship them unreviewed. Earlier statements in this log that `MAX_ROUNDS`
was exhausted at round 5 are superseded by that extension. After round 6: **rounds 6 of 6, attempts 8 of 8
— both caps genuinely exhausted.**

Full loop: **16 → 10 → 10 → 9 → 6 → 6** findings; criticals **4 → 3 → 2 → 2 → 2 → 2**.

**The science is done.** Codex: *"The scientific estimand and claim language are now sound… no material
scientific overclaim remains."* Not one round-6 finding concerns the statistics, the estimand or the claim.
All six are RNG contract, artifact lifecycle, and scope bookkeeping.

**#6 is the same self-forbidding pattern I had just fixed one round earlier.** Round-5 #2 caught the plan
freezing the Spec W artifacts while requiring an RNG change; I carved out the RNG artifacts and did not
notice that "no change to sampling" plus the Out-of-scope sampling prohibition equally forbade the new
conditional outer-site bootstrap the plan itself introduces. Fixing a pattern in one location and leaving
it in another is the defect this review has found most often in how I revise.

**#5 was mine too** — I replaced "evaluable site" in the gate and left it standing in the Proof line I wrote
in the same edit. Tenth instance this session.

### Critique (verbatim)

The scientific estimand and claim language are now sound, but the RNG contract remains materially under-specified.

1. **Critical — integer assignment is execution-order dependent.** “Sequential in first-request order” means two conforming implementations that request estimands in different orders assign different integers and therefore different bootstrap streams ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:269>)).  
   Fix: Collect every requested key before code-7 draws, sort by one canonical serialized representation, and assign integers `0…N−1` in that order; prohibit on-demand first-request assignment.

2. **Critical — the key serialization is not injective or fully specified.** “Unit indices concatenated” does not distinguish an integer array from digit/string concatenation, the group-index base is unstated, and the JSON’s path, top-level schema, version, uniqueness validations, and hash binding are missing.  
   Fix: Freeze a literal path and canonical JSON schema using zero-based group indices and arrays of `{site_id, step28_unit_index}`, require tuple↔integer bijection, and bind the table hash into the evaluation output or RNG map.

3. **High — the outcome-derived table’s lifecycle can reopen a noninterference channel.** The merge places it in Phase-C step 28, before inference, although its key contains outcome-conditioned `J`; unlike the stratum artifact, prediction invariance under this table’s presence or mutation is not required ([J definition](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:239>), [merge row](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:488>)).  
   Fix: Let step 28 reserve code 7 and its schema only, then construct the key table after inference and `J` determination but before bootstrap draws, with pre-join predictions invariant to its absence or mutation.

4. **High — “represented groups” still lacks a set definition.** It affects `J`, the RNG region key, and gate condition 4, but the plan never resolves whether it means every group containing any `J` site or only groups meeting the three-event-supported-site threshold; those interpretations can change both the point estimate and seed ([estimand](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:228>), [gate](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:442>)).  
   Fix: Compute `J*` over the full 36-site frame, define `G_J = sorted(unique(group(j): j∈J*))`, state whether the primary retains all of `J*`, and express the gate formally as `|{g∈G_J: supported_sites(g)≥3}|≥2`.

5. **Medium — the operative gate is corrected, but Proof reintroduces the rejected term.** Line 567 again says “<3 evaluable sites,” whose governing meaning is components anywhere in the origin, even though the later test uses the correct frontier-specific definition.  
   Fix: Replace every residual “evaluable site” reference in the stratified gate and proof with `FRONTIER-event-supported site`.

6. **Medium — the scope still forbids its own evaluation-resampling amendment.** “No change to … sampling” and Out of scope’s blanket sampling prohibition conflict with the new conditional outer-site bootstrap and code-7 stream ([scope claim](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:96>), [bootstrap](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRONTIER-STRATIFICATION-PLAN.md:250>)).  
   Fix: Limit the prohibition to Phase-C4 training sampling and the existing within-site tile-draw geometry, explicitly carving in the new stratified evaluation resampling.

The three named mutations of existing frozen material are narrow enough and do not license unrelated edits. The missing piece is to classify the new key table and its builder explicitly as new report-side artifacts. The single `FRONTIER-event-supported` definition otherwise closes the substantive gate defect, the two-group floor is defensible, and no material scientific overclaim remains.

Before adoption, the provenance must also be reconciled: the current file still says `status: deadlocked`, and the review log still says `MAX_ROUNDS` is exhausted despite the user-authorized extension.

VERDICT: REVISE
### Claude's response (round 6) — all 6 accepted, applied in v7, UNREVIEWED

| # | Fix in v7 |
|---|---|
| 1 | Integer assignment made **order-independent**: all requested keys collected, sorted by canonical serialisation, assigned `0…N−1`. On-demand first-request assignment **prohibited** — it made the bootstrap stream depend on execution order |
| 2 | Serialisation frozen as a **JSON array of `{site_id, step28_unit_index}`** (not digit concatenation, which is not injective), zero-based group indices, literal path, `schema_version`, asserted **bijection**, and the table **sha256 bound into the evaluation output and RNG map** |
| 3 | Lifecycle corrected: step 28 **reserves code 7 and the schema only**; the table is built **after inference and after `J`**, since its key is outcome-conditioned, with pre-join predictions byte-identical whether it is absent, present or mutated |
| 4 | `represented groups` formally defined: `J*` over the **full 36-site frame**, `G_J = sorted(unique(group(j) : j ∈ J*))`, the primary **retains all of `J*`** (coverage is a gate, not a filter), and condition 4 stated as `\|{g ∈ G_J : supported_sites(g) ≥ 3}\| ≥ 2` |
| 5 | Residual "evaluable sites" removed from Proof |
| 6 | Scope carved: Phase-C4 **training** sampling and within-site tile geometry stay frozen; the **evaluation-side stratified resampling** of §3.2 and its code-7 stream are explicitly carved in |

**These six fixes are unreviewed and no attempts remain.**

### Resolution — DEADLOCKED, not approved

Six rounds, no `APPROVED`. Claude has **no counter-position on any outstanding finding** — every round was
accepted in full and nothing was rejected. This is a budget exhaustion, not a disagreement.

What a reader should take from the artifact: the scientific design is reviewer-endorsed as sound and free of
overclaim; the remaining risk is concentrated in the **RNG determinism contract and artifact lifecycle**,
whose v7 fixes have not been adversarially checked.
