---
review_provenance:
  status: deadlocked
  schema_version: 2
  rounds:
    - round: 1
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb801-5928-7271-add9-781dff680d8a
      body_sha256: e59027fdbbf5e13edc07cf70e67c35f29861001051d2f0a51496676b669b1016
      verdict: REVISE
    - round: 2
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb801-5928-7271-add9-781dff680d8a
      body_sha256: ec7dd5916162b620d4bb8fe4a369bcb0f8580bec8ce2974f7dc2b6607c6e4e93
      verdict: REVISE
    - round: 3
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb801-5928-7271-add9-781dff680d8a
      body_sha256: e9faf6ab5ebf753778a5db5305955bcedf2adf557a30daded74f1b70ab370358
      verdict: REVISE
    - round: 4
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb801-5928-7271-add9-781dff680d8a
      body_sha256: c746d75db252238bff31ab5c0feb6beef13ef3c04c6a6a2bc9d4e88cb4e16499
      verdict: REVISE
    - round: 5
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb801-5928-7271-add9-781dff680d8a
      body_sha256: 99478d926af02944d4b56cbab32d4160a0e91760f434126b9e564ac468ad8b6b
      verdict: REVISE
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan: frontier-vs-infill evaluation stratification for Specification W
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–5_

> **Amends** `ANALYSIS-DRIVER-PLAN.md` (`approved-final`, body `030d78fa`). Supersedes
> `FRONTIER-STRATIFICATION-PROPOSAL.md` (2026-07-31, not adopted).
> **Specification W is AMENDED / EXPLORATORY.** The 12-site v11 path carries the inferential claim and is
> not touched by anything here.

## Goal

Report the existing Phase E step-40 metrics **stratified by distance to prior loss**, so that performance
is resolved along the axis that the contagion features are built on, rather than pooled across it. If our
sites resemble Forest Foresight's (94 % infill), aggregate AP is an infill metric wearing a general label,
and two opposite failures are equally invisible: `contagion+static` could carry real frontier signal that a
pooled average cannot show, or a strong aggregate could be entirely infill — reproducing the known weakness
and reporting it as success.

