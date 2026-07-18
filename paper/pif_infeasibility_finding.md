# Pseudo-invariant feature normalization is infeasible inside active deforestation frontiers

> **⚠️ RETRACTED 2026-07-17 — DO NOT CITE AS WRITTEN. The central claim below is FALSE.**
> This draft argues PIF-eligible forest is absent from deforestation frontiers and elevates that to
> an identifiability obstruction (esp. §5A). It is not. PIF forest sits **0–9 km outside the 4 km
> analysis box, in the same Sentinel-2 granule** — verified in `risk/census/ingranule_annulus_census.py`
> and `annulus_granule_check.py` (commit `db60096`). The real, much narrower finding: PIF is
> unavailable *inside a 4 km-buffered box* and available immediately outside it — a **buffer-geometry
> design note**, not a property of frontiers. §5A ("identifiability obstruction", "cure is the size
> of the disease") is withdrawn; the offset/IQR numbers stand but the interpretation does not.
> This file is kept as the record of the retracted line of reasoning; rewrite around the design note
> or scrap. See PLAN-REVIEW-LOG.md (paper-review round) and CONTEXT_HANDOFF.md §11.

**Status:** RETRACTED draft, 2026-07-17. Retained for provenance, not for use.
**Framing (original, now withdrawn):** a methodological negative result about a normalization method's
domain of applicability.

---

## 1. The claim

Pseudo-invariant feature (PIF) normalization — selecting unchanged reference pixels and regressing
each year onto a reference year — is standard practice for multi-date optical change work. It
carries an unstated precondition: **the scene must contain forest that is both undisturbed and far
from disturbance.** Inside an active deforestation frontier, that population does not exist. The
precondition fails silently, because PIF returns *fewer pixels*, not an error.

This matters precisely where such studies are aimed. Frontier boxes are chosen *because* clearing
is active there; PIF requires reference forest *because* clearing is absent there. The sampling
design and the radiometric method are structurally incompatible.

## 2. Setting

19 sites (12 drawn from a pre-2021 probability frame across 4 biome strata + 7 purposive legacy
boxes), Sentinel-2 L2A over a 4 km-buffered ~28 × 24 km box per site, 2018–2020, with Hansen GFC
v1.12 for forest history. PIF population as locked: `datamask==1`, `treecover2000 ≥ 70`, no
2001–2020 loss, **≥ 1,920 m from any 2001–2020 loss pixel**, floor 5,000 native pixels.

## 3. Result 1 — the population is empty where it is needed

At Rondônia (Amazon "fishbone", the canonical frontier):

All distances below are **halo-corrected** (§5.1): the Hansen window is read ≥1,920 m beyond the
counted extent so that clearing just outside it is visible, and only interior pixels are counted.

| Quantity | Value |
|---|---|
| Intact forest pixels (no distance rule) | 506,341 |
| Median distance, intact forest → nearest 2001–2020 loss | **168 m** |
| 90th / 99th percentile | 494 m / 826 m |
| **Farthest forest pixel from any clearing** | **1,469 m** |
| Farthest *any* pixel in the buffered extent | 1,573 m |
| **PIF pixels (floor 5,000)** | **0** |

**Nothing in a ~36 × 32 km window — forest or otherwise — reaches even 1,573 m**, against a 1,920 m
criterion. Prior loss touches every edge of the extent. The failure is not marginal and not a
threshold artifact: relaxing the rule to the plan's own alternative definition (distance to 640 m
cells with ≥25% loss) still yields **0**.

Cohort-wide, under the locked criterion: **6 of 19 sites** reach the PIF floor.

## 4. Result 2 — PIF survival is strongly stratified by biome

Screened over a fixed 40-box rank-order prefix of each stratum's frozen candidate frame
(Hansen-only, no stopping rule, halo-corrected):

| Stratum | PIF survival |
|---|---|
| amazon_moist | 26/40 (65%) |
| congo_moist | 25/40 (62%) |
| sea_peat | 10/40 (25%) |
| **dry_forest** | **2/40 (5%)** |

PIF feasibility is therefore **not random with respect to the scientific population**. It removes
saturated frontiers preferentially, and it removes dry forest almost entirely — partly for a second
reason: dry forest does not carry 70% canopy. At `gran_chaco_paraguay`, `treecover2000 ≥ 70` admits
**2,783 px** against **388,917 px** at `≥ 30`. A canopy threshold imported for pseudo-invariance
silently excludes an entire biome.

**Consequence for inference.** Any frontier study that drops PIF-infeasible sites is left with a
subpopulation where prior-clearing contagion is *weaker* than in the population it means to
describe. For a study asking whether some new predictor adds information *beyond* contagion, that
attrition weakens the baseline and biases toward **confirming** the new predictor. The selection is
easy to report as neutral "optical QC"; it is not neutral.

## 5. Three traps worth documenting

**5.1 Edge inflation of distance-based masks.** A Euclidean distance transform over a windowed
raster treats the array edge as "no disturbance beyond it", so pixels near the boundary are credited
with inflated distances. Every site's PIF count fell once a ≥1,920 m Hansen halo was read around the
extent and counting was restricted to the true interior; one site (`santa_cruz_bolivia`, 5,464 →
3,367) **flipped from pass to fail**, taking the cohort from 7/19 to 6/19 and, with it, this study's
whole viability arithmetic. Any distance-thresholded mask computed on a clipped raster inherits this
bias, always in the permissive direction.

