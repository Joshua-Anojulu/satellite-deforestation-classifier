# Plan: within-site-relative reframe (candidate replacement for the risk study's radiometric design)
_Act 1 partially locked with Josh, 2026-07-17. **NOT yet reviewed by Codex — Act 2 outstanding.**_

> Status: this is a **candidate** design, not an approved one. `PLAN.md` remains frozen and
> untouched. `AMENDMENT-4-PLAN.md` (the PIF-repair attempt) is **superseded by this direction** but
> retained as the record of why. Do not implement any of this before Act 2.

## Why this exists

The risk study's radiometric design is structurally incompatible with its sampling design: PIF
needs undisturbed forest far from disturbance; the study samples inside active frontiers where that
population does not exist (Rondônia: 0 PIF pixels under every reading tried; median distance from
intact forest to nearest clearing 168 m). Five rounds of adversarial review established that every
repair route carries a defect:

- distant reference → breaks the same-scene assumption, error lands on the block under test;
- restrict to PIF-feasible sites → deletes saturated frontiers where contagion is strongest →
  biases **toward confirming** the hypothesis; dry forest survives at 5%;
- drop normalization → needs a drift gate that grew into affine estimation + coverage census +
  split-half composites, and round 5 still found a false-confirmation hole in it
  (additive-only correction is blind to multiplicative gain drift).

**The reframe dissolves rather than repairs.** Express condition features *relative to the site-year's
own forest distribution*. Then a per-band, per-year affine drift (gain + offset) — precisely what
round 5 said the additive gate could not catch — **cancels to first order**, because numerator and
denominator experience the same drift. No PIF, no reference patch, no drift gate, no PIF-driven
selection. All 19 sites, on imagery **already on disk**.

It also restores what AMENDMENT-4 had to sacrifice: `c_*_tailmass` needs only a reference median,
so a within-site reference makes it computable **everywhere**. The full C baseline returns at every
site, which **dissolves** (not mitigates) the r2#6 defect where dropping tailmass weakened the
baseline and inflated D.

## Locked in Act 1 (with Josh)

1. **Two references, prespecified primary + sensitivity** — both specified to the same standard.
2. **PRIMARY: whole fixed support.** Standardize each site-year against every eligible forest pixel
   in that site-year (at-risk cells included). Chosen because it introduces **no new constants** —
   no distance rule, no canopy threshold — so there is no retuned surface for the
   threshold-shopping charge to attach to, and it matches the fact that LOSO scores **within-site**
   ranking. Accepted cost: **blind to site-wide uniform trends** (if a whole site degrades, no cell
   is anomalous).
3. **SENSITIVITY: interior forest (`veg_far`).** `tree ≥ 30`, no 2001–2020 loss, ≥640 m from
   clearing; census-verified present at **19/19** sites. Keeps the at-risk-vs-interior contrast, so
   site-wide degradation of frontier cells stays visible.
   **Known attack, to be met head-on in Act 2:** this is arguably PIF with relaxed constants
   (640 m vs 1,920 m; 30% vs 70%). It is only defensible because (a) it is the **sensitivity, not
   the primary**, and (b) its estimand is explicitly **"condition relative to the site's interior
   forest"** — a *different claim*, not a looser version of the frozen one. If Act 2 rejects that
   framing, the sensitivity is dropped; the primary does not depend on it.
4. **Disagreement between the two is a FINDING**, reported, never resolved by preference. Agreement
   ⇒ the primary's site-wide blind spot is empirically unimportant. Disagreement ⇒ site-wide and
   within-site degradation are separable, which is itself informative.

## Recommendations on the open items (NOT yet locked — Act 1 incomplete)

- **Statistic:** robust z against the reference population — `(x − median_ref) / IQR_ref` per
  site-year, per index/band. Robust to the skew and outliers these distributions have; exactly
  affine-cancelling for bands. *Alternative considered:* percentile rank — fully invariant to any
  monotone transform (stronger), but discards magnitude and compresses tails, where degradation
  signal plausibly lives.
- **`d_*` features:** trends/deltas of the **standardized** annual summaries — i.e. change in a
  cell's *relative position* within its site's forest. Arguably a better operationalization of
  "degrading ahead of its neighbours" than the absolute version ever was.
