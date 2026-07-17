# Plan: AMENDMENT-4 — PIF is infeasible in-frontier; the combined floor is unreachable
_Locked via grill — by Claude + Josh, 2026-07-17. Revised after Codex review round 1._

> Scope note: this is the **amendment plan**, not the study plan. `PLAN.md` (frozen, 860 lines) is
> NOT edited or overwritten here. On approval this is appended as AMENDMENT-4 in the style of
> AMENDMENT-1..3.

## Goal

`risk.prepare` fails at every cohort site: the L3 PIF population is empty or under its 5,000-px
floor, because PIF demands forest ≥1,920 m from **any** 2001–2020 loss pixel while the study
deliberately samples **inside active frontiers**. Round-1 review then established something
stronger: with the distance bug fixed, **the locked combined-cohort floor of 14 is arithmetically
unreachable**, which triggers L13.6's *stop and re-plan*. This plan is that re-plan.

It must not become a rescue. The design's whole purpose is that it can **reject** the hypothesis
and cannot **falsely confirm** it, and review found a mechanism by which PIF attrition could
*favour* confirmation (finding #7). The restructure below is adopted because it **removes** that
mechanism, not because it restores a cohort.

## Corrected evidence (read-only; no locked parameter moved)

**Prerequisite bug, fixed.** `risk.prepare` had never run: `_area_weighted_values(array, support,
transform, bounds)` received 3 arguments at both call sites (`risk/prepare.py:147,152`), so bounds
landed in the `transform` slot and the path raised `TypeError` on contact. Original code from
`b4f5265`; no test exercised `prepare_site`. Fixed by passing `source.transform`; regression test
`risk/tests/test_clearobs_area_weighting.py` added. Suite 22 passing. **Uncommitted.**

**Round-1 finding #2 (confirmed, material).** The distance transform ran only over the downloaded
extent, so the array edge read as "no loss beyond" and edge forest was credited with inflated
distances. Re-run with a 1,980 m Hansen halo, counting only pixels inside the true extent, every
site's PIF count **falls** (correct signature: added loss can only shrink distances):

| | no halo | **halo (correct)** |
|---|---|---|
| `santa_cruz_bolivia` | 5,464 (PASS) | **3,367 (FAIL)** |
| `F4_P004.140_P0114.250` | 3,166 | 0 |
| `mai_ndombe_drc` | 2,061 | 769 |
| `F1_P000.180_M0063.250` | 330,062 | 314,793 |

**Consequence — the floor is unreachable.** Legacy PIF survivors drop from 2 to **1**
(`tshopo_drc` only). The frame contributes at most 12. Combined cohort ≤ **12 + 1 = 13 < 14**, and
13 is an *upper* bound because the real L2 clear-observation gate can only remove more. **L13.6:
stop and re-plan.**

**Round-1 finding #6 (confirmed).** The earlier "100/50/20/8%" rates used stopping-time
denominators (screening halted at 3 successes), so `3/k` was a biased survival estimate. Re-run
over a **fixed 40-box rank-order prefix per stratum, no stopping rule, halo included**:

| Stratum | Survival | Refills 3 from the prefix? |
|---|---|---|
| amazon_moist | 26/40 (65%) | yes |
| congo_moist | 25/40 (62%) | yes |
| sea_peat | 10/40 (25%) | yes |
| **dry_forest** | **2/40 (5%)** | **no — binding constraint** |

The biome gradient survives correction; the dry_forest stratum is the constraint on frame 12/12.
These remain upper bounds: the L13.4 ≥50 km separation check is not applied here.

**Other confirmed defects** (verified in code, not taken on Codex's word):
- **#16:** `prepare_site` writes model-consumable cell tables even when `site_qc.passed` is false
  (`risk/prepare.py:346–375`), and `risk/models.py` ingests any CSV with no cohort-manifest check
  → a QC-failed site can silently reach the model.
- **#5:** L13.5 requires a frame site failing the real L2 gate to be **replaced from the queue**
  until 3 survive or the queue exhausts. The previous draft wrongly said "dropped".
- **#4:** L13.4 locks a **deterministic round-robin** (`amazon → congo → dry_forest → sea_peat`,
  rounds 1–3) with a *cross-stratum* 50 km rule. Also: a replacement landing within 50 km of a
  legacy box **drops that legacy box** — which can remove `tshopo_drc`, the last legacy survivor.
- **#18:** stale "5 years" text survives at `PLAN.md` lines 235, 310, 717, 784, 800 — beyond L3.
- **#12 premise verified:** `pif_median` is consumed at exactly one line —
  `features.py:77`, `result["tailmass"] = mean(values < pif_median - 0.20)`. Nothing else in
  either pipeline requires PIF.

## Approach

**A. No locked parameter is retuned.** The 1,920 m rule, `treecover2000 ≥ 70`, the 5,000-px floor,
the 4 km buffer (L11), and the L13.6 floors all stand exactly as written. Reading B (loss-cell) is
**rejected**: it is the most permissive tested and lands on exactly the floor while still missing
12/12 — choosing a definition because it clears a floor is the failure mode the freeze prevents.

**B. Change the PIPELINE, not the estimand hierarchy.** L13.8 stands **unchanged**: Combined LOSO
remains **primary**, frame-only LOSO remains the generalization analysis. Round-2 review (#8, #9)
established that the previous draft's "retire the combined analysis, elevate the frame" was both
(a) a post-freeze hierarchy change dressed up as execution of an existing one — L13.8 says
"Combined LOSO … **Primary**", and `PLAN.md:922` grants the frame only *generalization claims* —
and (b) unnecessary, because the floor is unreachable **only for the PIF/normalized arm**. Without
PIF the combined cohort can reach 19 ≥ 14 and the frozen primary is viable. It is therefore kept.

The PIF requirement is a property of the **normalization**, not of the science question. Since
`pif_median` feeds only `tailmass` (`features.py:77`):

1. **PIF-free pipeline (carries the frozen L13.8 analyses): unnormalized, `*_tailmass` dropped.**
   No PIF population required → **no PIF-driven attrition**, **no new downloads** (imagery is on
   disk). Cohort = every site passing the *non-PIF* L2 checks (clear observations, nodata,
   out-of-range) — potentially all 19, including the saturated frontiers (Rondônia, mato_grosso,
   riau_sumatra, gran_chaco) that PIF deletes. Runs **both** frozen analyses: Combined LOSO
   (primary, if non-PIF L2 survival ≥ 14) and frame-only LOSO (generalization, if 12/12).
2. **Normalized pipeline (secondary): unchanged L3, PIF-feasible sites only**, attrition reported
   by biome group, generalization bounded to PIF-feasible frontiers.
3. **Normalized/tailmass-free pipeline (new, #3): built solely to isolate normalization** — see F.

**Adopted because it removes finding #7's mechanism**, not because it restores n. Under the
previous design PIF QC preferentially deleted saturated frontiers — exactly where block B
(contagion) is strongest — so the C/D-vs-B contrast would have been measured on a subpopulation
with an artificially weakened baseline, biasing **toward confirming** the hypothesis. The PIF-free
pipeline has no PIF selection, so the primary contrast runs on the unselected cohort.

**B2. Dropping tailmass weakens the BASELINE, not the history block (#6 — correcting this plan).**
Verified: `d_*` features are `slope_mean`, `slope_std`, `slope_p10`, `tstd_mean`, `delta` — **none**
use tailmass. `tailmass` is exclusively `c_{name}_tailmass`, part of the **static 2020 snapshot**
that block D must beat. Removing it therefore makes the baseline *less* complete and can **inflate
D's incremental AP** — a false-confirmation mechanism this plan itself introduced. The previous
draft's "only the tailmass family is lost, every d_* survives" was wrong in a direction that
favoured the hypothesis. Mandatory consequences:
- The primary claim is scoped to **"history adds value beyond the prespecified *tailmass-free*
  snapshot"** — never "beyond the snapshot".
- A **full-C vs tailmass-free comparison is required on the PIF overlap**, where both are
  computable.
- **Positivity that appears only after tailmass removal is `INCONCLUSIVE`**, not a finding.

**C. The patch/reference-donut arm is withdrawn entirely.** It was the previous draft's
sensitivity. Review findings #9–#11, #13, #14 (unexecutable placement rule, "same relative orbit"
not delivering same-scene control, circular validation, gate omitting the block under test,
uncalibrated margins) are all **accepted**, and #12 supplies a strictly better route: the PIF-free
arm answers the same question — keeping saturated frontiers visible — with fewer assumptions,
zero new locked parameters, and zero downloads. Withdrawn, not deferred.

**D. Locked distance procedure (fixes r1#2, r1#3, r2#11).** Every PIF distance computation —
census, screen, and `prepare` — reads a **1,980 m Hansen halo** beyond the counted extent,
computes the transform on the haloed array, and counts only pixel centres inside the canonical
extent. One canonical buffered footprint and pixel-centre rule is specified for **both** the
no-download screen and full `prepare`.

The previous ±20% guard is **withdrawn as an invented threshold** (r2#11). Replaced by a bound that
is **measured, not assumed** (r3#11): the claim that backend projection/grid snapping displaces
each edge by at most one 10 m pixel is *not* derived anywhere in code, so it is not relied upon.
Instead, the **canonical-vs-master edge displacement is measured and recorded for every raster**
already on disk (a free check — the composites exist). From the measured displacement `e` (in
Hansen pixels, per edge) the worst-case count discrepancy is `B = 2·(H + W)·e` for an `H×W`
window; **any candidate whose screened count falls in `[5000 − B, 5000 + B]` goes to the real
gate**. Where `e` cannot be measured or bounded for a geometry, that candidate **bypasses
screening entirely** and is downloaded. Screening therefore only ever excludes candidates below
the floor *by more than a measured bound* — in practice the large majority, whose counts are 0.

**D2. Mandatory drift falsification gate — executable spec (r2#1/#2/#4, r3#1–#8).**
Prespecified and **hashed before any label is attached**; run **independently at every primary
site**, not only on the PIF overlap (which is selected *against* saturation and may vanish).
Drift is the mirror-image false-confirmation path: uncorrected sensor/atmosphere drift can
*fabricate* `d_*` trend. Round 3 correctly judged the previous wording "a promise of a guard";
this is the guard.

- **D2.1 Control definition — categorical, never reflectance-based (r3#1).** Selecting controls
  because their 2018–2020 reflectance looks stable is circular and would near-guarantee a pass; it
  is **prohibited**. Both classes are defined from ≤2020 *categorical/history* data only, and
  **two disjoint classes are mandatory (r3#8)**. The **water class is withdrawn** — the D2.2 census
  found permanent water at only **10/19** sites (zero pixels at two), so requiring it would make
  the headline `INCONCLUSIVE` by construction under D2.7 and the study could return no finding at
  all, not even the null. Nor is water replaceable by another surface: in moist tropical frontiers
  the categorically stable non-vegetation classes (bare, built) are near-absent, while
  grassland/shrubland/cropland **are the post-clearing state** and would import the very signal
  being corrected. The two classes therefore probe the actual concern behind r3#8 —
  **degradation contamination of a vegetation control** — instead of surface-type transport:
  - **(a) `veg_near`** — forest within 640 m of 2001–2020 loss (frontier-exposed).
  - **(b) `veg_far`** — forest beyond 640 m of 2001–2020 loss (interior).
  - Forest = Hansen `datamask==1`, **`treecover2000 ≥ 30`**, no 2001–2020 loss. The threshold is
    the study's **own forest universe** (`eligible30`, `prepare.py:222`), i.e. the population the
    analysis support is built from — a control must match the population it corrects. It is **not**
    PIF's 70%, which exists because pseudo-invariance needs dense canopy, a requirement that does
    not apply to a drift control. Fixed before any drift is inspected.
  - **Disjoint, not nested** (split at `CELL_SIZE_M`, the study's own grid unit), so agreement is
    not tautological; **both are forest**, so radiometric transport to the target is ideal, where
    water's is the worst of any surface.
  - **Disagreement ⇒ D2 fails (r3#8):** if `veg_near` and `veg_far` corrections differ beyond the
    locked margin, the estimated "drift" is contaminated by **real degradation** and the gate
    fails. The favourable class can never be chosen — and per r4#4 there is **no combination
    rule**: both adjusted pipelines are run separately and the raw conclusion must survive **both**
    (D2.6).
  - **Bias direction, stated in advance:** a vegetation control that itself degrades causes the
    correction to **erase real history** → bias **toward the null**, i.e. conservative against the
    hypothesis, the same direction that made AMENDMENT-3 defensible. It cannot fabricate a
    positive. Over-correction flipping the sign would surface as `HISTORY HARMS` (F2 row 4), which
    is reported, not folded into "null".
- **D2.2 Effective support + the completed pre-approval census (r3#2, r4#1).** Adjacent 10 m pixels
  are not independent, so support is counted in **640 m blocks** (the study's grid). **The census
  is now run** (label-blind, ≤2020 Hansen, read-only) — blocks holding ≥53 control pixels:

  | | `veg_near` blocks | `veg_far` blocks |
  |---|---|---|
  | all 19 sites have both | **19/19** | **19/19** |
  | rondonia | 1,845 | 104 |
  | gran_chaco_paraguay | 1,350 | 179 |
  | **F4_M002.900_P0105.500 (binding)** | 622 | **11** |
  | riau_sumatra | 2,349 | 26 |

  Control masks are **time-invariant by construction** (`treecover2000`, loss ≤2020, `datamask`),
  which satisfies r3#2's fixed-pixel requirement directly; the year-varying conjunct is the
  clear-observation intersection — **the identical pixels and block weights must have adequate
  finite observations in all three years**, and a site failing that fixed intersection is
  insufficient-support, never silently re-populated per year.
  **The floor is NOT set here.** It must be locked from a power/equivalence calculation on the
  block bootstrap **before any drift diagnostic is inspected** (r4#1); the census is reported first
  precisely so the floor cannot be chosen to fit it. **Known consequence:** `veg_far` at
  `F4_M002.900_P0105.500` has 11 blocks, so a floor above ~11 makes that site
  insufficient-support and, under D2.7, the **entire headline `INCONCLUSIVE`**. That is the honest
  cost of not excluding sites, and it is a live possibility, not a formality.
- **D2.3 Estimator — spatial, band-first, with a locked correction field (r3#5, r4#3).** A
  site-wide common-mode scalar cannot catch spatially varying aerosol/BRDF, which can fabricate
  `d_*_slope_std` and distort `p10` even when the median shift is zero. Shifts are estimated **per
  640 m block, per band**; **both** common-mode and spatial-heterogeneity drift are tested; **bands
  are corrected first**, then indices and **every** D feature are recomputed from corrected bands.
  **Correction field (locked before any shift is computed):** a target block containing control
  support takes **its own** block shift; a block without control support takes the
  **inverse-distance-weighted mean of its k = 4 nearest control blocks** (geodesic, block centres);
  if the nearest control block exceeds **1,920 m** (3 cells — the study's own neighbourhood
  radius), the block is **unsupported** and the site is insufficient-support. Edge blocks use the
  same rule with no extrapolation beyond the buffered extent. No smoothing, no site-mean fallback.
- **D2.4 Margins — and the repeatability limitation, stated not papered over (r3#4/#6, r4#5).**
  Margins are a locked function of a **pooled cohort-wide repeatability reference**, *not* of each
  site's own noise; a site whose dispersion exceeds a locked multiple of that reference is
  **insufficient support** rather than granted wider, easier bounds. **Round 4 is right that the
  stored `dispersion` band is not clean repeatability**: verified at `download_timeseries.py:100`
  it is the temporal SD across a ~4-month season, mixing phenology, atmosphere, platform and real
  surface change, and it is **not** the sampling distribution of the annual median — used raw it
  would give an over-wide margin that lets drift pass. Therefore the conversion from
  (`dispersion`, `clearobs`) to median-composite uncertainty is **prespecified and validated
  against split-half composites**. Split-half products are **required for all sites** for this
  validation (not only platform-mix triggers) — an explicit, accepted cost item (see L).
- **D2.5 Platform/orbit — diagnostic only, and the correction does not depend on it (r3#4, r4#6).**
  Round 4 is right that `product_ids` list every product intersecting the bbox while **SCL masking
  decides contribution per pixel**, so equal catalogue counts can hide a changing platform mix over
  the support. Catalogue mix is therefore **demoted to a reported diagnostic** and no gate depends
  on platform attribution. This is sound because the D2 correction is **estimated from controls
  that experience the same acquisitions, masking and platform mix as the target support**, so it
  absorbs common-mode shift **whatever its cause** — platform, aerosol, or BRDF. Attribution would
  aid interpretation; it is not required for the guard.
- **D2.6 Test statistics — two gates, run separately per control class (r3#6/#7, r4#4/#8/#9).**
  "Small median change" is not a pass rule: a small change spatially aligned with risk can still
  move AP, and a large constant shift may not change ranking. **Both control classes produce their
  own adjusted pipeline (`veg_near`-adjusted and `veg_far`-adjusted) and the conclusion must
  survive both** — there is deliberately **no combination rule**, so no selectable mixture exists.
  1. **Label-blind feature-equivalence gate.** For every D feature × band × control class, **both**
     of these must lie inside the D2.4 margins (r4#8 — a small mean can hide a risk-aligned
     spatial tail): the **signed block-weighted mean** of cell-level `raw − adjusted` differences,
     **and** the **95th percentile of `|raw − adjusted|`** across cells. Judged on **spatial-block
     bootstrap confidence intervals**, not point estimates, with a locked familywise procedure
     across sites × bands × D features.
  2. **Post-label concordance, with "survives" defined (r4#9).** Survival means the **drift-adjusted
     hierarchical ΔAP CI independently satisfies the same positive classification as the raw CI
     under identical folds**. If **either** control class's adjustment fails to do so → `INCONCLUSIVE`.
- **D2.7 D2 NEVER excludes a site (r3#3 — resolving a contradiction in this plan).** The previous
  risks section said failing sites make the primary "narrow", implying exclusion — which would
  recreate exactly the saturation-driven attrition the restructure exists to remove, and change
  the estimand. **All frozen sites remain in the combined and frame estimates.** A site lacking
  adequate controls, or failing D2, makes the **overall headline `INCONCLUSIVE`**. The gate can
  never act as a new attrition filter.
- **D2.8 `m_*` covariates demoted to diagnostics.** Verified at `prepare.py:368–370`: each is a
  site-year **scalar broadcast to every cell**, so it cannot represent spatially varying aerosol,
  and in frame LOSO ~12 site-constant columns would be fit on 11 training sites — effectively site
  indicators. Reported, never relied on as the drift control.

**F. Matched concordance — isolate normalization, one variable at a time (r2#3, r2#4).** The
previous comparison (unnormalized/tailmass-free vs normalized/tailmass-included, potentially on
different sites) confounds **normalization × tailmass × cohort composition**. Replaced by a
**normalized/tailmass-free** pipeline compared against the **unnormalized/tailmass-free** pipeline
on **exactly the same sites, training sets, folds, tuning, and features** (a third hashed
common-site manifest). Matched concordance is **supporting evidence only** — it can neither
license a positive headline on its own nor substitute for the D2 drift gate.

**F2. Headline decision table (r2#5).** Frozen L4 assumed both arms always exist; they may not.
Prespecified:

| # | Drift gate (D2) | PIF-free CI (unnormalized, tailmass-free) | Full-C comparison (B2) | Matched concordance (F) | Headline |
|---|---|---|---|---|---|
| 1 | FAIL / insufficient controls at **any** frozen site | any | any | any | `INCONCLUSIVE` (site stays in the estimate — D2.7) |
| 2 | PASS | CI unreliable / undefined / non-evaluable | any | any | `INCONCLUSIVE` |
| 3 | PASS | CI contains zero | any | agrees, or not available | **NULL — history adds nothing beyond the tailmass-free snapshot + contagion** (reportable) |
| 3b | PASS | CI contains zero | any | **contradicts** on the identical overlap | `INCONCLUSIVE` — normalization-sensitivity finding (r4#11: frozen L4 treats *any* pipeline disagreement as inconclusive; the veto is not applied only to positives) |
| 4 | PASS | CI **excludes zero, negative** | any | agrees, or not available | **HISTORY HARMS** — reported as a finding, not folded into "null" |
| 4b | PASS | CI **excludes zero, negative** | any | **contradicts** on the identical overlap | `INCONCLUSIVE` — normalization-sensitivity finding (r4#11) |
| 5 | PASS | positive | not evaluable (overlap < locked floor) | any | `INCONCLUSIVE` (r3#9) |
| 6 | PASS | positive | positive only after tailmass removal | any | `INCONCLUSIVE` (B2) |
| 7 | PASS | positive | survives full-C | contradicts | `INCONCLUSIVE` — reported as a normalization-sensitivity finding |
| 8 | PASS | positive | survives full-C | **not available** (normalized arm absent/underpowered) | `INCONCLUSIVE` — absence of the comparison is **not** evidence of agreement (r3#10) |
| 9 | PASS | positive | survives full-C | agrees | **HISTORY ADDS VALUE**, scoped to "beyond the tailmass-free snapshot" |

Two properties are deliberate. **The gate cannot manufacture the deflationary result either**: D2
failure yields `INCONCLUSIVE` (row 1), never a null — so a broken gate cannot be read as evidence
against the hypothesis any more than for it. And **absence of evidence is never scored as
agreement** (row 8), which the previous draft's "unavailable-and-not-contradicting" wrongly did.

**F2b. Minimum evaluable overlap (r3#9, r4#10).** The B2 full-C comparison requires a locked
minimum: **sites, biome-group coverage, positive counts, and at-risk cells**. Below it the
comparison is **not evaluable** and any positive headline is `INCONCLUSIVE` (row 5). Round 4 is
right that "a locked minimum" without values leaves room to declare an inconvenient comparison
underpowered — so these values, like the D2.2 floor, are set in **U** below and are frozen
**before** any full-C result is computed.

**U. Register of quantities that must be locked before any diagnostic is inspected (r4#7, r4#10).**
Round 4 is correct that D2 still names quantities it does not fix, and that resolving them after
seeing drift output would be threshold shopping. **They are not values this plan invents by
judgement; each has a stated derivation, and none may be set after inspection:**

| Quantity | How it is fixed | Blocking? |
|---|---|---|
| D2.2 effective-block floor | power/equivalence calc on the block bootstrap | **yes** — decides whether `F4_M002.900_P0105.500` (11 far-blocks) stalls the headline |
| D2.4 pooled-margin function; excessive-dispersion multiple | validated against split-half composites | **yes** |
| D2.6 bootstrap CI level; block resampling scheme; familywise procedure; minimum bootstrap success rate | prespecified from the study's existing block-bootstrap design (L4/L13.7) | **yes** |
| D2.6 per-cell feature summary | fixed as (signed block-weighted mean, 95th pct of abs) | fixed above |
| D2.1 class-disagreement margin | same pooled reference as D2.4 | **yes** |
| F2b full-C minimum (sites, biomes, positives, at-risk cells) | power calc on the overlap | **yes** |
| D geometry `e` | measured per raster from composites on disk | free, measurable now |

**Approval should be conditional on this register being filled with derivations, not numbers
chosen to fit the census already reported in D2.2.**

**F3. Separate hashed manifests per arm (r2#10).** PIF-free and normalized arms freeze **distinct**
cohort and replacement manifests, plus a third exact common-site manifest for matched concordance.
A PIF-failing original frame site **stays in the PIF-free cohort** and is replaced **only** in the
normalized cohort; a normalized replacement's 50 km proximity to a legacy box must **not** delete
that legacy box from the PIF-free cohort.

**E. Structural temporal firewall (#1).** Screening and QC run in a process that receives Hansen
`lossyear` **already clipped to ≤2020** and never holds 2021–2024 codes. The cohort is frozen and
hashed **before** any label is attached. The QC expression was already mathematically
label-invariant; this makes it structurally so, so the claim rests on process, not on inspection.

**F. Locked replacement state machine (#4, #5).** Global round-robin per L13.4
(`amazon → congo → dry_forest → sea_peat`, rounds 1–3); each accepted candidate joins `retained`
immediately and constrains later ≥50 km decisions across all strata; a frame site failing **any**
L2 check (optical, coefficient, or PIF-in-the-normalized-arm) triggers the next queue box, and
replacement continues until 3 survive per stratum **or the queue exhausts** — never merely until
a cohort count is reached. Every rank screened, accepted, or rejected is logged with its reason.
If a replacement drops a legacy box under L13.4's 50 km rule, that is recorded as a cohort change.

**G. Survival evidence (#6).** Screen the **complete frozen candidate frame** per stratum (Hansen
only, free), not a stopping-time sample, and report finite-population survival with ≤2020
covariate distributions of retained vs non-retained boxes. Spatial-separation attrition is
reported **separately** from PIF attrition. The phrase "8% tail" is withdrawn as unsupported.

**H. Scope amendment (#7).** L13.7's generalization population is amended: the **normalized arm**
generalizes only to **PIF-feasible frontiers**, and generalization to saturated active frontiers
is **prohibited** for that arm. Retained-vs-frame ≤2020 covariate comparisons — especially block-B
strength (`b_*` contagion features) — are reported so the selection mechanism is visible rather
than described as "optical QC".

**I. Code fixes before any further downloads (#16, #17).**
- `prepare_site` emits model-consumable tables **only** when `site_qc.passed`; QC-failed sites
  write a QC artifact and nothing else.
- `risk.models` verifies every site ID against the **hashed final-cohort manifest** and refuses
  unknown or QC-failed sites.
- Synthetic end-to-end `prepare_site` tests: multiple replacements, temporal-firewall isolation,
  QC failure, rejection of failed-site tables, halo-vs-no-halo distance equivalence.
- The census/screen code is committed (not scratchpad), and emits a **hashed per-rank ledger**.

**J. Evidence publication (#15).** All validation and screening diagnostics are published,
including failures. Where an effect cannot be estimated, it is reported as **unestimated with its
diagnostics**, never silently withheld.

**K. Documentation (#18).** Append a complete, line-referenced AMENDMENT-3/4 supersession map
covering lines 235, 310, 717, 784, 800 rather than silently editing frozen sections.

**L. Sequencing and corrected cost (r4#12, r4#5).** Code fixes and tests → complete-frame screen
(free, Hansen-only) → D2.2 floor locked from power calculation → downloads → real L2 gate →
prepare → models → evaluation. `drive_sites.ps1` remains the single CDSE loop (one connection).

**The previous "~84 files / ~16 h" estimate is withdrawn as unreliable.** Two corrections:
- **No accelerator for undownloaded candidates (r4#12).** The D geometry bound is *measured* from a
  backend master raster, which new candidates do not have. Unless a conservative bound is first
  derived **and validated** from the backend grid specification, every screened-in candidate must
  be downloaded and decided by the real gate — and at dry_forest's 5% survival that is **dozens of
  full-box downloads**, not seven. Sequencing assumes **no accelerator** for new candidates until
  such a bound is validated.
- **Split-half composites for all sites (r4#5, D2.4):** required to validate the repeatability
  conversion, ≈19 sites × 3 years × 2 halves.
A defensible total cannot be stated until the complete-frame screen reports how many dry_forest
candidates must be downloaded. **Quoting a figure now would be guessing**; the plan commits to
reporting the count before the first download.

## Key decisions & tradeoffs

- **The PIF-free pipeline's real cost: no radiometric normalization in the primary.** Uncorrected
  sensor/atmosphere drift across 2018–2020 could manufacture spurious `d_*` trends and *fabricate*
  incremental signal. Round 2 established that the acquisition covariates plus L4 overlap
  concordance are **not sufficient** guards — the covariates are per-cell-broadcast site-year
  scalars (proxies, not radiometric controls) and the overlap is selected against saturation and
  may not exist. **Resolved, not deferred:** the D2 label-blind drift gate is mandatory at every
  primary site and a failure bars a positive headline (`INCONCLUSIVE`).
- **Rejected: lowering the 14 floor.** Not touched.
- **Rejected: retiring the combined analysis / elevating the frame** (r2#8, r2#9). The previous
  draft argued this from `PLAN.md:922`; that was selective — L13.8 says "Combined LOSO … Primary",
  and the floor is unreachable only for the PIF arm. Without PIF the combined cohort is viable
  (≤19 ≥ 14), so the frozen primary **runs as written**. No estimand or hierarchy change is made,
  which also removes the "choosing the analysis that survives" objection at its root.
- **Accepted: the frame may still fail.** dry_forest survives at 5%. If its queue exhausts under
  PIF + separation, the **normalized arm's** frame cannot reach 12/12 and its generalization
  analysis is not run (L13.6, unchanged). The PIF-free arm is unaffected, since it has no PIF
  requirement.
- **Accepted: Rondônia stays in the PIF-free arm only**, with `tailmass` absent.
- **Accepted: a deflationary null remains the reportable result** in either arm, and the shortened
  AMENDMENT-3 window (3 points) still biases C/D toward the null.

## Risks / open questions

1. **The D2 drift gate is the study's load-bearing assumption, and its failure mode is a stall.**
   Per D2.7 a control shortfall **never removes a site** — it makes the whole headline
   `INCONCLUSIVE`, so the gate cannot become a new attrition filter. The live risk is therefore not
   a narrowing estimand but a **study-wide stall**: if effective control support fails at even one
   frozen site, no positive headline is available at all. The D2.2 census **has now run** and both
   disjoint vegetation classes exist at 19/19 sites, with `veg_far` at `F4_M002.900_P0105.500`
   (11 blocks) binding. **But class existence is not correction coverage** (r5#1): the census has
   *not* yet shown that every evaluated target block satisfies the full D2.3 neighbourhood rule
   after the fixed cross-year clear intersection, and the 11 far-blocks can only *decrease* under
   that intersection (r5#3). This is the single most likely way the study stalls, and it is
   **unresolved**.
2. **Additive-only correction has a blind spot for multiplicative gain drift (r5#5) — UNRESOLVED.**
   D2.3 as written estimates per-band *shifts*. A year-specific multiplicative **gain** can
   fabricate `d_*_slope_std`, distort `p10`, and bend indices nonlinearly while an additive
   correction leaves `std` untouched — so raw and adjusted pipelines could **agree falsely** and
   the gate would pass drift it was built to catch. This is a concrete false-confirmation path
   that conditional approval cannot cure; the estimator must become **affine (gain + offset)**,
   with gain and offset separately equivalence-tested, before this plan is implementable.
2. **`tailmass` removal is not neutral** (B2). It weakens the static baseline, and the mitigations
   (scoped claim, full-C comparison on the PIF overlap, `INCONCLUSIVE` if positivity appears only
   after removal) all lean on an overlap that is selected against saturation and may be small or
   absent.
3. **dry_forest may exhaust** in the normalized arm (5% survival, ≥50 km separation unapplied in
   the screen). The PIF-free arm is unaffected.
4. **L13.4's 50 km rule can drop `tshopo_drc`** from the *normalized* cohort; per F3 it must not
   propagate to the PIF-free cohort.
5. **Complete-frame screening cost** is untested at frame scale (5,885 candidates × haloed reads).
6. **AMENDMENT-3 interaction stands**: 3 annual points; a null cannot cleanly separate "no signal"
   from "window too short". With B2, a *positive* is likewise scoped to a tailmass-free baseline.
7. **Two false-confirmation paths are now explicitly guarded, and both guards are new and
   untested**: PIF-attrition selection (removed by the PIF-free pipeline) and radiometric drift
   (barred by D2). Review should attack whether either guard is real or merely stated.

## Out of scope

- Any change to the 1,920 m rule, `treecover2000 ≥ 70`, the 5,000-px floor, the 4 km buffer, the
  L13.6 floors, or the frame draw.
- Re-drawing the frame, re-rolling any stratum, or replacing failed legacy sites from the frame
  queue (L13.5 forbids it).
- The reference-patch/donut arm (withdrawn, section C).
- Re-downloading 2016/2017 imagery (settled by AMENDMENT-3).
- Any use of ≥2021 data in feature construction, screening, or cohort decisions.