The bias concentrates in the **tail**, which is what makes it dangerous: at Rondônia the median
(168 m) and p90 (494 m) are unmoved by the halo, while the maximum forest distance falls 1,561 →
1,469 m and the extent-wide maximum falls 2,006 → 1,573 m. Summary statistics look stable; the
quantity a distance *threshold* actually depends on does not. **This paper's own first draft quoted
the uncorrected tail figures** — the error survives review precisely because the headline statistics
appear unaffected.

**5.2 A backend that sums booleans as −1.** Reducing a boolean "clear observation" mask with a sum
on the CDSE openEO backend returned **negative** counts (−16..−8 where truth was 8..16). Magnitudes
were plausible and correctly ordered, so only the rule *a count cannot be negative* caught it.
Unguarded, every site would have failed the clear-observation gate and the study would have been
declared unviable on a sign error. Wrapping the reduction in `.absolute()` is correct under both
encodings.

**5.3 The pre-2018 Sentinel-2 L2A archive is too thin for a median composite.** A pixel's clear
count cannot exceed the number of L2A products overlapping it. In the locked 2016 seasonal windows
many sites had only 2–7 products — unrecoverable by any mask or cloud threshold. Per year:
2016 → 12/19 sites viable, 2017 → 16/19, 2018–2020 → 19/19. Verification that data is *correct*
never checks that enough of it *exists*.

## 5A. The obstruction is general: every within-scene escape closes

PIF's infeasibility invites an obvious response — *use a different reference*. It does not work, and
the reason is structural rather than a failure of imagination.

**The confound.** Within one scene, a site-wide radiometric drift and a site-wide degradation
signal produce identical imagery: "the scene got 3% darker (aerosol)" and "the forest degraded 3%"
are not separable. Breaking the tie requires a subpopulation **assumed signal-free**. PIF *is* that
assumption, operationalized. §3–§4 show the assumption is unsatisfiable inside a frontier.

**The self-reference corollary, measured.** The natural escape is to standardize each cell against
its own site-year distribution, `z_it = (x_it − m_t)/IQR_t`, so per-band drift cancels. For a cell
whose raw condition never changes, `Δz_i = x_i·(1/IQR₂₀ − 1/IQR₁₈) + const` — a spurious trend
proportional to static condition, appearing whenever the site scale moves. Measured over the fixed
three-year support at all 19 sites (`risk/census/identifiability_evidence.py`):

| Index | median \|IQR change\| across sites (max) | **fabricated Δz, unchanged cell at z=+1** (median / p90) |
|---|---|---|
| **NDVI** | **17.6%** (171.9%) | **0.265 / 0.770** |
| NBR | 9.2% (41.5%) | 0.106 / 0.496 |
| NDMI | 5.7% (35.7%) | 0.114 / 0.423 |

**The trade is a wash — this is the paper's central quantitative claim.** Standardization genuinely
suppresses drift: under a +0.005 reflectance offset with ±2% differential NIR/RED gain, the NDVI
artifact falls from **0.258 to 0.033** baseline-IQR units (median, 19 sites) — an 8× reduction. But
the moving reference that achieves it fabricates **0.265 z** of trend for a cell that never changed.
**The artifact removed and the artifact introduced are the same size.** A fixed reference avoids the
fabrication but cancels no drift, because the cancellation only ever worked *because* the reference
moved with the drift.

| Reference | Cancels drift? | Fabricates history? |
|---|---|---|
| moving (site-year) | yes (0.258 → 0.033) | **yes (0.265 z)** |
| fixed (one scale) | **no** | no |
| signal-free subpopulation (PIF) | yes | no — **but does not exist in-frontier (§3–§4)** |

**Scope, stated honestly.** This is an obstruction under explicit assumptions: single-sensor optical
imagery, no external radiometric anchor, and references drawn from within the scene. It is not a
proof that the question is unanswerable. An external anchor — cross-sensor calibration, vicarious
sites — breaks it, and that is the direction we would point a successor. Note also that the
fabrication is only fabrication under an **absolute** condition estimand; under a peer-relative
estimand it is the intended signal, but that is a **different question**, and one whose answer is
driven by what a cell's neighbours did rather than by the cell's own history.

## 6. What a viable design would require

- **Do not assume PIF inside frontiers.** Establish the reference population *before* committing to
  a sampling frame; it is a property of the frame, not of the imagery.
- **A reference outside the box is not a free substitute.** It breaks the same-scene assumption PIF
  rests on (atmosphere, acquisition dates, view geometry, phenology) and its error lands on the
  features under test.
- **Prefer drift-invariant formulations.** Features expressed relative to a scene's own within-year
  distribution cancel per-band affine drift to first order and need no invariant reference.
- **Report survival by stratum.** Deterministic replacement prevents cherry-picking but does not
  prevent attrition bias.

## 7. Reproducibility

All figures here are label-blind (≤2020 inputs only), Hansen-only, and require no imagery download.
Scripts to be committed alongside this draft; census outputs and per-rank ledgers hashed. The
adversarial review that produced several of these findings is preserved in `PLAN-REVIEW-LOG.md`
(5 rounds, `AMENDMENT-4-PLAN.md`).

## 8. Honest limitations

- Survival rates come from a 40-box prefix per stratum, not the complete frame; they are
  finite-sample estimates on a prespecified prefix, and the ≥50 km separation constraint is not
  applied, so they are **upper bounds** on usable replacements.
- The PIF criterion analysed is this study's locked one (1,920 m / 70% / 5,000 px). Other studies
  use other constants; the *mechanism* generalizes, the exact rates do not.
- Rondônia's numbers are one site's; the biome gradient is the generalizable claim.
