---
review_provenance:
  status: approved-final
  rounds:
    - round: 1
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 61e0bab6a2b1e7b95e0097dead4181f449b951502839e8b644437de44446d1ca
      verdict: REVISE
    - round: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 54f4cc6ce07aaca71f3f4b2ff4fd23c11f620a7a84119f4e3c63c44c1bb660e5
      verdict: REVISE
    - round: 3
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 26848662c9dbe7fb8f509f15d074d2f820f5d5e145ddc354d48acdc23897dd08
      verdict: REVISE
    - round: 4
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: f0d7dad6a3d21ca1bed77d5f7213c6f285ce8d2f088bbd5f27a7a95b0a02b7fa
      verdict: REVISE
    - round: 5
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 3e88e30461a5db35268fba82e60a20f736d03e7003cd6dbdec5650f9a860e8e6
      verdict: REVISE
    - round: 6
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 138ee4834f4451b18ebdf305c729dad5866a8f0381773671db9d574af7817240
      verdict: REVISE
    - round: 7
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      session: 019fa356-0b74-7682-8927-0262224a39df
      body_sha256: 030d78fa637b6eb5514649756b4c580982aae2e18359ed1234381bbd4b49f93a
      verdict: APPROVED
  historical_cross_model_review: true
  final_body_cross_model_approved: true
  final_body_sha256: 030d78fa637b6eb5514649756b4c580982aae2e18359ed1234381bbd4b49f93a
  degraded_rounds: []
  status_note: >-
    Approved by codex/gpt-5.6-sol over the hash of this exact body. Three non-blocking
    implementation notes are recorded in ANALYSIS-DRIVER-REVIEW-LOG.md rather than here,
    so that editing the body cannot break the approval binding.
---

# Plan: Specification W analysis phase — pre-SAR descriptive stage
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–4_

> **Governing documents.** `FORECAST-PLAN.md` (v11) as amended for n=4K by `FRAME-WIDENING-PLAN.md` §6.
> Counts imported from `forecast.specification_w`. Specification W is **AMENDED / EXPLORATORY**; the
> 12-site v11 path carries the inferential claim and must not be touched.

## Goal

Deliver the **pre-SAR descriptive stage** of the Specification W analysis: repair four verified defects in
the embargo firewall, acquire the missing outcome (GFC) and static layers under external checksums,
materialise per-pixel features on the GFC 30 m grid for the three frozen origins, and run the tabular
§§8/10 stack with descriptive results — stopping short of lifting the 2023 embargo, and stopping short of
any headline model selection.

**Scope is stated honestly (round-4 #13):** the frozen design has six ablation arms and two require SAR.
This stage therefore produces a complete tabular pipeline and descriptive metrics, **no headline gate, no
architecture competition, and no full deep training** — only the tiling artifact, a receptive-field
measurement and a one-site integration pilot, because full deep runs cannot be reused once SAR changes the
network's input channels.

**Premise corrections carried from review.** v1 wrongly claimed the worker implements §4 "exactly". v2 said
"frozen" about values it never gave. v3's contagion densities were identically zero (numerator over
*eligible* pixels, which by definition exclude loss ≤ T). v4 reintroduced the same emptiness through the
**year encoding**: Hansen stores **raw codes 1…24, not years**, so `lossyear − 2000` is nonsense. Each is
corrected below rather than patched.

## Approach

### Phase 0 — Firewall hardening (fixes existing committed defects)

1. **Unforgeable seal, with an explicit trust root.** `gfc_censor.py:143` admits any non-empty mapping of
   64-character strings (its test passes `{"all-frozen-artifacts": "a"*64}`). Replace with a
   content-addressed, atomically finalized, read-only artifact directory; hashes recomputed from disk
   **while the transition lock is held**; manifest bound to the **immutable git tree SHA** of the generating
   code. **Hashes and a tree SHA establish integrity, not authority**, so the trust root is stated
   explicitly and is what the seal is checked *against*: (a) an **allow-list of approved tree SHAs**,
   (b) a **complete artifact allow-list** — extra artifacts are as fatal as missing ones, and (c) a
   **worker-owned seal store** that the analysis account cannot write. A seal validating against anything
   outside these three is `EMBARGO_NOT_SEALED`.
