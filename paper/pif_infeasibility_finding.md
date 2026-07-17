# Pseudo-invariant feature normalization is infeasible inside active deforestation frontiers

**Status:** draft outline, 2026-07-17. Evidence is complete and reproducible; prose is not final.
**Framing:** a methodological negative result. It is not a failed study write-up — the finding is
that a widely-used normalization method has a domain where it cannot be applied, and the boundary
is measurable.

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