**The claim is deliberately narrow** (round-1 #15, round-2 #2, round-4 #6). This design measures the
**incremental performance of the tuned-and-calibrated `contagion+static` PIPELINE over the fixed
`contagion` PIPELINE, within each prior-loss-distance stratum**. It is **not** utility attributable to
static features alone: step 32 excludes the contagion arm from the tuning grid and fits it once with frozen
hyperparameters, while `contagion+static` is tuned over four candidates and each arm selects its own
calibrator — so the two arms differ in **features, model selection and calibration** simultaneously, and
`ΔAP` cannot separate them. v4 still called this "utility of static drivers as a class"; that was an
overclaim. It does **not**
assert that contagion is weak or uninformative on `FRONTIER` — v2 retracted the constancy claim but left
that language standing here. `FRONTIER` means exactly one thing: **beyond the prespecified 50 px contagion
support**. The primary is a valid incremental contrast *regardless* of how strongly contagion turns out to
rank there, and §3.4 measures that strength rather than presuming it. It does **not** identify the
contribution of dated OSM roads specifically — `contagion+static` bundles roads, terrain, rivers, ecoregion
and climate, and no arm here separates them — and it does **not** compare 30 m against Forest Foresight's
400 m, since the 30/90 m contrast is a within-study aggregation change with a different estimand. Road
vintage and resolution ablations would identify those claims and are named as a follow-on, not smuggled in
here.

**No new model, no new arm, no change to training, tuning, calibration, nesting, sampling or the θ schema.**

## What round 1 refuted, and what replaced it

v1's headline was that on `FRONTIER` the contagion feature vector is **constant by construction**, so its
AP-lift is identically lift over the prevalence null. **That was wrong, verified against the repo, and is
retracted.**

- **The vector is not constant.** C1.15 makes densities *focal-excluded* with **zero denominator → `NaN`
  plus an `*_undefined` flag**. An isolated eligible pixel — no other `baseline_forest_θ` pixel in
  `disc(r)` — reads `NaN / undefined=1` where its neighbours read `0 / undefined=0`, and the pattern varies
  by radius. At 90 m, `valid_count`, `any_missing` and all-nine-undefined status vary too. **A model can
  rank on that missingness pattern.**
- **Even a constant per-site vector would not give constant macro-region scores.** Each held-out site is
  scored by a **different LOSO model and fold-specific calibrator** (plan step 37), so pooled `FRONTIER`
  scores differ by site and rank across sites regardless.
- **The terminology correction was also wrong.** `FORECAST-PLAN.md:228` freezes **`AP-lift ≡ AP /
  prevalence`** — already null-relative. v1 called the proposal's "AP-lift" misleading for using the term
  exactly as the governing schema defines it.

**What survives is weaker and empirical:** contagion is *expected* to be near-degenerate on `FRONTIER`,
because every density numerator is empty there. Whether it is, and how much ranking power the missingness
pattern retains, is **measured, not asserted** (§3.4).

## Approach

### 1. The stratifier

1.1 **`d_prior_px(T)`** = Euclidean distance transform, in **pixels**, from each focal pixel to the nearest
    pixel of **`loss_support_θ,T`** — the same θ-consistent support the contagion features already use
    (C1.15):

    `loss_support_θ,T = (datamask == 1) ∧ (treecover2000 ≥ θ) ∧ (1 ≤ loss_code ≤ T − 2000)`

    Reusing that definition verbatim makes both standing repo bug classes structurally inapplicable rather
    than merely avoided, which round 1 confirmed: the support is expressed in **raw `loss_code`**, so no
    `lossyear − 2000` formulation appears; and the stratifier is a **distance with no denominator**, so the
    identically-zero-numerator failure — which required a density over `eligible()` — cannot arise.

1.2 **A NEW, UNCENSORED transform — not the existing feature.** `dist_nearest_loss` is censored at
    `R_max = 50` px, *exactly* the `FRONTIER` boundary; reusing it yields an all-NaN stratum.

1.3 **Frozen geometry** (round-1 #7). Distances are **centre-to-centre Euclidean**; discs are **closed**
    (`d ≤ r`). Absence is `d > 50` strictly. `loss_absent_within_rmax` is therefore consistent with
    `FRONTIER` iff its censoring rule is also `d > 50`; the merge (§5) states that explicitly rather than
    leaving `≥ 50` vs `> 50` to an implementer.

1.4 **Bucket only — no continuous artifact.** With a 51 px halo, `d_prior_px > 50` is decidable for every
    core pixel, but an exact value beyond 51 px is not computable. The stratifier is consumed **solely** as
    the 3-way label; **v1's per-site decile promise is withdrawn** (round-1 #6), because deciles require
    exact frontier distances the halo cannot supply. Recovering them would need a larger halo and an
    explicitly authorised continuous artifact; neither is in scope.

1.5 **Edge exactness is a contract, not an assumption** (round-1 #8). The halo width is sufficient only if
    the surrounding conditions hold, so all of these are bound into the artifact contract and tested:
    the raw mosaic **extends ≥ 51 px beyond the site**; **tile seams are covered**; the transform runs
    **before cropping**, with core crop indices recorded; **empty support** (`prior.any() == False`) is
    handled explicitly rather than relying on SciPy's finite-array EDT boundary behaviour, which returns
    distances measured to the array edge, not to infinity.

### 2. Strata — fixed, predeclared, in pixels

| Stratum | Definition | Interpretation |
|---|---|---|
| `INFILL` | `d_prior_px ≤ 5` | adjacent to existing loss |
| `EDGE` | `5 < d_prior_px ≤ 50` | within contagion's largest disc |
| `FRONTIER` | `d_prior_px > 50` | beyond **every** contagion radius |

2.1 **These are FEATURE-SUPPORT strata, not physical-distance strata** (round-1 #9). Pixel cuts align
    exactly with contagion's grid support, which is what the strata are *for*. They are **not** physically
    comparable across sites: GFC ground size varies with latitude **and by axis**, and `risk/census/` uses
    **anisotropic** EDT sampling with separate x and y geodesic sizes — not one scalar. v1's claim that
    pixels buy physical comparability was backwards and is withdrawn. **Both the x-axis and y-axis metre
    spans of the 5 px and 50 px cuts are emitted per site** as descriptive metadata, so the physical
    ambiguity is visible rather than hidden behind a single nominal number.

2.2a **The 3×3 anchor is frozen** (round-4 #1). C2.18 defines complete nine-pixel blocks but never says
    where block `(0,0)` starts — site-core top-left, source-tile origin, or a global GFC lattice — and the
    three choices give different 90 m membership, labels and join IDs. Frozen: **`block_row =
    floor(grid_row / 3)`, `block_col = floor(grid_col / 3)`, zero-based on the **site array** defined below.**
    v5 pointed at "the site grid origin named in C3.21", but C3.21 defines only the Parquet path and never
    says whether `grid_row = 0` is the cropped site array, the source tile, or the global GFC lattice
    (round-5 #4). Frozen: `grid_row` / `grid_col` are **zero-based indices into the site's pinned GFC
    window array and its recorded transform** — the same array C1.15's features are evaluated on. **Block
    IDs are computed BEFORE core tiling**, so they do not depend on tile placement. Trailing exclusion:
    a block is excluded iff `3·block_row + 2 ≥ n_rows` or `3·block_col + 2 ≥ n_cols`. Leading partial blocks cannot occur under this anchor; **trailing partial blocks** (fewer than
    9 native pixels at the right or bottom edge) are **excluded**, consistent with C2.18's existing
    all-nine-eligible rule.

2.2 **90 m block label = the ordered MINIMUM of the nine exported categorical labels** — equivalently,
    **`FRONTIER` iff all nine native pixels are `FRONTIER`** (round-1 #10, round-2 #8). Codes are ordered
    `INFILL(0) < EDGE(1) < FRONTIER(2)`, so the minimum is well defined on the exported labels themselves.

    v2 said "minimum of `d_prior_px`", which contradicts §1.4's bucket-only export: the continuous distance
    is never emitted, so downstream code cannot take its minimum. Taking the minimum of the **labels**
    gives the identical result and is computable from what actually leaves the sandbox.

    The justification is the **frontier invariant** — this is the operator under which block-level
    `FRONTIER` means the same thing as native `FRONTIER`. It is *not* justified by analogy to the
    block-positive union rule, as v1 claimed; predictor exposure and outcome aggregation need not share an
    operator. **Partial and ineligible blocks are excluded before aggregation** (C2.18 already requires all
    nine native pixels eligible), and the merge specifies the stratum's categorical, eligibility,
    `*_undefined`, `valid_count` and `any_missing` handling together in C2.18.

2.3 **Boundaries never move**, and are frozen before any Phase E run. Empirical per-site cuts would place
    `FRONTIER` at a different feature-support distance in each site, so macro-region pooling would average
    incommensurable populations; and the `d_prior` distribution is a function of loss history, making
    post-hoc choice outcome-adjacent.

### 3. What is reported

3.1 **Metric vocabulary follows the governing schema** (round-1 #3). **`AP-lift ≡ AP / prevalence`**
    (`FORECAST-PLAN.md:228`) — a null-relative ratio, never a pairwise model contrast. An arm-versus-arm
    difference is **`ΔAP`**. v1 used "AP-lift over contagion" for a contrast; that term was already taken.

3.2 **The predeclared primary — the full estimand index is frozen** (round-2 #3, round-3 #1, #2). v3 froze
    the *statistic* but not *which* number it is: Specification W has two origins, `FRAME_GROUP_ORDER` has
    **four** macro-region groups (`risk/config.py`), and both raw and calibrated scores exist, so three
    dimensions were still free. Frozen:

    | Dimension | Primary value |
    |---|---|
    | stratum | `FRONTIER` |
    | θ | 30 |
    | scale | 30 m |
    | **origin** | **`T = 2021` (validation)** |
    | **scores** | **calibrated** — isotonic can introduce ties, so raw and calibrated AP are not identical |
    | **region** | one site-equal estimate over `J`, **conditional on the REPRESENTED groups**, whose list is emitted as part of the estimand (round-4 #4) |

    The four per-group values are reported as **secondary descriptive**, not as four primaries — otherwise
    the headline carries a fourfold multiplicity it does not declare.

    **`J` is indexed, and the primary names one member** (round-3 #2). Define
    **`J_{θ,T,scale,region,stratum}`** over the full natural-prevalence evaluation population for every
    combination §3.3 reports. The primary is exactly `J_{30, 2021, 30m, represented, FRONTIER}`.

    v4 labelled the region dimension "all", which would let six evaluable sites drawn entirely from one of
    the four groups carry a primary presented as global (round-4 #4). The represented-group list travels
    **with** the number, and §4.7 adds a coverage condition so a single-group result can never wear an
    unqualified label.

    With that index fixed:

    - **`J` = the contributing-site set** — the sites whose `FRONTIER` stratum contains **both classes in
      the ORIGINAL sample**. `J` is fixed once, from the original sample, and does **not** move between
      replicates.
    - **The estimand is therefore CONDITIONAL, and is named as such** (round-4 #5): *the site-equal mean
      `ΔAP` among original-sample two-class `FRONTIER` sites.* `J` is outcome-conditioned — it excludes
      every zero-positive, positive-only and otherwise one-class site — so the interval quantifies
      sampling variation **given `J`**, and says nothing about site-eligibility uncertainty or about the
      full 36-site frame. **Excluded sites are reported with their group and their reason for exclusion**,
      and any broader full-frame reading is explicitly prohibited.
    - **Point estimate:** `Δ̂ = |J|⁻¹ · Σ_{j∈J} ( AP_static,j − AP_contagion,j )`, both arms scored on
      **identical rows** within site *j*.
    - **Resampling:** draw **`|J|` site instances with replacement** from `J` (site is the outer level of
      the §10 hierarchical bootstrap), then resample blocks within each drawn instance as §10 already
      specifies. A site drawn twice contributes two independent within-site block draws.
    - **Undefined propagation:** if **any** drawn instance's within-site block draw yields **zero rows in
      the stratum, or fewer than two classes**, the **entire replicate is marked undefined**. v3 said only
      "one-class", leaving zero-row draws — which are neither one-class nor evaluable — undefined in the
      specification rather than in the data (round-3 #3). A site is never silently dropped and never quietly
      excluded, either of which would change the estimand mid-bootstrap.
    - **§10's stopping rule is unchanged**: the all-eligible-pixel stopping total continues to govern block
      resampling within an instance; stratification changes what is *measured*, never what is *drawn*.
    - **RNG is allocated NUMERICALLY** (round-3 #3, round-4 #2). `specification_w_rng_map.json` allocates
      analysis codes 0–6; **code `7` = "stratified evaluation block bootstrap"** is added. v4 said "a new
      analysis code" without naming it, and proposed keying the stream on a tuple of strings and a sorted
      site list — which is **not** a NumPy `SeedSequence.spawn_key`, so two implementations would hash it
      differently. v5 then routed the estimand through "the existing canonical `unit_index`
      registry", but step 28 defines only a `(θ, site, origin, scale)` mapping and supplies **no encoder or
      ordering for a variable-length site set** (round-5 #1). Frozen instead — a **new persisted key
      table**, written before any draw:

      | Element | Rule |
      |---|---|
      | field encodings | `θ`, `T` as integers; `scale ∈ {30, 90}`; `stratum ∈ {0,1,2}` per §4.3; `region` as the **sorted** tuple of represented group indices in `FRAME_GROUP_ORDER` order |
      | site-set encoding | site IDs sorted **lexicographically**, then their step-28 unit indices concatenated in that order |
      | integer assignment | sequential in first-request order, recorded in **`specification_w_stratified_keys.json`** |
      | collision rule | a repeated field tuple **must** return its existing integer; any mismatch **fails closed** |

      That integer is the spawn-key coordinate, used with the map's existing `entropy: 42` and `PCG64`.
    - The interval is the §10 percentile interval over defined replicates; the **undefined fraction is
      reported** and gates the primary (§4.6).

    `AP-lift` (`≡ AP / prevalence`) is reported alongside for each arm, per §3.3's table.

3.3 **Macro-region aggregation is frozen PER METRIC** (round-2 #5). v2 defined it only for AP. Every
    step-40 metric now names its site-level functional, its eligible-site set, its macro reduction and its
    undefined propagation:

    | Metric | Site-level | Eligible-site set (frozen from ORIGINAL sample) | Macro reduction | Replicate behaviour |
    |---|---|---|---|---|
    | **prevalence** | `π_j` in stratum | sites with ≥1 stratum row | unweighted mean over that set | undefined if any selected instance has 0 rows |
    | AP | `AP_j` in stratum | two-class sites = `J` | unweighted mean over `J` | replicate undefined |
    | AP-lift | `AP_j / π_j` | `J` | **`mean_j(AP_j / π_j)`**, never `mean(AP)/mean(π)` | replicate undefined |
    | ΔAP (primary) | `AP_static,j − AP_contagion,j` | `J` | unweighted mean over `J` | replicate undefined |
    | Brier, log-loss | site mean over stratum rows | sites with ≥1 stratum row | unweighted mean over that set | replicate undefined if a selected instance has 0 rows |
    | calibration slope/intercept | per-site fit | sites two-class **and** non-constant-score in the original sample | unweighted mean over that set | replicate undefined if a selected instance becomes one-class or constant |
    | budget recall | `Σ expected captured loss area / Σ future-loss area` in stratum | sites with **> 0 future-loss area** in stratum | **`Σ_k A_orig,j(k) · R*_j(k) / Σ_k A_orig,j(k)`** over drawn instances `k`, where `A_orig` is the **original-sample** area and `R*` the instance's **block-resampled** recall (round-4 #7) | replicate undefined if a selected instance has 0 future-loss area |

    **Prevalence was missing from v3's table** although step 40 lists it (round-3 #4), and budget recall was
    left as bare "area-weighted" — which named neither the macro formula nor whether original or resampled
    area supplies the weights. It is now a ratio of sums with **original-sample** weights, and sites with
    zero future-loss area are excluded from its site set rather than contributing an undefined recall.

    **Every metric's site set is frozen from the ORIGINAL sample, and a replicate that cannot evaluate a
    selected instance is marked undefined** (round-3 #5). v3 said "site omitted, listed" for Brier,
    log-loss and budget recall, which silently changes the macro estimand *inside* a replicate — the same
    defect the `ΔAP` rule was written to avoid, left standing in the neighbouring rows.

    **Raw rows are never pooled across sites** for any metric, because per-site LOSO models and
    fold-specific calibrators put site scores on different scales (round-1 #2). The contributing-site list
    is emitted with every macro figure.

3.4 **Contagion's ranking power on `FRONTIER` is measured — as ranking power, not dispersion**
    (round-2 #1). v2 reported `*_undefined` frequencies, distinct score counts and score variance. None of
    those measure *association with labels*, and the variance figure was additionally confounded by exactly
    the fold-specific scaling v2 had itself identified. Frozen instead, **per held-out site**, never pooled:

    - **`AP_contagion,j` and `AP-lift_contagion,j` within `FRONTIER`**, for **raw and calibrated** scores —
      this is the actual ranking-power measurement;
    - the **complete missingness signature, enumerated** (round-3 #9). At 30 m the joint pattern over
      exactly these **17** flags: `loss_density_r_undefined` and `recent_loss_density_r_undefined` for
      `r ∈ {1,3,5,10,20,50}` (12), `nbr_loss_frac_w_undefined` for `w ∈ {3,9,21}` (3),
      `loss_absent_within_rmax` (1) and `nearest_loss_age` NaN (1). v3 said "six radii and three window
      widths", which did not say whether the two density families carry separate flags — they do. At 90 m,
      the joint pattern additionally includes **`valid_count` and `any_missing` for every contagion
      predictor**, not a single block-level summary;
    - the number of distinct **calibrated** contagion scores, and separately of **raw** scores, as a
      descriptive companion — v3 did not say which.

    Site-level diagnostics are summarised across sites; raw scores are not pooled. If contagion ranks
    materially on `FRONTIER`, that is a finding about the missingness channel — the primary (§3.2) remains
    a valid incremental contrast either way (round-2 #2).

3.5 **Per-metric status is predeclared** (round-1 #5), because several step-40 metrics are undefined or
    order-dependent in a degenerate stratum:

    | Metric | Rule in a stratum |
    |---|---|
    | AP, AP-lift, ΔAP | reported when both classes present; otherwise `UNDEFINED_ONE_CLASS` |
    | Brier, log-loss | reported (defined for constant scores) |
    | calibration slope/intercept | **suppressed as `UNIDENTIFIED`** when scores are constant or one class |
    | budget recall | **exact analytic expectation over the boundary tie group** — fractional expected captured loss area, **no RNG** (round-2 #9); labelled `UNINFORMATIVE` when scores are constant |

3.6 **All other step-40 metrics are reported per stratum** alongside the existing aggregate, with
    per-stratum event counts and prevalence. Aggregate metrics remain descriptive.

3.7 **Per-stratum prevalence is itself a result**, reported as the **project-defined infill analogue**
    (round-2 #10). A `d_prior_px ≤ 5` feature-support class is **not** shown to be the same construct as
    Forest Foresight's "inside previously deforested areas" at 400 m. The external 94 % is therefore cited
    as **motivation only**, and no equality is claimed without an explicit definition crosswalk, which this
    plan does not attempt.

3.8 **Scope, matching what the approved design actually runs:**

    | θ | arms | scales | stratified metrics |
    |---|---|---|---|
    | **30** (primary) | all four | 30 m and 90 m | full step-40 set, per §3.5 |
    | 10, 25, 50, 75 | `full_without_sar` only | **30 m only** | **AP, AP-lift and budget recall only** |

    Steps 17 and 35 restrict the four sensitivity θ values to `full_without_sar` at 30 m with one frozen
    candidate, so the primary **cannot** be computed there — no `contagion+static` arm, no `contagion` to
    contrast. They are raw-probability-only, so Brier, log-loss and calibration are unavailable by the
    plan's own rule.

3.9 **The deep pilot is out of scope** — it produces no Phase E metrics to stratify.

### 4. Constraints

4.1 **Leakage safety, stated so it cannot be mis-implemented** (round-1 #13). `d_prior_px` is a function of
    `loss_support_θ,T`, which is **pre-origin by construction** (`loss_code ≤ T − 2000`). The held-out
    site's **own pre-origin loss history is REQUIRED** to compute its stratum. v1 said "never from the
    held-out site's outcomes", which an implementer could read as excluding that history — which would make
    every held-out site spuriously frontier-heavy and corrupt the primary. What is forbidden is narrower and
    exact: **`T+1` labels, and any fitted state or calibrator derived from the held-out site.**

4.2 **The stratum is a SEPARATE REPORT ARTIFACT, joined only after inference — it never enters the
    feature table** (round-2 #6). v2 proposed a loader-level allow-list to reject the column. That polices
    a hazard instead of removing it, and it polices the wrong path: `risk/models.py:54`
    (`columns_for_arm`) selects features by **prefix match** (`column.startswith(prefixes)`), so a column
    named `contagion_stratum` would be silently swept into the contagion arm; and
    `fit_predict_outer(..., extra_features=())` accepts caller-supplied extras. The approved driver
    supersedes that wrapper at step 29, so an allow-list would also be written against a path that does not
    exist yet.

    Removing the hazard instead: the stratum label is stored as its own artifact and **joined to
    predictions after inference**. No feature table ever contains it, so no naming accident and no
    `extra_features` call can make it a predictor.

    **The join is a relational contract, not a phrase** (round-3 #7). v3 said "pixel/block id", which is not
    a key. Predictions today carry `site`, `grid_row`, `grid_col`, `cohort`, `group` and
    `future_loss_pixels` (`risk/models.py:210`) but **not θ, origin or scale**, so an unqualified join is
    many-to-many and would duplicate rows — silently changing AP. Frozen:

    | Element | Contract |
    |---|---|
    | 30 m key | `(θ, origin, scale, site, grid_row, grid_col)` |
    | 90 m key | `(θ, origin, scale, site, block_row, block_col)` with **`block_row = floor(grid_row/3)`, `block_col = floor(grid_col/3)`**, zero-based on the **site grid origin** (round-4 #1) |
    | stamping | θ, origin and scale are **written into the prediction frame** at inference; the join never infers them |
    | cardinality | **many-to-one**, report side **unique** on its key — asserted, not assumed |
    | completeness | **two-sided**: prediction keys are **unique per (model, arm)** and their set is **exactly equal** to the evaluated report-key set — not merely a subset (round-4 #3) |
    | cross-arm | the **unit set is identical across arms**, so `ΔAP` contrasts the same population |
    | independence | pre-join predictions are **byte-identical** under mutation of the report artifact |
    | row preservation | prediction row count **identical** before and after the join |
    | `255` | a matched `NOT_EVALUATED` is a **hard error**: predictions exist only for evaluated pixels |

4.3 **Frozen artifact schema** (round-2 #7). "Three levels enumerated" left dtype, codes, nodata,
    filenames and validation open. Frozen:

    | Property | Value |
    |---|---|
    | dtype | **`uint8`**, plain array — **pickled / object arrays prohibited** |
    | codes | `0 = INFILL`, `1 = EDGE`, `2 = FRONTIER`, `255 = NOT_EVALUATED` |
    | ordering | `0 < 1 < 2`, which is what makes §2.2's block minimum well defined |
    | key | `(θ, site, T)`, one artifact each |
    | path | **`ml-data/deforestation-risk/report/stratum/{theta}/{origin}/{site}.stratum.v1.npy`**, with sidecar **`{site}.stratum.v1.json`** carrying θ, origin, site, shape, transform, code map, schema version, and — so §1.5's edge contract is *demonstrable* rather than merely required (round-5 #6) — the **source-grid identity and hash, core window indices, per-edge halo widths, seam-coverage evidence and empty-support status** — these literal names are bound into the supervisor allow-list |
    | validated | shape and transform equal the site's GFC grid; **eligibility consistency** — `255` iff outside `eligible_θ(T)`; **allowed-value check** rejecting any byte outside `{0,1,2,255}` |

    The supervisor validates exact names, dtype, shape and formulas, so this schema is what makes the
    artifact expressible to it at all.

4.4 **Noninterference must be origin-scoped** (round-1 #12). A combined transcript holding strata for
    several origins cannot stay byte-identical under mutation, because a `loss_code` that is future for one
    origin is valid prior history for another. **Separate per-origin predictor projections** are compared,
    each under erasure, relocation and recoding applied **strictly after that artifact's own `T`**.

4.5 **Reporting-side only.** The stratum label must not enter feature vectors, tuning, selection or
    calibration. The models are *not* blind to the stratum — `loss_absent_within_rmax` is already a
    contagion feature — which is legitimate origin-time information, and §3.4 is what quantifies its effect.

4.6 **Bootstrap.** Stratum membership is fixed per pixel **before** resampling; blocks are resampled per §10
    unchanged; per-stratum metrics are recomputed **within** each replicate, and `ΔAP` formed there (§3.2).

4.7 **Sparse-stratum gating** (round-1 #14). A pooled count does not establish that the hierarchical
    bootstrap is stable — 100 positives concentrated in one site or tile can still produce a large fraction
    of zero-positive replicates. Therefore:

    - **Hard gate on the primary — FIVE conditions, all required** (round-2 #4, round-3 #8, round-4 #4, #9):
      1. **≥ 100 positives counted ONLY over the contributing set `J`** — v2 counted them macro-region-wide,
         so positives sitting in one-class sites that cannot enter a per-site AP would have inflated the
         gate for a site-equal estimator that never sees them;
      2. **≥ 6 two-class sites in `J`**, so a site-equal mean is not carried by one or two sites;
      3. **event support**: at least **6 FRONTIER-event-supported sites** and **≥ 30 intersecting
         components in total** (round-3 #8). **`FRONTIER-event-supported site` is defined once**: a site
         `j ∈ J` with **≥ 5 distinct C2.19 components intersecting `FRONTIER`** (round-5 #3);
      4. **group coverage**: at least **two** of the four `FRAME_GROUP_ORDER` groups represented in `J`,
         each contributing **≥ 3 FRONTIER-event-supported sites** — the same defined term as condition 3,
         **not** `FORECAST-PLAN.md:224`'s "evaluable site", which means ≥ 5 components *anywhere in the test
         origin* and would let a second group qualify with almost no frontier support (round-5 #3). The
         represented-group list is emitted with the estimate and is **inseparable from every reported
         figure** (round-4 #4). Without this, six sites from a single group could carry a primary that
         reads as global. Two groups rather than four is a deliberate judgement: requiring all four would
         almost certainly suppress a sparse `FRONTIER` primary outright, and the conditional label plus the
         emitted group list is what keeps a two-group result honest;
      5. the existing **undefined-replicate gate** from `FORECAST-PLAN.md` passes.

      **Condition 3 exists because pixel counts are not event counts.** Loss is spatially contiguous, so
      6 sites × 100 positive *pixels* can be a single component per site — and if the bootstrap block spans
      each site, every replicate stays defined and conditions 1, 2 and 4 all pass on what is effectively
      **six mapped events**. Components are the ones C2.19's census already labels; they are **not
      relabelled after stratification**, which would make the gate a function of the stratum it guards.
    - **Emitted diagnostics:** the number of **sites** and **tiles** supporting positives in the stratum,
      and the realised **fraction of undefined replicates**.
    - **The per-site `< 25` rule is presentation-only.** Those sites are **flagged in display but retained
      in pooled resampling** — dropping them would silently change the estimand.
    - The counts are frozen blind before Phase E and are a judgement call of the same kind as
      `B₀ = 50 000`, not a derived quantity.

### 5. Adoption path

5.1 **A separate merged candidate is built first** (round-1 #16). v1's path was circular: it forbade editing
    the driver until the merged body was approved, while approval requires reviewing that merged body.
    Instead: assemble `ANALYSIS-DRIVER-PLAN.candidate.md` marked `in-progress`, run the chain against **its
    exact body hash**, and on approval **atomically adopt it** as the new `ANALYSIS-DRIVER-PLAN.md`.
    `030d78fa` remains the recorded approval of the body it actually covered.

5.2 **Every affected section is enumerated** — v1 claimed "exactly four places" and undercounted:

    | Section | Change |
    |---|---|
    | step 40 (metrics) | stratified axis; primary; per-metric status table (§3.5) |
    | step 41 (bootstrap) | fixed membership; replicate-wise `ΔAP`; undefined-replicate gate |
    | C1.15 (allow-list) | stratum artifact; `loss_absent_within_rmax` censoring stated as `d > 50` |
    | Phase 0.8 (transcript) | per-origin predictor projections |
    | **C2.18 (90 m)** | block stratum aggregation, and its categorical/undefined/`valid_count` rules |
    | **C3.21 (table schema)** | **an independently named report artifact — NOT a column in the feature Parquet** (round-3 #6). The feature-table schema and its hashes must be **identical whether or not the report artifact exists**, which is the testable form of §4.2's guarantee |
    | **Proof** | the stratification tests |
    | **Risks / Out of scope** | narrowed claim; follow-on ablations |
    | **Metric terminology** | `AP-lift` reserved to `AP/prevalence`; `ΔAP` introduced |
| **Phase D / step 29** | the post-inference **join contract** for the report artifact (round-2 #6) — no feature-table change, stated so the boundary is explicit |
| **step 41 (estimator)** | `J`, `Δ̂`, site-instance resampling and undefined propagation (§3.2) |
| **step 28 (RNG)** | the stratified key table and its collision rule (round-5 #2) |
| **`specification_w_rng_map.json`** | analysis code `7` added |
| **`forecast/specification_w.py:339`** | the generator that **regenerates** `analysis_codes` 0–6 as a dict literal — editing the JSON alone would be **erased on the next regeneration** (round-5 #2) |

5.3 **`ANALYSIS-DRIVER-PLAN.md` is not edited until §5.1's candidate is approved.**

## Key decisions & tradeoffs

- **The constancy claim is retracted and replaced by measurement** (§3.4) — asserting it was the error
  round 1 caught, and round 2 then showed the replacement measured dispersion rather than ranking power.
  It now measures per-site AP of the contagion arm within the stratum, raw and calibrated.
- **The stratum never enters a feature table.** A post-inference join removes the hazard that a loader
  allow-list would only have policed — and `columns_for_arm` selects by prefix, so the hazard was real.
- **`ΔAP` for arm contrasts, `AP-lift` reserved to `AP/prevalence`**, matching the governing schema.
- **Replicate-wise contrasts on identical rows**, because per-site LOSO models and calibrators put scores on
  different scales.
- **Feature-support strata, not physical-distance strata**, with both axis metre spans emitted so the
  ambiguity is visible.
- **Minimum for 90 m blocks**, justified by the frontier invariant rather than by analogy to positivity.
- **A separate merged candidate**, resolving v1's circular adoption path.
- **Narrow claim** (§Goal): a **stratified performance contrast between the tuned-and-calibrated
  `contagion+static` pipeline and the fixed, separately calibrated `contagion` pipeline** — not
  static-driver utility, not OSM datedness, not 30 m vs 400 m. v5 fixed the Goal and left this summary
  asserting attribution the design cannot support (round-5 #5).

## Risks / open questions

- **The external 94 % premise remains UNTESTED by this plan** (round-3 #10). §3.7 measures the
  *project-defined infill analogue* only; the two constructs have no crosswalk, so no comparison against
  94 % is made. v3's Risks and Proof both still implied one — the same stale-language slip the review has
  caught repeatedly.
- **`FRONTIER` may be too sparse to report**, in which case §4.6 suppresses the primary — intended
  behaviour, not failure.
- **Merging costs a full re-review** of a seven-round plan, and could surface findings in previously
  approved material.
- **The floor counts (100 / 25) are judgement calls**, frozen blind.
- **The firewall change is a schema change** (§4.2), touching the most safety-critical component.
- **The narrowed claim leaves the differentiators unidentified.** Road-vintage and resolution ablations are
  a named follow-on; until they exist, this project's distinguishing data is not shown to matter.
- **Multiplicity** remains large: three strata × four arms × two scales, plus four θ sensitivities.

## Out of scope

- Any change to the model, arms, training, tuning, calibration, nesting, sampling, or the θ schema.
- **Road-vintage and resolution ablations** — the follow-on that would identify the differentiators.
- **The 12-site v11 primary path**, `risk/models.py`, `risk/hansen.py`, `risk/labels.py`, and the
  firewall's intent.
- **The frozen Specification W artifacts — with exactly three carve-outs** (round-5 #2), which the merge
  authorises and nothing else: **step 28**, **`specification_w_rng_map.json`**, and the
  `analysis_codes` literal at **`forecast/specification_w.py:339`**. v5 froze these blanket while
  simultaneously requiring an RNG change, so the plan forbade its own prerequisite.
- Lifting the 2023 embargo; any confirmatory or headline result.
- The deep pilot, SAR arms, and the §9 architecture competition.
- Editing `ANALYSIS-DRIVER-PLAN.md` before §5.1's candidate is approved.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: `d_prior_px` over `loss_support_θ,T` in **raw
   `loss_code`**, rejecting a `lossyear − 2000` formulation; **uncensored** transform proven to differ from
   `dist_nearest_loss` beyond 50 px; **closed-disc, centre-to-centre** geometry tested at **exactly 5 px and
   exactly 50 px**, with `loss_absent_within_rmax` proven consistent at `d > 50`; prior loss **outside the
   core but inside the halo** proven to affect assignment; **empty support** proven not to inherit SciPy's
   array-edge distance; transform-before-crop and seam coverage asserted; strata proven to partition
   `eligible_θ(T)`; 90 m block label proven to equal the **minimum**, and a block proven `FRONTIER` **iff
   all nine** native pixels exceed 50 px; **contagion `*_undefined` patterns proven to VARY within
   `FRONTIER`** (the retraction of v1's claim, tested rather than asserted); stratum proven **absent from every feature table** and joined only
   after inference, with a column deliberately named to match a `columns_for_arm` prefix proven **not**
   to reach any arm; artifact proven `uint8` non-pickled with values confined to `{0,1,2,255}`, `255`
   proven to occur **iff** outside `eligible_θ(T)`, and shape/transform proven equal to the site grid; per-origin
   predictor projections proven byte-identical under erasure/relocation/recoding **after that artifact's
   `T`**; held-out site's **pre-origin history proven present** in its own stratum computation; `J` proven fixed from the original sample and stable across
   replicates; `Δ̂` proven to equal the unweighted mean over `J` of per-site AP differences on identical
   rows; a site drawn twice proven to receive **two independent** within-site block draws; a one-class
   draw proven to mark the **whole replicate undefined** rather than dropping the site; calibration coefficients proven **suppressed** under
   constant scores; budget recall proven **invariant to raster order** and **RNG-free**, via the exact analytic
   expectation over the boundary tie group; the hard gate proven to suppress the primary on **each of its five conditions
   independently** — fewer than 100 positives **within `J`**, fewer than 6 two-class sites, event support
   below 6 sites x 5 components / 30 total, fewer than 2 represented groups or a group with < 3 evaluable
   sites, and undefined-replicate failure;
   `< 25` sites proven **retained** in resampling and flagged only in display; **a zero-row stratum draw
   proven to mark the whole replicate undefined** rather than being treated as one-class; the join proven
   **many-to-one on the full stamped key**, with prediction row count **unchanged** and a matched `255`
   proven to raise; the **feature-table schema and hashes proven byte-identical whether or not the report
   artifact exists**; RNG **analysis code 7** proven allocated **by the generator at
   `forecast/specification_w.py`**, not only in the JSON, and proven to survive a regeneration; the
   stratified key table proven to return an identical integer for a repeated field tuple and to **fail
   closed** on a mismatch;
   the **event-support gate** proven to fail on 6 sites carrying one component each; the
   **group-coverage** condition proven to fail when all of `J` sits in one group, **and proven to fail on a
   second group whose sites are `FORECAST-PLAN.md` "evaluable" but not FRONTIER-event-supported**; the **block anchor** proven to be `floor(grid_row/3)` on the **site GFC window array**, computed
   **before** core tiling, with trailing exclusion proven at `3·block_row + 2 ≥ n_rows`;
   the join proven to reject a **missing** prediction row and an **arm-specific population difference**,
   with pre-join predictions proven byte-identical under report-artifact mutation; the artifact proven to live at its literal frozen path, with the sidecar proven to
   carry source-grid hash, core window, per-edge halo widths, seam evidence and empty-support status;
   90 m block label proven equal to the **ordered minimum of the nine exported labels**, and a partial or
   ineligible block proven excluded before aggregation.
2. Per-stratum event counts, prevalence, and the **project-defined infill analogue** — reported on its own
   terms, **not** compared against the external 94 %.
3. The primary: replicate-wise `ΔAP` on `J_{30, 2021, 30m, represented, FRONTIER}` using **calibrated** scores,
   with its bootstrap interval, its contributing-site list, and the four per-group values as secondary —
   or the explicit insufficient-data result naming **which** of the five gate conditions failed, with the
   represented-group list and the excluded-site table (group and reason) emitted either way.
4. §3.4's ranking-power measurements: per-site `AP` and `AP-lift` of the **contagion** arm within
   `FRONTIER`, raw and calibrated; the complete `*_undefined` signature at 30 m and `valid_count` /
   `any_missing` at 90 m; distinct-score counts as a companion. Never pooled across sites.
5. Per-site x-axis and y-axis metre spans of the 5 px and 50 px cuts.
6. The full stratified step-40 set with per-metric status, labelled **descriptive / pre-SAR** and
   **exploratory** throughout.

Josh runs the proof. Reviewer and builder claims are advisory.