2. **One container, one commit.** `os.replace` publishes masks at `:199` before `:214` checks the log.
   Neither `open("x")` nor a directory rename fixes it (a same-volume NTFS move **retains the source
   security descriptor**, so a container staged under the worker-only root stays unreadable, and relaxing
   its ACL first opens an exposure window). Masks **and** transition record go into **one container file**,
   published with **`ReplaceFileW`** over a pre-created placeholder carrying the final ACL.
3. **`ReplaceFileW` is not a one-state primitive, so a state table is frozen — not a "contract".** Call it
   with **flags `0`**; **ACL-ignore flags are prohibited**. **`lpBackupFileName` is frozen to a fixed path
   in the worker-owned store** (non-NULL, so backup semantics are deterministic) — the 1176/1177 path states
   depend on that argument, so leaving it unspecified leaves recovery undefined. The plan carries an
   explicit table mapping **every return code × observed (path, file ID, DACL) combination → committed or
   uncommitted → an idempotent recovery action**:

   | Return | Observed state (non-NULL backup) | Status | Recovery |
   |---|---|---|---|
   | success | destination file ID = staging ID, destination DACL = placeholder DACL; backup holds the **old destination** | **committed** | none |
   | 1175 (`ERROR_UNABLE_TO_REMOVE_REPLACED`) | destination unchanged, staging intact | uncommitted | retry from **intact staging** |
   | 1176 (`ERROR_UNABLE_TO_MOVE_REPLACEMENT`) | destination **and** staging both under their original names; the **new payload is still at staging**; backup holds the **old placeholder** | uncommitted | **retry from intact staging.** Restoring from the backup path would republish the *old placeholder* as the payload — the wrong content. |
   | 1177 (`ERROR_UNABLE_TO_MOVE_REPLACEMENT_2`) | old placeholder at the **backup path**, exposed replacement still at **staging**, **destination absent** | **exposed — must roll FORWARD** | restore the placeholder from backup, then **forward-publish the same verified staging payload**. Never rolled back, and never "quarantined": the commit is already exposed, so reversing it is not a recoverable state. |
   | any other error | classified from observed **names, file IDs and DACLs** | **fail closed** | halt, publish nothing, require manual seal re-verification |

   Two corrections from round 6 are load-bearing here. **1176 recovers from staging, not from backup** — the
   backup holds the old placeholder, so the v6 rule would have restored the wrong content. **1177 rolls
   forward, not back** — the replacement is already exposed, so treating it as reversible would improperly
   reverse a commit that has happened. The **any-other-error** row exists because the table claims
   exhaustive coverage and Microsoft documents states beyond the three named codes. Every row is tested
   under **both** account tokens. `REPLACEFILE_WRITE_THROUGH` is unsupported, so durability is step 4.
4. **Publication target and durability.** The publication directory is a **fully local, non-reparse NTFS
   path outside OneDrive** — this repo itself lives under OneDrive, whose minifilter and cloud replication
   sit outside `ReplaceFileW`'s local-NTFS guarantee. Pre/post-replacement flushing is specified; **power-loss
   durability is explicitly excluded from the guarantee** rather than silently claimed.
5. **Fault-injection postconditions match the commit point.** The `ReplaceFileW` call is the commit point:
   **neither before / both after / never exactly one**, plus restart recovery for abandoned staging
   containers and for each recovered Win32 state.
6. **Close the Job-Object escape race.** `sandbox_process.py:154` calls `Popen(...)` then `job.assign(...)`,
   leaving a window to spawn an uncontained grandchild. Launch under the dedicated token with
   **`CREATE_SUSPENDED`**, assign to a Job Object with **breakaway denied** and kill-on-close, then resume.
   Tested with an immediate grandchild-escape attempt.
7. **Real process isolation.** A **dedicated least-privilege local account** owns the raw GFC directory;
   the sealed worker runs under it, the interactive analysis account is denied. Tested both ways.
