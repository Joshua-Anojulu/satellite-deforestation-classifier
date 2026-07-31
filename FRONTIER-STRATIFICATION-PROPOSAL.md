# Proposal: frontier-vs-infill evaluation stratification

**Status:** PROPOSAL — not adopted. `ANALYSIS-DRIVER-PLAN.md` is `approved-final` (body `030d78fa`);
this document does not modify it. Adoption requires the grill/Codex chain and owner sign-off.

**Date:** 2026-07-31
**Motivating evidence:** Forest Foresight (WWF-NL), *Environmental Research Communications* 2026,
doi:10.1088/2515-7620/ae1f69.

---

## 1. The external finding

Forest Foresight is the leading operational deforestation-forecasting system: ResUNet, 35 predictors,
400 m resolution, 6-month lead, 17 countries. Its static driver set (elevation, slope, distance to
roads, distance to waterways, protected-area status, precipitation, temperature) is effectively our
frozen static schema.

Its authors report the following, and treat it as the system's central limitation:

- **94 %** of newly detected loss occurs inside previously deforested areas.
- Detection rate falls from **82 % near recent loss** to **7.4 % in untouched forest**.
- Alert-derived (neighbourhood/history) features **dominate** the model; environmental and
  socioeconomic drivers are marginalised.
- Named limitation: OSM road networks are used as a **static snapshot**, "missing informal, rapidly
  evolving extraction infrastructure that characterizes emerging deforestation frontiers."
- Conclusion: substantial gains require moving **beyond historical deforestation patterns**.

## 2. Why this matters to us specifically

Two facts about this project are directly responsive to that limitation:

1. We hold **36 dated OSM extracts**, i.e. time-varying road networks, not one snapshot. This is the
   exact gap the leading system names.
2. We work on the **30 m GFC grid**, ~13× finer than 400 m — the scale at which a new logging spur is
   resolvable at all.

Neither advantage is visible in an aggregate metric. That is the problem this proposal addresses.

## 3. The statistical argument

The plan already separates arms `contagion`, `contagion+static`, `optical`, `full_without_sar`
(step 30), which is the right structure for asking whether static drivers add signal beyond
neighbourhood history. But Phase E step 40 reports **only aggregate** per-site and macro-region AP,
AP-lift, Brier, log-loss, calibration slope/intercept, and budget recall.

If our sites behave like Forest Foresight's, the event population is ~94 % infill. Aggregate AP is
therefore an infill metric wearing a general label. Consequences:

- `contagion+static` can show **near-zero aggregate AP-lift** over `contagion` while carrying **large
  lift on the frontier stratum**, because the frontier stratum is a few percent of events and cannot
  move a pooled average.
- The reverse is equally undiagnosable: a strong aggregate result can be **entirely infill**, i.e. we
  reproduce the known weakness with better data and report it as success.

Both failure modes are invisible under the current reporting design, and both are avoided by
stratifying the *same* metrics rather than adding new ones.

## 4. Proposed change (reporting axis only)

Add one stratification variable and report existing Phase E metrics within strata. **No new model,
no new arm, no change to training, tuning, calibration, nesting, or the θ schema.**

### 4.1 Stratifier

For each focal pixel in `eligible_θ(T)`, define

```
d_prior(T) = euclidean distance, in metres, from the focal pixel to the nearest pixel in
             loss_support_θ,T   (prior-loss support as already defined for contagion)
```

computed by exact distance transform over the `loss_support_θ,T` mask, on the same θ baseline and the
same grid as the contagion features.

### 4.2 Strata (predeclared, fixed before any Phase E run)

| Stratum | Definition | Interpretation |
|---|---|---|
| `INFILL` | `d_prior ≤ 150 m` (≤ 5 px) | adjacent to existing loss |
| `EDGE` | `150 m < d_prior ≤ 1500 m` (≤ 50 px) | within contagion's largest disc |
| `FRONTIER` | `d_prior > 1500 m` | beyond all contagion radii |

Boundaries align with the existing contagion radii `r ∈ {1,3,5,10,20,50}` px so the strata are
interpretable against the features rather than arbitrary.

### 4.3 Reporting

For each arm, report the step-40 metric set **per stratum** alongside the existing aggregate, plus
per-stratum event counts and prevalence. `FRONTIER` AP-lift of `contagion+static` over `contagion`
is nominated as **the primary scientific quantity**; aggregate metrics remain descriptive.

## 5. Constraints this must satisfy

1. **Leakage safety.** `d_prior(T)` is a function of `loss_support_θ,T` only — data available at the
   origin. It uses no outcome from the prediction year. It must be computed inside the same sealed
   worker and LOSO fold discipline as every other feature-side quantity, and never from the held-out
   site's outcomes.
2. **θ consistency.** The distance transform runs over the θ-consistent `loss_support_θ,T`, with
   `baseline_forest_θ` semantics unchanged. Do **not** define strata over `eligible()` in any way that
   reintroduces the identically-zero-numerator class of bug logged twice in this repo.
3. **Raw lossyear codes.** Any masking used to build `loss_support_θ,T` for the transform must use raw
   codes `1..24`, never `lossyear - 2000`.
4. **Stratification is reporting-side.** It must not enter feature vectors, tuning, or selection —
   otherwise it becomes a covariate and the comparison it exists to enable is destroyed.
5. **Bootstrap.** Per-stratum uncertainty uses the existing §10 hierarchical spatial block bootstrap.
   The `FRONTIER` stratum will be sparse; if a site's `FRONTIER` event count falls below a predeclared
   floor, report it as insufficient rather than emitting an unstable interval.

## 6. Cost

Low. One `distance_transform_edt` per (site, origin, θ) over masks already materialised for contagion,
plus a `groupby` on the existing metrics path. No additional model fits, so the 29,000-pair /
~320 wall-hour envelope is unchanged.

## 7. Risk of NOT doing this

The project's differentiators — time-varying roads and 30 m resolution — are frontier-specific by
construction. Under aggregate-only reporting they are **unmeasurable**, and the most likely outcome is
a modest aggregate number that is indistinguishable from the existing literature. The contribution
would exist in the data and be absent from the results.

## 8. Open questions for review

1. Are the 150 m / 1500 m boundaries right, or should they be derived per-site from the empirical
   `d_prior` distribution? (Fixed boundaries are predeclarable; empirical ones are better matched but
   introduce a per-site degree of freedom.)
2. Should `FRONTIER` be the predeclared primary for the **exploratory Spec W arm only**, leaving the
   sealed 12-site v11 inferential claim untouched?
3. Does the sparse-stratum floor in §5.5 need to be a hard gate rather than a reporting convention?