- **Block B (contagion) stays absolute.** It is Hansen-derived and carries no optical drift;
  standardizing it would destroy the baseline the estimand is measured against.
- **Cohort:** all sites passing the non-PIF L2 checks (clear observations, nodata, out-of-range) —
  potentially 19. No PIF gate, therefore no PIF attrition.
- **L13.8 unchanged:** combined LOSO stays primary, frame-only LOSO stays the generalization
  analysis. No hierarchy change to defend (this was r2#8/#9's lesson).
- **Residual-drift check — MEASURED, and it partly falsifies the claim above.**
  `risk/census/drift_invariance_test.py` applies synthetic per-band affine drift to a real composite
  (rondonia/2020, 4.3 M support pixels) and measures the residual in the standardized index:

  | Drift | Raw index change | **Standardized residual (median / p95, z units)** |
  |---|---|---|
  | uniform gain +3% | 0.0000 | **0.0000 / 0.0000** |
  | differential gain ±2% (NIR vs RED) | 0.0065 | **0.0003 / 0.0405** |
  | **uniform offset +0.005** | 0.0243 | **0.0328 / 0.1460** |
  | combined | 0.0166 | **0.0313 / 0.1062** |

  1. **Uniform gain is a non-issue.** Normalized-difference indices are *already* exactly
     gain-invariant — `(gN − gR)/(gN + gR) = (N − R)/(N + R)` — before standardization enters. The
     round-5 objection that killed D2 ("additive correction is blind to multiplicative gain") is
     real for **bands** but does not reach the **indices** this study uses.
  2. **Differential gain is absorbed** by the site median (residual 0.0003 z).
  3. **Additive offset is NOT cancelled — the claim was wrong.** Standardization is **no better than
     raw** for offset (0.0328 vs 0.0243 median): the nonlinearity converts an additive band offset
     into a genuine index change, and dividing by IQR can amplify it. "Affine drift cancels to first
     order" holds **exactly for bands** and **fails for the offset component on indices**. A
     *year-varying* offset — atmospheric-correction error being the obvious source — injects a
     systematic per-year shift, and `d_*` features are slopes across exactly those years. That is a
     spurious-trend path in the confirming direction and it must be closed before this design is
     primary.

  **The problem is now bounded and specific**, which the D2 apparatus never was: gain is free,
  differential gain is handled, and only the **offset** component needs treatment.
  **Candidate (unproven, for Act 2 to attack):** a within-scene offset correction — subtract each
  band's low percentile computed over the **fixed support** (identical pixels all three years),
  a dark-object-subtraction variant needing no external controls, no PIF and no reference forest.
  Its own risk is that the dark tail of forest (shadow fraction) may itself change with clearing,
  which would re-import the signal being corrected; the fixed support limits but may not remove that.

## Risks / open questions

1. **The estimand changes** to *relative* condition history. This is a post-freeze re-plan and must
   be disclosed as one, not presented as execution of the frozen plan (r2#8's lesson, learned the
   hard way).
2. **Second-order drift residual on indices** is unquantified (above).
3. **The primary is blind to site-wide trends** by construction. Defensible under within-site LOSO
   scoring, but it is a real loss, and the sensitivity is the only thing that sees it.
4. **AMENDMENT-3 stands:** 3 annual points; a null still cannot separate "no signal" from "window
   too short".
5. **Standardizing against a support that includes at-risk cells** slightly dampens contrast where
   many cells are degrading — a conservative direction (toward the null), but it should be measured,
   not assumed.
6. **Unverified claim:** that within-site standardization cancels the drift AMENDMENT-4's D2 was
   built to catch. Argued analytically here; **not demonstrated empirically**. Testable on existing
   imagery.

## Out of scope

- Any change to `PLAN.md`'s locked frame, labels, cells, temporal firewall, or L13.8 hierarchy.
- Any new imagery download (the entire point: this runs on data already on disk).
- Reviving the reference-patch arm or the D2 drift gate (both superseded).

## Next step

**Act 2: Codex adversarial review**, resuming the discipline of `PLAN-REVIEW-LOG.md`. Attack first:
(a) the unquantified second-order index residual; (b) whether the `veg_far` sensitivity is relaxed
PIF wearing a new estimand; (c) whether "cancels to first order" survives contact with real data;
(d) whether the primary's site-wide blindness quietly changes what a null means.