8. **Noninterference, split by artifact class and by transcript projection.** Mutating `lossyear > T`
   necessarily changes `positive_{T+1}`, so labels cannot stay byte-identical; and **recoding alone** cannot
   catch a `lossyear > 0` read. Therefore:
   - Predictor/eligibility artifacts are tested under **erasure**, **relocation** and **recoding**
     (including T+1), requiring byte-identical outputs.
   - Labels are tested against their exact target formula, never under future mutation.
   - Because `CensorTranscript` carries **one combined** name/size/hash inventory, **separate predictor and
     label transcript projections (manifests)** are defined, and only the **complete predictor projection**
     is compared during future-mutation tests.
9. **Frozen θ grid** (worker hardcodes θ=30) and **both connectivities** (`precheck_evaluability.py:56`
   hardcodes 8-conn and returns only a count): emit allow-listed masks per θ, and extract a reusable
   labelling function returning labels and component sizes for 8- and 4-connectivity.

### Phase A — Outcome layer acquisition

10. **Year encoding is fixed at the input boundary.** Hansen `lossyear` stores **raw codes**: `hansen.py:209`
    uses `loss >= 1, loss <= 20` and the worker uses `lossyear > 20`, `lossyear == 21`. Define once, at the
    boundary: **`loss_code`** = the raw byte, and **`loss_year = 2000 + loss_code`** for non-zero codes.
    **Exactly one representation is used in every formula and test**; `loss_code` is used throughout below.
11. **Derive the tile inventory from site footprints expanded by the full halo**, fail-closed if any tile is
    absent. (Computed: the 51 px halo adds no tiles here, so **21 tiles × 3 layers = 63 files** — but the
    derivation runs at runtime and fails closed rather than trusting that number.)
12. **Verify against the published MD5 first, then pin** (§F freezes a "GFC version+md5 rule"):
    download → verify each tile against the **independent published MD5** → then write the write-once
    SHA-256 inventory recording URL, release, layer, tile id, MD5, SHA-256, dimensions, transform, dtype,
    nodata, semantic ranges. `analysis_allowed = complete ∧ mode=="pinned" ∧ verified`.

### Phase B — Static drivers

13. **Acquire** roads (Geofabrik/OSM ≤ T), WDPA ≤ T, Copernicus DEM into `forecast/static_layers.py`.
    `risk/external_layers.py` is not edited.
14. **One frozen primary schema across origins** — the intersection of issue-date-valid coverage; coverage
    is an explicit feature, never NaN; region-limited layers (Asia-only PEATMAP) excluded from the primary arm.

### Phase C1 — Contagion features (inside the sealed worker)

15. **Support, defined once and used by every feature.** v3 put the numerator over *eligible* pixels, which
    excludes everything lost by T, so all densities were identically zero; v4's `lossyear − 2000` was
    nonsense on raw codes. Both are replaced by a single θ-consistent support:

    **`loss_support_θ,T = (datamask == 1) ∧ (treecover2000 ≥ θ) ∧ (1 ≤ loss_code ≤ T − 2000)`**

    - **Focal set** (where features are evaluated): `eligible_θ(T)` pixels.
    - **Denominator** for every density: `baseline_forest_θ = (datamask == 1) ∧ (treecover2000 ≥ θ)`,
      regardless of later loss.
    - **Numerator**: `loss_support_θ,T` — **explicitly intersected with the same θ baseline**, so a fraction
      can never exceed one and θ sensitivities stay internally consistent.
    - **Zero denominator** → `NaN` plus an explicit `*_undefined` `uint8` flag.

    | Feature | Definition | Parameters |
    |---|---|---|
    | `loss_density_r` | \|`loss_support_θ,T` ∩ disc(r)\| / \|`baseline_forest_θ` ∩ disc(r)\|, **focal excluded** | `r ∈ {1,3,5,10,20,50}` px |
    | `recent_loss_density_r` | as above, restricted to `T−2002 ≤ loss_code ≤ T−2000` | same `r` grid |
    | `nbr_loss_frac_w` | same ratio over a `w×w` square, **focal excluded** | `w ∈ {3,9,21}` px |
    | `dist_nearest_loss` | Euclidean distance (px) to nearest `loss_support_θ,T` pixel, censored at `R_max` | `R_max = 50` px |
    | `nearest_loss_age` | `(T − 2000) − loss_code` of that pixel; **ties → largest `loss_code`, then smallest raster index** | NaN if none within `R_max` |
    | `loss_absent_within_rmax` | `uint8` censoring flag | — |
    | `loss_trend` | OLS slope of annual `loss_support_θ,T` counts within `r = 10` px over the 5 codes `T−2004 … T−2000` | 5-year window |

    **`R_max = 50` px ⇒ halo = 51 px**; neighbourhood maths on the haloed array, cropped afterwards.
    `float32` / `NaN`; flags `uint8`. Nothing outside this table leaves the sandbox.

### Phase C2 — Grid, scales, θ, and the 90 m estimand

16. Analysis grid is the pinned GFC 30 m grid; operators named per layer.
17. **θ is a first-class schema dimension** (round-4 #3): features and eligible populations vary with θ, so
    θ appears in table paths, sampling strata, RNG keys, metrics and fit counts. **θ = 30 is primary and
    receives the full pipeline.** θ ∈ {10,25,50,75} are **full retrains**, restricted to the
    `full_without_sar` arm at 30 m with a single frozen candidate, and reported as labelled sensitivities.
    **Isolation is by artifact, not by pixel.** The eligible populations are **nested** across thresholds
    (θ=10 ⊇ θ=25 ⊇ θ=30 ⊇ …), so v5's "no pixel is ever shared across θ training sets" was impossible and
    is withdrawn. Physical pixels **may overlap** between θ datasets; what is isolated per θ is the
    **dataset, RNG stream, inclusion probabilities and weights, on-disk artifacts, and fitted model** — no
    fitted state or sampling draw is ever reused across θ.
    **θ sensitivities are raw-probability-only:** no calibrator is fitted or transferred for them (borrowing
    the θ=30 calibrator would confound the very thing the sensitivity measures), and they are therefore
    reported on **rank-based metrics only** — AP, AP-lift and budget recall — never Brier, log-loss or
    calibration slope/intercept.
18. **90 m definitions:** block in-population iff **all 9** native pixels are `eligible_θ(T)`; block positive
    iff **≥ 1** native pixel has `loss_code == T − 1999` — explicitly *probability of at least one loss in
    the block*. Continuous predictors aggregate as **mean over non-NaN**, categorical by **majority with
    ties broken by smallest category code**. Missingness is reported as **`valid_count`** and
    **`any_missing`**; **`*_undefined` is set only when all nine inputs are undefined** (v4's `any` rule made
    a block with one NaN both defined and undefined). Blocks with fewer than 9 valid native pixels excluded.
19. **Per-scale component census:** native labelling and the native two-pixel floor (≈0.18 ha; 8-conn,
    4-conn sensitivity) retained for both scales, each census computed **after restricting the native
    positive mask to that scale's evaluated support**.
20. **Shift moves predictions only.** Labels, population and block support are **held fixed**; only
    predictions shift, on **common support**; the **unshifted result is the sole dual-gate result**.

### Phase C3 — Tables and tiles

21. **Parquet per (θ, site, origin, scale)** at
    `ml-data/deforestation-risk/tables/{theta}/{scale}/{origin}/{site}.parquet`.
22. **Architecture-safe tiling.** v4's 258 px core aligned to 3×3 blocks but not to U-Net downsampling.
    Core size is a multiple of **`lcm(3, 2^depth)`**; at depth 4 that is 48, so the frozen core is
    **288 native px** (= 3 × 96 = 16 × 18), valid at both scales, with the **native-input → 90 m-output
    mapping stated explicitly**. **Halo is sized from the architecture's theoretical maximum receptive
    field**, not a measured effective field on one initialization, with a fail-closed assertion. Every pixel
    belongs to exactly one core; halos are **context-only and contribute no loss**; tiling is outcome-blind.

### Phase C4 — Sampling

23. **Training origin only** (origin 2020). Origin 2021 retained in full; origin 2022 exists pre-lift as
    **unlabeled predictors only**, with no sampling fraction created before lift.
24. **Strata are `(θ, site, origin, scale)`**; negatives drawn independently over eligible pixels (30 m) or
    complete eligible blocks (90 m); each scale targets its own pooled units.
25. **Weights.** `m_s = min(50·P_s, N⁻_s)` when `P_s > 0`; `m_s = min(B₀, N⁻_s)` when `P_s = 0` with
    **`B₀ = 50 000`**; `π_i = 1` for positives, `m_s/N⁻_s` for negatives; `w_i = 1/π_i`.
26. **Estimators frozen, and unbiased.**
    - Full-batch target: `L = (1/N_train) · Σ_{i∈sample} w_i · loss_i` with the known full-population
      `N_train`.
    - **Minibatch (deep pilot):** v4's `Σ_batch / N_train` is biased by `b/n`. The frozen reduction is
      **`(n / (b · N_train)) · Σ_{i∈batch} w_i · loss_i`** (analogously with the tile-inclusion factor for
      tile batches), with **last-batch handling, gradient accumulation, clipping and weight decay** defined.
    - **LightGBM:** raw `sample_weight` optimizes a *proportional* objective, and `min_data_in_leaf` is a
      **Hessian-based approximation, not a guaranteed row count** — v4's raw-count claim is withdrawn.
      The normalization and thresholds are given numerically rather than named:

      **Canonical weight normalization:** `w̃_i = w_i · (n_sample / Σ_j w_j)`, so `Σ w̃ = n_sample` and the
      mean canonical weight is exactly 1. All thresholds below are stated in these canonical units:

      | Parameter | Frozen value |
      |---|---|
      | `min_sum_hessian_in_leaf` | `100.0` |
      | `min_gain_to_split` | `0.0` |
      | `lambda_l1` | `0.0` |
      | `lambda_l2` | `1.0` |

      **The invariance tests follow from the normalization, which v6 got backwards.** Because
      `w̃_i = w_i · (n_sample / Σ_j w_j)`, replacing every `w_i` with `c·w_i` yields **exactly the same
      `w̃`** — the factor cancels. Therefore:

      1. **Global raw rescaling → identical normalized weights and identical models, with thresholds
         unchanged.** (v6 asserted the opposite and would have failed on a correct implementation; and
         jointly scaling the already-fixed thresholds would have *changed* the configuration rather than
         preserved it.)
      2. **Non-vacuity control = a *relative* weight perturbation** — altering the ratio between strata,
         not a global factor — which must change the model.
      3. **Joint scaling is tested separately**, only at a **normalization-bypassed LightGBM adapter
         boundary** where `w̃` is passed through without renormalization; that is the only place where
         weights and the Hessian/L1/L2 quantities must co-scale.
27. **All reported quantities computed on complete natural-prevalence populations.**
28. **New RNG analysis code** amended and serialized with a canonical `(θ, site, origin, scale)` unit-index
    mapping before any draw, with collision and order-invariance tests.

### Phase D — Tabular models (§8)

29. **Backbone:** LightGBM discrete-time hazard. Supersedes `forecast/model_path.py`; `risk/models.py`
    unmodified.
30. **Arms:** contagion, contagion+static, optical, **`full_without_sar`**. SAR and optical+SAR pending.
    **No headline gate and no architecture competition** at this stage.
31. **Frozen baselines:** prevalence null and NDVI-trend heuristic (closed-form), logistic sanity model
    (fitted), all carried through pipeline, schema, metrics and audit.
32. **Frozen outer grid and selection rule.** Candidates: `num_leaves ∈ {31,127}` × `min_data_in_leaf ∈
    {200,2000}`; fixed `lr = 0.05`, `feature_fraction = 0.8`, `bagging_fraction = 0.8`, `bagging_freq = 1`;
    max 2000 rounds, early stopping 100. **Selection metric = AP on the validation origin**, with a
    **deterministic tie-break**: smaller `num_leaves`, then larger `min_data_in_leaf`, then lowest candidate
    index.
    **The contagion arm is excluded from this grid.** The §10(a) amendment (step 34) requires the outer
    contagion baseline to be the *identical fixed algorithm* as the inner model, so tuning it over four
    candidates would contradict the amendment it depends on. Contagion is therefore fitted **once per
    (fold, scale)** with the frozen inner hyperparameters; only the three remaining arms are tuned.
33. **Calibration frozen and counted.** Candidate set **{Platt, isotonic}**, selected on the validation
    origin by **log-loss**, deterministic tie-break to Platt. Calibrators are counted as fits.
34. **§10(a) inner model — the amendment that makes the design tractable.** A fixed 500-round nuisance model
    is leakage-safe but estimates a *different* residual process than the outer tuned contagion baseline
    whose dependence is supposed to determine `L`. Resolution: **formally amend §10(a) so the contagion
    baseline used for range estimation is the identical fixed algorithm at both inner and outer levels**, so
    inner and outer target the same process. Inner hyperparameters are frozen data-independently
    (`num_leaves=31`, `min_data_in_leaf=2000`, `lr=0.05`, 500 rounds, no early stopping — early stopping
    would require a selection set). **If that amendment is rejected**, the fallback is the explicitly
    **conservative maximum-lag block size `200·g`**, which never understates dependence; per-pair inner
    selection excluding both `h` and `j` (≥10 080 inner candidate fits) does not fit the ceiling and is
    not adopted.
35. **Fit-count formula** (`S = 36`), reconciled with the §10(a) amendment:
    - Outer tuned (3 grid-tuned arms): `S × 3 arms × 4 candidates × 2 scales = 864`
    - Outer contagion (fixed algorithm, **not tuned**): `S × 1 arm × 2 scales = 72`
    - Logistic sanity: `S × 4 × 2 = 288`
    - Inner cross-fitting: `INNER_CONTAGION_FITS × 2 scales × 1 frozen candidate = 2520`
    - Calibrators: `S × 4 arms × 2 scales × 2 candidates = 576`
    - θ sensitivities (**raw-probability-only, no calibrators**): `4 θ × S × 1 arm × 1 candidate × 1 scale = 144`
    - **Tabular total = 4464 fits.**
    - **Deep: pilot only** — tiling artifact, theoretical receptive-field derivation, and
      `2 architectures × 1 site × 2 scales = 4` integration runs. Full deep training is deferred.
36. **Benchmark and ceiling.** Cold-cache benchmarks of **every fit class** (outer tuned per scale, logistic,
    inner, calibrator, θ-sensitivity) and each pilot run, plus measured **inference, evaluation, bootstrap
    and I/O** overhead; `num_threads` pinned to physical cores − 2 and recorded. An explicit execution
    schedule is produced. Projection = Σ(measured × count) + overhead, **× 1.5 safety margin**, against a
    **168 hour ceiling**. Over ceiling ⇒ **stop and re-plan**, never trim silently.

### Phase E — Evaluation (§10)

37. **Exact nesting**: per outer held-out site, all tuning and calibration use only the other sites —
    training on 2021 outcomes (origin 2020), selecting/calibrating on 2022 outcomes (origin 2021) — with the
    held-out site contributing **predictors only** at final inference.
38. **Normalization fixed per LOSO fold**; the moving-reference design stays retired.
39. **Event algorithm and dual gate** per C2.19.
40. **Metrics** on full populations: per-site and macro-region AP, prevalence, AP-lift, Brier, log-loss,
    calibration slope/intercept, area-weighted recall at 1/5/10 % budgets.
41. **Uncertainty:** §10 hierarchical spatial block bootstrap; range from a Matheron semivariogram over
    pre-calibration residuals of the amended inner/outer-consistent contagion baseline, lag bins in metres,
    on unsampled populations. Independent pixels are never resampled.
42. **Embargo holds.** All phases run pre-lift. The proof asserts a **canonical uncommitted placeholder
    state** — not path absence, since a placeholder must exist by construction.

## Key decisions & tradeoffs

- **One representation of the loss year**, fixed at the input boundary. Two separate rounds produced
  identically-zero features from encoding confusion; this removes the class of bug.
- **θ is a schema dimension**, not a footnote — otherwise sensitivities silently mix populations.
- **§10(a) amended so inner and outer use the same fixed algorithm**, with a conservative `200·g` fallback.
  The alternative (per-pair inner selection) is correct but does not fit any realistic ceiling.
- **`ReplaceFileW` with flags 0, enumerated 1175–1177 recovery, on local non-reparse NTFS outside OneDrive**,
  with power-loss durability explicitly excluded rather than claimed.
- **Deep work cut to a pilot**, because full runs cannot survive SAR changing the input channels.
- **`risk/` stays frozen**; Phase 0 only strengthens enforcement.

## Risks / open questions

- **The §10(a) amendment is load-bearing.** If a reviewer rejects both it and the `200·g` fallback, the
  design does not fit the ceiling.
- **`ReplaceFileW` behaviour must be verified empirically** on this machine, including every documented
  failure state under both tokens.
- **Published GFC MD5 availability** is assumed by the frozen rule; absent it, the plan stops rather than
  self-certifying.
- **θ retrains multiply artifacts** and could still surprise on disk footprint.
- **`B₀ = 50 000`** remains a judgement call, not a derived quantity.
- **This stage yields no confirmatory result** by construction — descriptive only until SAR lands.

## Out of scope

- **Sentinel-1 / SAR** acquisition, pilot, artifact screen and arms — separate plan, separate archive.
- **The §9 architecture competition, headline gate, and full deep training.**
- **The §4 detector/boundary audit**; **the §11 Rondônia wrapper.**
- **Lifting the 2023 embargo and producing the headline test result.**
- **Any modification to the 12-site v11 primary path, `risk/models.py`, `risk/hansen.py`, `risk/labels.py`,
  the frozen Specification W artifacts, the certified composite archive, or the firewall's intent.**
- **Re-downloading or reprocessing any optical composite.**

## Proof

From the repo root, `PYTHONPATH` set to the repo root, `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: forged-seal rejection; `ReplaceFileW` flags-0
   publication with **every state-table row — 1175, 1176 (retry from staging), 1177 (roll forward), and the
   fail-closed any-other-error row — tested under both tokens**; neither-before / both-after /
   never-exactly-one fault injection plus restart recovery; grandchild-escape against `CREATE_SUSPENDED` +
   no-breakaway job; worker-succeeds / analysis-denied isolation; erasure/relocation/recoding
   noninterference on the **predictor transcript projection** with labels tested by exact formula; θ grid;
   both connectivities; halo-expanded fail-closed tile derivation; **`loss_code` boundary conversion**; the
   corrected θ-consistent contagion features with zero-denominator and tie rules; per-scale strata; the
   **unbiased minibatch reduction**; LightGBM **global-rescaling invariance under unchanged thresholds**,
   the **relative-perturbation non-vacuity control**, and joint scaling at the normalization-bypassed
   adapter boundary; zero-positive strata; RNG code
   allocation and order-invariance; `lcm(3, 2^depth)` tiling with halo ≥ theoretical receptive field; LOSO
   nesting; the bootstrap.
2. GFC verification report: 63/63 files, MD5-verified against the published list, all issue counts 0,
   `mode: "pinned"`, `verified: true`.
3. Phase D36 benchmark artifact: per-fit-class and per-pilot measurements, overhead, execution schedule, and
   the ×1.5-margined projection against the 168 h ceiling.
4. Predictions + audit for the **train and validation origins**, stamped with `RESULT_NAMESPACE`, metrics on
   full natural-prevalence populations, all results labelled **descriptive / pre-SAR**.
5. The canonical **uncommitted placeholder state**, asserted by test.

Josh runs the proof. Reviewer and builder claims are advisory.
