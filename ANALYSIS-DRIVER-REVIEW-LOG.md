# Analysis-Driver Plan — Review Log

**Task.** Specification W analysis phase: acquire the missing outcome (GFC) and static layers under the
existing pinning discipline, materialise a per-pixel feature table on the GFC 30 m grid for the three
frozen origins, and implement the §§8/9/10 model and evaluation stack — stopping short of lifting the
2023 embargo.

**Plan file.** `ANALYSIS-DRIVER-PLAN.md`
**Governing documents.** `FORECAST-PLAN.md` (v11) as amended by `FRAME-WIDENING-PLAN.md` §6.

## Resolved caps

| Var | Value |
|---|---|
| `MAX_ROUNDS` | 5 |
| `MAX_ATTEMPTS` | 8 |
| `PLAN_FILE` | `ANALYSIS-DRIVER-PLAN.md` |
| `LOG_FILE` | `ANALYSIS-DRIVER-REVIEW-LOG.md` |
| reviewer | `codex` — codex-cli 0.145.0, gpt-5.6-sol, reasoning xhigh |

Canary (read-only smoke test, run in the target repo before Round 1): Codex attempted a shell write of
`CANARY_PROBE.txt` at the repo root and reported "Write was denied by sandbox policy." No file was
created and `git status --porcelain` was unchanged. Note: this box's `~/.codex/config.toml` defaults to
`sandbox_mode = "danger-full-access"` + `approval_policy = "never"`, so `-s read-only` (round 1) and
`-c sandbox_mode="read-only"` (every resume) are mandatory, not stylistic.

## Act 1 — Grill summary (Claude ↔ Josh)

State established by exploration before any question was asked:

- The clearobs gate fix (`f529fc5`) is in place and the Specification W optical archive is **certified** —
  720/720 TIFFs, all issue counts 0, `mode: "pinned"`, `verified: true`, `analysis_allowed: true`.
- The suite was **not** green as the handoff claimed. `test_gfc_censoring.py` had 3 failures from a
  timeout-budget race (0.1 s budget vs ~0.20 s interpreter startup on this box). Fixed and committed
  separately as `a50b261`; `forecast/tests` is now 60 passed.
- `PROCESSED_DIR` does not exist and there are **zero** Specification W outputs on disk.
- `HANSEN_DIR` does not exist — **the GFC outcome layer is entirely absent** from the box.
- `risk/download_timeseries.py` has **no Sentinel-1 support**; the only S1 trace is `"sar_pilot_sites": 3`
  in the W manifest.
- Missing §3 static drivers: roads (OSM ≤T), WDPA ≤T, Copernicus DEM. Present: HydroBASINS, Ecoregions2017,
  PEATMAP (Asia), CHIRPS.
- `forecast/gfc_censor_worker.py` **already implements §4 exactly** at pixel level for T ∈ {2020,2021,2022}
  with the pre-lift/post-lift embargo split — so the label builder does not need writing.
- `risk/models.py:run_loso` is the **retired** study's cell-level runner (arms `S/B/C/D`, `grid_row`/
  `grid_col`/`future_loss_pixels` outputs, no temporal nesting); `forecast/model_path.py` wraps it.
- Sizing: ~880 k GFC-30 m pixels per site → ~31.7 M rows per origin, ~95 M across three origins at 30 m.
  RAM 31.7 GB, disk free 273 GB, GPU RTX 4060 Laptop 8188 MiB (matches §9's 8 GB assumption).
- 21 distinct GFC 10° tiles × 3 layers = 63 files required.

Decisions locked with Josh:

| # | Decision |
|---|---|
| 1 | Label/population logic is **reused** from `gfc_censor_worker.py`, not rewritten. `risk/` stays frozen. |
| 2 | Scope = the full §§4/8/9/10 stack (less the deferrals below). |
| 3 | Counts are **imported** from `forecast.specification_w`, not restated; `FRAME-WIDENING` §6 wins on conflicts. |
| 4 | Compute: prespecified negative subsampling, **1:50**, all positives kept, fixed per-fold seed, log-offset intercept correction. |
| 5 | SAR/§7 → **separate plan**, with a **separate S1 archive and its own gate**; the sealed optical archive is never re-opened. SAR arms reported pending. |
| 6 | GFC tiles → **in-plan acquisition + verification gate**, pinned to `GFC-2024-v1.12`, write-once inventory, role-gated. |
| 7 | Static layers → acquire all three (OSM ≤T, WDPA ≤T, Copernicus DEM). |
| 8 | §4 detector/boundary audit → **deferred** to its own plan. |
| 9 | Feature tables → **parquet per (site, origin, scale)** outside the repo; 216 files. |
| 10 | §11 Rondônia case study → **deferred**. |
| 11 | Proof = `pytest forecast/tests` green + a certified GFC verification report + train/validation-origin predictions and audit, with the 2023 embargo still sealed. |

---

## Round 1 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df
- reviewed body_sha256: 61e0bab6a2b1e7b95e0097dead4181f449b951502839e8b644437de44446d1ca
- verdict: REVISE (8 blockers, 5 high, 2 medium)

### Critique (verbatim)

Material problems remain.

1. **Blocker: the negative-subsampling correction is overstated.** A logit correction is exact only when inclusion rates are known and outcome-conditional; with negative fraction \(q\), `logit(p_population) = logit(p_sample) + log(q)`. Here \(q\) varies by site-origin, so one intercept correction is insufficient, and correcting predictions does not correct AP, prevalence, AP-lift, budget recall, Brier, log-loss, calibration regressions, or variograms computed on sampled rows. This also conflicts with the frozen natural-prevalence calibration requirement. [ANALYSIS-DRIVER-PLAN.md:83](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:83>) [FORECAST-PLAN.md:296](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:296>)  
   **Fix:** Subsample training rows only, fit with inverse-inclusion weights, compute normalization/calibration/metrics/residual fields on complete natural-prevalence populations, and freeze the exact correction formula and weight composition.

2. **Blocker: “per site-origin” sampling leaks the test outcome or is impossible pre-lift.** Drawing 50 negatives per positive for origin 2022 requires `positive_2023`, despite the claimed embargo. [ANALYSIS-DRIVER-PLAN.md:83](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:83>) [ANALYSIS-DRIVER-PLAN.md:126](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:126>)  
   **Fix:** Sample only origin-2020 training data; retain full origin-2021 validation data and full unlabeled origin-2022 scoring data, with no 2022 sampling fraction created before lift.

3. **Blocker: the existing censor masks cannot produce the required contagion features.** The worker emits only eligibility and positive booleans, while §8 needs temporally truncated loss-density, distance, neighbour-fraction, and trend fields; computing those outside the worker would require forbidden raw `lossyear` access. [gfc_censor_worker.py:23](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor_worker.py:23>) [gfc_censor_worker.py:224](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor_worker.py:224>) [ANALYSIS-DRIVER-PLAN.md:74](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:74>)  
   **Fix:** Extend the sealed worker to emit only prespecified, per-origin features derived from `lossyear<=T`, using a frozen maximum-radius halo plus one pixel and cropping only after all neighbourhood calculations.

4. **High: the claim that the worker implements §4 “exactly” is false.** It hardcodes θ=30, so the frozen θ∈{10,25,50,75}% sensitivities cannot run; the reused component helper also hardcodes 8-connectivity, returns only a count, and cannot perform the required 4-connectivity sensitivity. [FORECAST-PLAN.md:70](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:70>) [gfc_censor_worker.py:22](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor_worker.py:22>) [precheck_evaluability.py:56](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/precheck_evaluability.py:56>)  
   **Fix:** Add allow-listed masks for every frozen θ and a reusable component-label function supporting both frozen connectivities without exposing raw loss years.

5. **Blocker: the new analysis commands are outside the technical embargo boundary.** `PRE_LIFT_ROLES` contains no feature-building, model-fitting, or evaluation role, so “all GFC reads go through the firewall” is merely a coding convention for the planned entry points. [prelift_sandbox.py:15](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/prelift_sandbox.py:15>) [ANALYSIS-DRIVER-PLAN.md:126](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:126>)  
   **Fix:** Add mandatory roles for every pre-lift entry point and enforce raw-GFC denial with OS filesystem permissions or a separate restricted account, not solely Python audit hooks.

6. **Blocker: the post-lift seal can be forged.** `run_censoring` checks only that a nonempty mapping contains 64-character strings; the test demonstrates that `"a"*64` is accepted without any artifact existing or matching. [gfc_censor.py:143](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:143>) [test_gfc_censoring.py:200](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/tests/test_gfc_censoring.py:200>)  
   **Fix:** Require a committed allow-listed seal manifest and recompute every required artifact hash, namespace, configuration, and code revision before permitting post-lift execution.

7. **Blocker: the transition log is neither atomic nor truly write-once.** Post-lift masks are published before the log existence check, and `write_text` follows a racy check-then-write; a crash or concurrent call can expose `positive_2023` while leaving the log absent or overwritten. [gfc_censor.py:194](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:194>) [gfc_censor.py:214](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:214>)  
   **Fix:** Acquire an exclusive transition record with `open("x")` before generating post-lift output and atomically commit the log and handoff under one lock, with failure leaving neither published.

8. **Blocker: the 90 m estimand remains undefined and conflicts with the event rule.** “Any positive” changes the target from per-pixel loss to probability of at least one loss in a block, while a two-pixel component becomes ~1.62 ha rather than ~0.18 ha; one-pixel tolerance also means 30 m at one scale and 90 m at the other, and choosing the best shift using 2023 would leak test labels. [ANALYSIS-DRIVER-PLAN.md:166](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:166>) [FORECAST-PLAN.md:52](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:52>)  
   **Fix:** Freeze the 90 m eligibility, label, predictor, edge-block, component-area and metric estimands, express tolerance in metres, and report every prespecified shift as sensitivity rather than maximizing over test results.

9. **Blocker: the fit budget is not credibly tractable.** The frozen 1,260 inner fits at roughly \(8M×34/36\) rows imply about 9.5 billion 30 m row-fit exposures before hyperparameter candidates, arms, the 90 m scale, outer fits, or up to 72 deep runs. [specification_w.py:41](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/specification_w.py:41>) [ANALYSIS-DRIVER-PLAN.md:164](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:164>)  
   **Fix:** Freeze candidate grids, boosting/early-stopping budgets and total fit counts, benchmark representative 30 m and deep fits, set a wall-clock/resource ceiling, and stop-and-replan if the projection exceeds it.

10. **High: a flat sampled Parquet table is not a U-Net dataset.** The plan does not define predictor-only patch coordinates, halos, overlap, eligibility/loss masks, fold normalization, full-raster inference, or how sampled loss preserves spatial context; therefore the deep budget and receptive-field-dependent bootstrap cannot be implemented reproducibly. [ANALYSIS-DRIVER-PLAN.md:78](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:78>) [ANALYSIS-DRIVER-PLAN.md:161](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:161>)  
    **Fix:** Specify a separate grid-aligned tensor/tiling artifact with outcome-blind tiling, full context, inverse-probability loss masks, deterministic mosaicking, and a measured receptive field.

11. **High: three frozen baselines are omitted.** The plan implements four modality arms but not the required prevalence null, NDVI-trend heuristic, or logistic sanity model. [ANALYSIS-DRIVER-PLAN.md:97](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:97>) [FORECAST-PLAN.md:198](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:198>)  
    **Fix:** Add all three frozen baselines to the nested pipeline, prediction schema, metric suite, and audit artifacts.

12. **High: the GFC inventory bootstraps trust from the bytes it is supposed to authenticate.** A locally generated write-once SHA inventory can permanently pin a corrupt or substituted first download, while the governing design explicitly freezes a GFC version-plus-MD5 rule. [ANALYSIS-DRIVER-PLAN.md:40](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:40>) [FORECAST-PLAN.md:19](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:19>) [_inventory_gate.py:83](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/census/_inventory_gate.py:83>)  
    **Fix:** Verify every tile against an independent published MD5 before creating the SHA-256 inventory and record URL, release, layer, tile ID, MD5, SHA-256, dimensions, transform, dtype, nodata and semantic ranges.

13. **High: zero-positive site-origins disappear under “50 negatives per positive.”** A quiet training site receives zero rows, breaking site-balanced training and making its inclusion probability/offset undefined. [ANALYSIS-DRIVER-PLAN.md:83](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:83>)  
    **Fix:** Freeze an outcome-independent negative budget for zero-positive strata and census all negatives when below that budget, recording nonzero inclusion probabilities for every retained stratum.

14. **Medium: negative sampling has no RNG namespace.** Frozen analysis codes stop at 6 and the committed fold table allocates only those codes, so “derive from the stream scheme” either collides with an existing analysis or invents an unrecorded protocol change. [FORECAST-PLAN.md:170](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:170>) [specification_w.py:218](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/specification_w.py:218>)  
    **Fix:** Amend and serialize a new sampling analysis code plus canonical site-origin-scale unit-index mapping before any draw, with collision and order-invariance tests.

15. **Medium: the static-feature schema can change by origin.** Per-origin exclusion permits a layer to be present in training but missing in validation/test, encoding time through missingness; Asia-only peat also conflates “no peat” with “no coverage.” [ANALYSIS-DRIVER-PLAN.md:53](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:53>) [ANALYSIS-DRIVER-PLAN.md:158](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:158>)  
    **Fix:** Freeze one primary feature schema as the intersection of issue-date-valid coverage across all origins, represent source coverage explicitly, and exclude region-limited layers from the primary arm unless absence has a valid global meaning.

VERDICT: REVISE
### Claude's response (round 1)

**All 15 findings accepted; none rejected.** Four code-specific claims were independently verified before
acceptance rather than taken on trust:

- **#6 confirmed.** `gfc_censor.py:143-147` validates only `if not name or len(str(digest)) != 64` — no
  artifact is opened and no hash is compared. `test_gfc_censoring.py:200` passes `{"all-frozen-artifacts":
  "a"*64}` and it is admitted. The seal is forgeable.
- **#7 confirmed.** `os.replace(publish_dir, destination)` at `:199` publishes post-lift masks, and only
  afterwards does `:214` check `log_path.exists()` and `write_text`. Masks are published before the log
  exists, and the check-then-write is racy.
- **#12 confirmed.** `FORECAST-PLAN.md` §F lists "GFC version+md5 rule" among the frozen items, so a
  self-generated SHA inventory alone does contradict a frozen rule.
- **#14 confirmed.** `specification_w.py:218-224` allocates `code_0`, `code_1..5`, `code_6` — no code is
  free for a sampling draw, so one must be formally amended in.

**Correction carried into the plan.** v1 asserted `gfc_censor_worker.py` implements §4 "exactly". That was
wrong (finding #4): it implements the θ=30 default only. The premise is corrected in the revised Goal
rather than quietly patched.

**Changes made:**

| Finding | Change |
|---|---|
| 6, 7, 4(θ), 4(conn), 5 | New **Phase 0 — firewall hardening**: unforgeable seal manifest with recomputed hashes; `open("x")` transition record acquired *before* any post-lift output, published under one lock; allow-listed θ grid; reusable both-connectivity component labelling; mandatory roles for every new pre-lift entry point backed by OS-level (ACL) denial of raw GFC, not Python checks alone. |
| 1, 18 | Single log-offset replaced by **inverse-inclusion weights** in the loss; all reported quantities — normalization, calibration, metrics, residual field — computed on **complete natural-prevalence populations**. Resolves the §F natural-prevalence-calibration conflict. |
| 2 | Sampling restricted to the **training origin (2020)** only; validation origin retained in full; test origin exists pre-lift as unlabeled predictors with **no sampling fraction created before lift**. Closes the `positive_2023` leak. |
| 3 | Contagion/hazard features **moved inside the sealed worker**, computed over a frozen max-radius+1 halo and cropped only after all neighbourhood maths. |
| 8 | 90 m declared a **distinct estimand** (block-level "at least one loss", ~1.62 ha minimum component), reported alongside 30 m and never averaged; tolerance expressed in metres; every shift a prespecified sensitivity, never maximized over test outcomes. |
| 9 | Frozen candidate grid, boosting/early-stopping budgets and total fit count; **representative 30 m and deep benchmarks**; projected wall-clock against a stated ceiling with an explicit **stop-and-replan**. |
| 10 | Separate **grid-aligned tiling artifact** for the deep head: outcome-blind tiling, full context/halos, explicit masks, per-fold normalization, deterministic mosaicking, measured receptive field. |
| 11 | **Prevalence null, NDVI-trend heuristic and logistic sanity model** added to the pipeline, schema, metrics and audit. |
| 12 | Order changed to download → **verify against published MD5** → then create the SHA-256 inventory; record extended to URL, release, layer, tile id, MD5, SHA-256, dimensions, transform, dtype, nodata, semantic ranges. |
| 13 | **Outcome-independent negative budget** for zero-positive strata, censusing below the budget, so every retained stratum has a recorded non-zero inclusion probability. |
| 14 | New **sampling analysis code** formally amended and serialized with a canonical (site, origin, scale) unit-index mapping before any draw, plus collision and order-invariance tests. |
| 15 | **One frozen primary schema** = intersection of issue-date-valid coverage across origins; coverage represented explicitly; region-limited layers (Asia-only PEATMAP) excluded from the primary arm so "no peat" never shares an encoding with "not surveyed". |

**Nothing rejected.** Two findings (#6, #7) are defects in already-committed code rather than in the plan;
they are pulled into scope because the study's integrity claim rests on them.


## Round 2 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: 54f4cc6ce07aaca71f3f4b2ff4fd23c11f620a7a84119f4e3c63c44c1bb660e5
- verdict: REVISE (4 blockers, 6 high)

### Critique (verbatim)

The revision fixes several round-1 defects conceptually, but material implementation blockers remain.

1. **Blocker: the proposed transition is still not atomic.** `open("x")` immediately creates a durable record, so a crash can leave the record without output; conversely, a lock cannot atomically commit a log and handoff at two filesystem paths. “On any failure neither is left published” is incompatible with the described write-once sequence. [ANALYSIS-DRIVER-PLAN.md:49](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:49>)  
   **Fix:** Use a separate exclusive lock, stage the completed handoff and transition record together under the ACL-denied root, expose both with one same-volume directory rename, and fault-inject every durable boundary.

2. **Blocker: `icacls` alone cannot distinguish the worker from analysis code.** Current children inherit the parent’s Windows token, so if the sealed worker can read the raw directory, another child under the same account can too; the plan acknowledges this uncertainty but still claims OS enforcement. [ANALYSIS-DRIVER-PLAN.md:62](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:62>) [sandbox_process.py:154](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/sandbox_process.py:154>)  
   **Fix:** Run acquisition and censoring through a dedicated least-privilege account/service token, deny the interactive analysis account, and integration-test both worker success and analysis-process denial.

3. **Blocker: the widened censor lacks a semantic noninterference contract.** An output allow-list cannot catch an implementation that accidentally uses `lossyear>0` instead of `0<lossyear<=T`; the proof adds a generic feature-table test but not the necessary future-year invariance test. [ANALYSIS-DRIVER-PLAN.md:101](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:101>) [ANALYSIS-DRIVER-PLAN.md:254](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:254>)  
   **Fix:** Add a triangular noninterference test that arbitrarily mutates every `lossyear>T` value and requires byte-identical origin-T outputs, metadata, hashes, sizes, and transcripts.

4. **High: the contagion contract is still described as “prespecified” without being specified.** No radii, recent-loss windows, trend formula, distance censoring, no-nearby-loss encoding, dtype, nodata rule, or numeric maximum radius exists, so the worker’s allowable information release cannot yet be reviewed or implemented. [ANALYSIS-DRIVER-PLAN.md:101](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:101>)  
   **Fix:** Enumerate every feature formula and numeric parameter now, including boundary and no-event behavior, and derive the halo from those committed values.

5. **Blocker: the 90 m estimand is announced, not defined, and its dual gate conflicts with the frozen design.** Lines 112–118 promise later declarations rather than giving formulas, while Phase E still says “≥2 px”; at 90 m that means ~1.62 ha, but the frozen gate defines native mapped components ≥2 GFC pixels, ~0.18 ha. [ANALYSIS-DRIVER-PLAN.md:112](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:112>) [ANALYSIS-DRIVER-PLAN.md:191](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:191>) [FORECAST-PLAN.md:222](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:222>)  
   **Fix:** State the exact 90 m formulas and retain one native-30 m event census for both scales, applying only the AP-lift CI arm separately at each scale; also freeze the shift distance and offset set numerically.

6. **High: training-only sampling is temporally coherent, but the weighting objective remains undefined.** Origin-2020 sampling plus full origin-2021 calibration is valid in principle, yet the plan claims the “exact weight composition” is frozen while stating only `1/π_i`; it also implies site-balanced training without defining whether weights target pooled pixels, site-equal risk, or class balance. [ANALYSIS-DRIVER-PLAN.md:136](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:136>)  
   **Fix:** Freeze \(m_s\), \(\pi_s\), the zero-positive budget, weight normalization and target measure explicitly, and require each fold loader to open only its training-site sampling partitions and metadata.

7. **High: inverse-probability masks are underdefined for overlapping U-Net tiles.** If halo pixels contribute loss repeatedly, inclusion weights no longer recover the population objective; if halos are context-only, that ownership rule is missing. Sampling negative loss locations also does not reduce convolutional forward-pass cost when every outcome-blind tile must still run. [ANALYSIS-DRIVER-PLAN.md:122](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:122>) [ANALYSIS-DRIVER-PLAN.md:172](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:172>)  
   **Fix:** Assign every pixel to exactly one non-overlapping loss core, treat overlap/halos as context-only, reuse the same sampled-pixel mask across overlaps, and budget deep compute as full-tile compute.

8. **High: the deep-head scale accounting is contradictory.** Two architectures × 36 folds equals the stated 72 runs for one scale, not both; separate 90 m training requires 144 runs, while aggregating 30 m predictions needs a defined block-probability score and undermines the claim that 90 m is independently modeled. [ANALYSIS-DRIVER-PLAN.md:168](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:168>) [ANALYSIS-DRIVER-PLAN.md:174](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:174>)  
   **Fix:** Declare the deep headline scale explicitly and either train separate 90 m heads with 144-run accounting or freeze a mathematically defined aggregation of 30 m scores and label it as such.

9. **High: seal verification still has a time-of-check/time-of-use race.** Recomputing hashes proves the artifacts only at that instant; nothing prevents mutation before transition publication, and the required artifact set and code-revision semantics remain unspecified. [ANALYSIS-DRIVER-PLAN.md:44](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:44>)  
   **Fix:** Seal an atomically finalized, read-only/content-addressed artifact directory, verify it while holding the transition lock, and bind the manifest to the immutable generating tree SHA rather than mutable paths.

10. **High: the compute fix still defers every binding value.** The current plan contains no candidate grid, fit-count derivation, benchmark protocol, or wall-clock ceiling; saying these will later be “recorded in the plan” does not make the current plan executable or frozen. [ANALYSIS-DRIVER-PLAN.md:174](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:174>)  
    **Fix:** Add the numeric grids, thread/device assumptions, cold-cache benchmark procedure, total fit formula and ceiling now, or end the current plan at a formal benchmark amendment gate before committing to Phases D/E.

VERDICT: REVISE
### Claude's response (round 2)

**All 10 findings accepted; none rejected.** The central criticism — that v2 said "frozen" and
"prespecified" about values it never gave — was correct and is the main driver of v3. Three findings
turned on choices belonging to Josh rather than to Claude, and were put to him before revising:

- **Compute ceiling** → **168 hours (1 week)** of wall-clock, with stop-and-replan if the benchmark
  projects over it.
- **Deep headline scale** → **both scales trained independently, 144 runs**, preserving a genuine
  distinct estimand at 90 m rather than aggregating 30 m scores.
- **Raw-GFC isolation** → **dedicated least-privilege local account**, accepting the one-time machine
  change, rather than weakening the enforcement claim.

| Finding | Change |
|---|---|
| 1 | `open("x")` replaced by: separate exclusive lock, handoff **and** transition record staged together under the ACL-denied root, exposed by **one same-volume directory rename** (the actual atomic primitive), with fault injection at every durable boundary asserting neither is published on crash. |
| 2 | `icacls` downgraded from mechanism to speed bump; **dedicated least-privilege local account** owns the raw GFC directory, worker runs under it, interactive account denied, integration-tested both ways. |
| 3 | Added the **triangular noninterference test**: arbitrarily mutate every `lossyear > T` value, require byte-identical origin-T outputs, metadata, hashes, sizes and transcripts. This is what bounds *what the worker can depend on*, as opposed to what it emits. |
| 4 | Contagion contract **enumerated as a table**: `loss_density_r` and `recent_loss_density_r` at `r ∈ {1,3,5,10,20,50}` px, `nbr_loss_frac_w` at `w ∈ {3,9,21}` px focal-excluded, `dist_nearest_loss` censored at `R_max = 50` px, `nearest_loss_age` NaN-when-absent with an explicit `loss_absent_within_rmax` flag, `loss_trend` as an OLS slope over `T−4…T` within `r = 10`. `float32`/NaN, `uint8` flag. Halo = `R_max + 1 = 51` px, derived from the committed values. |
| 5 | 90 m **defined, not announced**: block eligible iff all 9 native pixels eligible; positive iff ≥1 native `lossyear == T+1`; mean/majority predictors; edge blocks excluded; offsets frozen in metres. The dual-gate conflict is resolved Codex's way — **one native-30 m event census serves both scales**, so ≥2 px keeps meaning ~0.18 ha, and only the AP-lift CI arm splits by scale. |
| 6 | Weights stated exactly: `m_s = min(50·P_s, N⁻_s)`, `m_s = min(B₀, N⁻_s)` with `B₀ = 50 000` when `P_s = 0`, `π_i = m_s/N⁻_s` for negatives and 1 for positives, `w_i = 1/π_i`, **target measure = pooled pixels at natural prevalence**, weights not renormalized per site. Site-equal risk and class balance explicitly disclaimed. Fold loaders open only their training-site partitions. |
| 7 | Tiles: 256×256 cores at stride 256 (**non-overlapping**), 32 px context halo, every pixel in exactly one core, **halos context-only contributing no loss**, sampled-pixel mask reused across overlaps, and deep compute budgeted as **full-tile** compute since sampling does not reduce forward passes. |
| 8 | Accounting corrected: 2 architectures × 36 folds × **2 scales = 144 runs**, both scales trained independently. |
| 9 | Seal bound to a **content-addressed, atomically finalized, read-only** artifact directory and to the **immutable generating tree SHA**, with hashes recomputed **while holding the transition lock**, closing the TOCTOU gap. |
| 10 | Numeric grid committed (`num_leaves ∈ {31,127}` × `min_data_in_leaf ∈ {200,2000}`, lr 0.05, 2000 rounds, early stop 100), fit-count formula derived (**3960 tabular fits + 144 deep runs**), cold-cache benchmark protocol with pinned thread count, and a **168 h ceiling** with explicit stop-and-replan. |

**Nothing rejected.** On finding 10 Codex offered two routes — put the numbers in, or end the plan at a
benchmark amendment gate. Numbers were committed where they are choosable and the gate retained only for
total wall-clock, which cannot honestly be known before measurement.


## Round 3 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: 26848662c9dbe7fb8f509f15d074d2f820f5d5e145ddc354d48acdc23897dd08
- verdict: REVISE (5 critical, 7 high, 2 medium)

### Critique (verbatim)

Material problems remain.

1. **Critical — the contagion-density features are identically zero.** The table defines the numerator over “eligible pixels,” but eligibility excludes every pixel lost by \(T\); therefore `loss_density_r` and `recent_loss_density_r` cannot contain losses ([plan:108](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:108>), [governing formula:69](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:69>)).  
   **Fix:** Evaluate features only at eligible focal pixels, but define neighborhood denominators over valid baseline-forest pixels and numerators over those with `1 ≤ lossyear ≤ T`, including a zero-denominator rule.

2. **Critical — the noninterference test is simultaneously impossible and insufficient.** Mutating every value `>T` changes the required `positive_(T+1)` label, so the complete output cannot remain byte-identical; merely recoding future nonzero years also would not detect a buggy `lossyear>0` feature ([plan:68](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:68>), [current label outputs:25](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:25>)).  
   **Fix:** Test predictor/eligibility artifacts separately under future erasure, relocation, and recoding—including \(T+1\)—while testing labels against their exact target formula and excluding label hashes from predictor noninterference comparisons.

3. **Critical — the fault-injection postcondition contradicts the commit point.** A crash before the rename should leave neither object published, while a crash after it must leave both; requiring “neither” at every durable boundary makes every post-commit test fail by design ([plan:57](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:57>)).  
   **Fix:** Define the rename as the commit point and test `neither before / both after / never exactly one`, with restart recovery for abandoned staging directories.

4. **Critical — the directory rename does not solve the cross-account ACL transition.** A same-volume NTFS move normally retains the source security descriptor, so a directory staged under the worker-only root remains unreadable after moving; relaxing its ACL before renaming creates a pre-lift exposure window ([plan:58](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:58>), [Microsoft NTFS move rules](https://learn.microsoft.com/en-us/troubleshoot/windows-client/windows-security/permissions-on-copying-moving-files)).  
   **Fix:** Publish handoff plus record as one container using `ReplaceFileW` over a pre-created destination placeholder whose final ACL is preserved, or specify an explicit recoverable ACL state machine instead of claiming the rename alone commits access.

5. **Critical — the alternate-account launcher retains a process-escape race.** Current code starts the child and only then assigns it to the Job Object, allowing it to spawn an uncontained process before assignment ([sandbox_process.py:154](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/sandbox_process.py:154>)); Microsoft explicitly supports suspended creation before job assignment ([documentation](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)).  
   **Fix:** Launch under the dedicated token with `CREATE_SUSPENDED`, assign the process to a no-breakaway Job Object, then resume it; test an immediate grandchild-escape attempt.

6. **High — the weighting contract lacks a scale-specific sampling unit.** It defines strata as `(site, origin)`, but 30 m units are pixels whereas 90 m units are complete 3×3 blocks with different \(P_s,N_s,\pi_i\); a sampled native-pixel mask does not induce the stated SRS probabilities for blocks ([plan:143](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:143>), [plan:156](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:156>)).  
   **Fix:** Define strata as `(site, origin, scale)`, draw negatives independently over eligible pixels or complete blocks, and state that each scale targets its own pooled units.

7. **High — weights are given, but the optimized estimator is not.** `Σw` equals the population count only in expectation; per-batch division by sampled `Σw` is a ratio estimator and can alter stratum influence, regularization, and deep-model gradients even though evaluation is full-population.  
   **Fix:** Freeze the training objective as `N_train⁻¹ Σsample w_i·loss_i` using the known full-population \(N\), with an unbiased minibatch reduction and explicit LightGBM/deep regularization semantics.

8. **High — one unrestricted 30 m event census is not valid for the strict 90 m population.** The 90 m population excludes every incomplete 3×3 block, yet the shared census can count components lying partly or wholly outside that support, inflating the 90 m evaluable-site and ≥30-component arms ([plan:125](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:125>), [plan:134](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:134>)).  
   **Fix:** Keep native labeling and the native two-pixel floor, but compute each scale’s component census after restricting the native positive mask to that scale’s evaluated support.

9. **High — the shift sensitivity remains undefined and can silently change the estimand.** Re-anchoring 90 m blocks at ±90 m changes complete-block inclusion, labels, prevalence, and component support rather than merely testing registration tolerance ([plan:131](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:131>)).  
   **Fix:** Hold labels, population, and block support fixed and shift predictions only on common support; make the unshifted result the sole dual-gate result.

10. **High — 3,960 is not the nested fit count.** Each inner \((h,j)\) residual model must select and calibrate without either site; unless hyperparameters are independently frozen, its four candidates must run per pair, giving `1260×2×4 = 10080` inner candidate fits and at least `10080+1152+288 = 11520` tabular fits before calibrators ([plan:184](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:184>), [nested requirement:238](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:238>)).  
    **Fix:** Count every inner candidate and calibrator separately, or define and justify an independently frozen inner hyperparameter rule that never uses site \(j\).

11. **High — the 168-hour projection cannot certify the ceiling.** Even the understated count permits only 2.55 minutes per tabular fit if deep runs cost zero; at 30 minutes per deep run it permits 1.45 minutes, while the benchmark samples only one architecture and omits scale/architecture variation, calibration, inference, bootstrap, and I/O ([plan:192](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:192>)).  
    **Fix:** Recompute from corrected counts using benchmarks for every fit class and deep architecture/scale, an explicit execution schedule, full inference/evaluation overhead, and a safety margin.

12. **High — the deep 90 m artifact is not defined.** A 256-native-pixel core is not divisible by three, so its boundaries cannot align with 90 m blocks, and the fixed 32-pixel halo is not required to exceed the subsequently measured receptive-field radius ([plan:143](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:143>), [plan:189](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:189>)).  
    **Fix:** Define separate scale-aligned tilings—90 m cells directly or 30 m core dimensions divisible by three—and require context halo ≥ measured receptive-field radius before training.

13. **Medium — the contagion boundary contract is still incomplete.** `nearest_loss_age` has no tie rule for equidistant losses, 90 m means over its intentional NaNs are undefined, and the fixed 21-tile inventory is not explicitly expanded by the 51-pixel halo ([plan:111](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:111>), [plan:116](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:116>)).  
    **Fix:** Freeze tie-breaking and NaN aggregation, and derive/fail-close the GFC inventory from every site footprint expanded by the full halo.

14. **Medium — the declared model schema still conflicts with the frozen ablations.** The plan calls an optical-only arm “full” while deferring SAR and optical+SAR, although the governing design freezes six arms ([plan:176](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:176>), [FORECAST-PLAN.md:199](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:199>)).  
    **Fix:** Rename it `full_without_sar` and prohibit final architecture competition or headline gating until all six frozen arms exist and their fits are budgeted.

VERDICT: REVISE
### Claude's response (round 3)

**All 14 findings accepted; none rejected.** Two load-bearing claims were verified in source before
acceptance:

- **#1 confirmed fatal by definition.** `eligible(T) = datamask==1 ∧ treecover2000 ≥ θ ∧ (lossyear==0 ∨
  lossyear>T)`, so the set "eligible pixels with loss ≤ T" is **empty**. Every v3 contagion density was
  identically zero. `FORECAST-PLAN.md` §8 had already removed own-pixel prior loss for exactly this reason;
  v3 reintroduced the same trap in the neighbourhood denominators.
- **#5 confirmed in committed code.** `sandbox_process.py:154` calls `subprocess.Popen(...)` and only then
  `job.assign(process)` — a real window in which the child can spawn an uncontained grandchild.

Josh was asked whether to continue or split the plan given that findings #10/#11/#14 are structural rather
than editorial; he chose to **continue rounds 4–5 on the full plan**.

| Finding | Change |
|---|---|
| 1 | Support definitions rebuilt: focal set = eligible(T); **neighbourhood denominator = valid baseline-forest** (`datamask==1 ∧ treecover2000 ≥ θ`, regardless of later loss); numerator = `1 ≤ lossyear−2000 ≤ T−2000`; explicit zero-denominator → NaN + `*_undefined` flag. |
| 2 | Noninterference **split by artifact class**: predictors/eligibility tested under **erasure, relocation and recoding** (incl. T+1) requiring byte-identical outputs; labels tested against their exact target formula; label hashes excluded from the predictor comparison. Recoding alone could not catch a `lossyear > 0` read — hence erasure and relocation. |
| 3 | Commit point defined as the publish call; postconditions are **neither before / both after / never exactly one**, plus restart recovery for abandoned staging. v3's "neither at every boundary" would have failed every post-commit test by design. |
| 4 | Directory rename abandoned: a same-volume NTFS move **retains the source security descriptor**, so the staged container would stay unreadable, and relaxing the ACL first opens an exposure window. Masks **and** record now go into **one container file**, published via **`ReplaceFileW` over a pre-created placeholder carrying the final ACL**. |
| 5 | `CREATE_SUSPENDED` → assign to a **no-breakaway** Job Object → resume, with an immediate grandchild-escape test. |
| 6 | Strata are now **(site, origin, scale)**; negatives drawn independently over pixels (30 m) or complete blocks (90 m); each scale targets its own pooled units. |
| 7 | Objective frozen as `L = N_train⁻¹ Σ w_i·loss_i` with the **known full-population `N_train`** and an unbiased minibatch reduction (never divide by the batch weight sum); `min_data_in_leaf` interpreted on unweighted row counts, stated in the audit. |
| 8 | Each scale's component census computed **after restricting the native positive mask to that scale's evaluated support**, keeping native labelling and the native 2 px floor. |
| 9 | Labels, population and block support **held fixed**; only **predictions** shift, on common support; the **unshifted result is the sole dual-gate result**. |
| 10 | Inner hyperparameters **frozen a priori and data-independently** (nuisance model for range estimation; no early stopping, since that needs a selection set). Count restated: **4248 tabular fits**, with the ≥11 520 alternative recorded and an explicit stop if the frozen-inner rule is rejected. |
| 11 | Benchmarks for **every fit class and each architecture × scale**, plus inference/evaluation/bootstrap/I-O overhead, an execution schedule, and a **×1.5 safety margin** against the 168 h ceiling. |
| 12 | **Scale-aligned tilings**: 256 native cores at 30 m, **258 (= 3×86)** at 90 m so cores align to blocks; halo = `max(32, ceil(RF_radius))` with the receptive field **measured before training** and a fail-closed assertion. |
| 13 | Tie rule frozen (most recent year, then smallest raster index); 90 m NaN aggregation defined (mean over non-NaN, flags aggregated as **any**, all-NaN → NaN + flag); tile inventory **derived from footprints expanded by the full halo and fail-closed** — recomputed, and it still yields 21 tiles / 63 files. |
| 14 | Arm renamed **`full_without_sar`**; the §9 **architecture competition and headline gate are explicitly DEFERRED** until all six frozen arms exist. Deep heads are trained and reported **descriptively only** in this plan. |

**Nothing rejected.** Finding 14's consequence is accepted rather than argued: this plan delivers a complete
pipeline and descriptive results, but no confirmatory model selection, until SAR lands.


## Round 4 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: f0d7dad6a3d21ca1bed77d5f7213c6f285ce8d2f088bbd5f27a7a95b0a02b7fa
- verdict: REVISE (7 critical, 4 high, 2 medium)

### Critique (verbatim)

Material problems remain.

1. **Critical — the GFC year encoding is still undefined and is wrong if read literally.** Current readers expose Hansen’s raw codes `1…24`, and current code tests `lossyear <= 20`; the revised formula `1 ≤ lossyear−2000 ≤ T−2000` would therefore empty the numerator again ([plan:126](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:126>), [risk/hansen.py:209](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/hansen.py:209>), [gfc_censor_worker.py:32](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor_worker.py:32>)).  
   **Fix:** Define `loss_code` as the raw byte and `loss_year = 2000 + loss_code` for nonzero codes at the input boundary, then use exactly one representation in every formula and test.

2. **Critical — the numerator is not explicitly intersected with θ-specific baseline forest.** At high θ, the current numerator can count losses on pixels excluded from the denominator, making a “fraction” exceed one and making θ sensitivities scientifically inconsistent ([plan:124](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:124>)).  
   **Fix:** Define `loss_support_θ,T = datamask==1 ∧ treecover2000≥θ ∧ 1≤loss_code≤T−2000` and use it for every density, trend, distance, and age feature.

3. **Critical — θ is missing from the downstream schema.** Features and eligible populations vary by θ, yet table paths, the stated 216-file count, sampling strata, RNG keys, and fit counts contain no θ dimension ([plan:91](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:91>), [plan:166](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:166>), [plan:184](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:184>)).  
   **Fix:** Freeze whether each θ sensitivity is a full retrain; if so, add θ to artifacts, strata, RNG keys, metrics, and fit counts, and if not, define the common-training estimand and explain how θ=10 pixels absent from θ=30 training are handled.

4. **Critical — the frozen inner model is leakage-safe but estimates the wrong residual process.** Section 10(a) requires inner fits to preserve training, selection, and calibration roles; a fixed 500-round nuisance model does not reproduce the outer tuned contagion baseline whose residual dependence is supposed to determine \(L\) ([plan:222](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:222>), [FORECAST-PLAN.md:236](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:236>)). This need not bias the variogram of its own residuals, but it changes the target variogram and can move the 0.95-sill crossing in either direction.  
   **Fix:** Either perform inner selection/calibration excluding both \(h\) and \(j\), or formally amend §10(a) so the reported contagion baseline uses the identical fixed algorithm; an always-conservative 200·g fallback is a simpler explicit amendment.

5. **Critical — `ReplaceFileW` is not a one-state failure primitive.** Microsoft documents failure states where the destination disappears, the old file moves, or the staging file inherits the placeholder’s attributes and ACL; reclaiming only “abandoned staging containers” does not cover them ([plan:65](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:65>), [Microsoft `ReplaceFileW` documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)).  
   **Fix:** Use flags `0`, prohibit ACL-ignore flags, enumerate and recover Win32 errors 1175–1177 by observed path/file-ID/DACL state, and test each state under both real account tokens.

6. **Critical — crash atomicity is improved, but durability is not established.** `REPLACEFILE_WRITE_THROUGH` is explicitly unsupported, and OneDrive’s minifilter/cloud replication is outside `ReplaceFileW`’s local-NTFS guarantee; moreover, the proof demands the container be absent even though a placeholder must exist ([plan:281](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:281>), [plan:320](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:320>)).  
   **Fix:** Require a fully local, non-reparse NTFS publication directory outside OneDrive, specify pre/post replacement flushing or explicitly exclude power-loss durability, and assert a canonical uncommitted placeholder state rather than path absence.

7. **Critical — the deep minibatch estimator is not unbiased as written.** With \(n\) sampled units and a uniform batch of size \(b\), `Σbatch/N_train` has expectation \(b/n\) times the desired gradient unless gradients are accumulated for the entire epoch before one optimizer step ([plan:198](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:198>)).  
   **Fix:** Use `n/(b·N_train)·Σbatch w_i loss_i`, or the analogous tile-inclusion factor for tile batches, and define last-batch, gradient-accumulation, clipping, and weight-decay behavior.

8. **High — the LightGBM objective contract is inaccurate.** Supplying raw `sample_weight=w` optimizes a proportional weighted objective, not literally the normalized formula when scale-sensitive regularization and split thresholds exist; additionally, LightGBM documents `min_data_in_leaf` as an approximation based on Hessians, not guaranteed unweighted row counts ([plan:199](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:199>), [LightGBM parameter documentation](https://lightgbm.readthedocs.io/en/stable/Parameters.html#min_data_in_leaf)).  
   **Fix:** Freeze normalized weight scaling plus every Hessian/gain/L1/L2 threshold, remove the raw-count claim, and test model invariance under equivalent global weight rescalings.

9. **High — the new 90 m tiling numbers are not architecture-safe.** A 258-pixel core aligns with 3×3 blocks but is not divisible by the usual \(2^d\) U-Net downsampling factor, and measuring an “effective” receptive field on one initialized network can miss theoretically reachable paths ([plan:168](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:168>)).  
   **Fix:** Derive core size as a multiple of `lcm(3, 2^depth)`, specify the native-input-to-90 m-output mapping, and size halos from the architecture’s theoretical maximum receptive field.

10. **High — the split noninterference test still conflicts with the aggregate transcript.** Current `CensorTranscript` contains one combined file-name/size/hash inventory, so changed label hashes necessarily change the transcript even when predictor fields are filtered ([plan:84](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:84>), [gfc_censor.py:38](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/gfc_censor.py:38>)).  
    **Fix:** Define separate predictor and label transcript projections—or separate manifests—and compare only the complete predictor projection during future-mutation tests.

11. **High — model selection and calibration remain under-specified.** The candidate grid has no validation selection metric or deterministic tie-break, while “288 calibrators” assumes one unspecified calibration method despite the governing design making the calibrator validation-selected ([plan:219](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:219>), [FORECAST-PLAN.md:25](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:25>)).  
    **Fix:** Freeze the outer selection metric, tie-break, calibration candidate set and selection rule, then recount all calibrator fits, including any descriptive deep models that report calibrated metrics.

12. **Medium — the 90 m undefined flag is semantically contradictory.** A block with one NaN and eight valid values receives a defined `nanmean` but also an `*_undefined=1` flag because flags aggregate with `any`; categorical majority ties also remain unspecified ([plan:150](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:150>)).  
    **Fix:** Emit `valid_count` or `any_missing`, set `undefined` only when all nine inputs are undefined, and freeze a deterministic categorical tie-break.

13. **Medium — deferring the headline gate is coherent, but the remaining scope description is not.** The plan correctly prevents headline selection, yet still claims to implement the §9 stack and spends 144 deep runs that cannot be reused once SAR changes the final input channels ([plan:41](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:41>), [plan:212](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:212>)).  
    **Fix:** Relabel this as a partial pre-SAR descriptive stage and defer full deep training—retaining only the tiling/integration pilot—until all six arms are available.

VERDICT: REVISE
### Cap amendment (after round 4)

`MAX_ROUNDS` raised from 5 by Josh's decision; the loop now runs until `APPROVED` or `MAX_ATTEMPTS = 8`,
which becomes the binding cap. Attempts used: 5 (one round-1 timeout that produced no verdict and was
correctly not counted as a round, plus rounds 1–4). **3 attempts remain.**

Josh also reversed the earlier "both scales, 144 deep runs" decision in light of finding 13: those runs
cannot be reused once SAR changes the network's input channels, so deep work is cut to the tiling
artifact, the receptive-field measurement, and a one-site integration pilot.

### Claude's response (round 4)

**All 13 findings accepted; none rejected.** Two were verified in source first:

- **#1 confirmed.** `hansen.py:209` uses `loss >= 1, loss <= 20` and `gfc_censor_worker.py:32` uses
  `lossyear > 20` / `== 21` — Hansen stores **raw codes 1…24, not years**. v4's `1 ≤ lossyear−2000 ≤ T−2000`
  would have evaluated `1−2000` and emptied the numerator, reproducing round 3's zero-feature bug in a new
  disguise. This is the second time an encoding assumption silently emptied the contagion features.
- **#6 confirmed.** The repo lives at `C:\Users\josha\OneDrive\Documents\Satellite Image Classifier` —
  inside OneDrive — so `ReplaceFileW`'s local-NTFS guarantee does not cover the publication path.

| Finding | Change |
|---|---|
| 1 | **`loss_code` (raw byte) and `loss_year = 2000 + loss_code`** defined once at the input boundary; `loss_code` used in every formula and test thereafter. |
| 2 | `loss_support_θ,T = datamask==1 ∧ treecover2000≥θ ∧ 1≤loss_code≤T−2000` — numerator **explicitly intersected with the θ baseline**, so a fraction can no longer exceed one at high θ. |
| 3 | **θ promoted to a first-class schema dimension**: table paths, strata, RNG keys, metrics and fit counts. θ=30 primary with the full pipeline; θ∈{10,25,50,75} are **full retrains** on `full_without_sar` at 30 m, single frozen candidate, labelled sensitivities. |
| 4 | **§10(a) formally amended** so the contagion baseline used for range estimation is the *identical fixed algorithm* at inner and outer levels, so both target the same residual process. Fallback if rejected: the conservative **`200·g`** maximum-lag block size. Per-pair inner selection (≥10 080 fits) does not fit the ceiling and is not adopted. |
| 5 | `ReplaceFileW` with **flags 0**, ACL-ignore flags prohibited, **Win32 1175/1176/1177 enumerated and recovered** by observed path / file-ID / DACL state, each tested under both tokens. |
| 6 | Publication moved to a **fully local, non-reparse NTFS path outside OneDrive**; flushing specified; **power-loss durability explicitly excluded** rather than claimed. Proof now asserts a **canonical uncommitted placeholder state** instead of path absence. |
| 7 | Minibatch reduction corrected to **`(n / (b · N_train)) · Σ_batch w_i·loss_i`** (v4's `Σ_batch/N_train` was biased by `b/n`), with last-batch, gradient-accumulation, clipping and weight-decay behaviour defined. |
| 8 | Raw-count claim for `min_data_in_leaf` **withdrawn** (it is a Hessian-based approximation). Frozen instead: normalized weight scaling plus `min_sum_hessian_in_leaf`, `min_gain_to_split`, `lambda_l1`, `lambda_l2`, with an invariance test under global weight rescaling. |
| 9 | Core size is a multiple of **`lcm(3, 2^depth)`** → **288 native px** at depth 4 (= 3×96 = 16×18), valid at both scales, with the native-input → 90 m-output mapping stated; halo sized from the **theoretical maximum** receptive field, not a measured effective one. |
| 10 | **Separate predictor and label transcript projections (manifests)** defined; only the complete predictor projection is compared under future-mutation, since `CensorTranscript` carries one combined inventory. |
| 11 | Outer **selection metric = AP on the validation origin** with a deterministic tie-break; calibration candidate set **{Platt, isotonic}** selected by log-loss with deterministic tie-break; calibrators recounted as **576** fits. |
| 12 | 90 m missingness reported as **`valid_count`** and **`any_missing`**, with `*_undefined` set **only when all nine inputs are undefined**; categorical majority ties broken by smallest category code. |
| 13 | Stage **relabelled "pre-SAR descriptive"**; full deep training deferred, retaining only the tiling artifact, the theoretical receptive-field derivation and a **4-run one-site integration pilot** (Josh's decision, reversing the earlier 144-run choice now that those runs are known to be unreusable once SAR changes input channels). |

Revised fit count: **4680 tabular fits + 4 pilot runs** (was 4248 + 144).


## Round 5 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: 3e88e30461a5db35268fba82e60a20f736d03e7003cd6dbdec5650f9a860e8e6
- verdict: REVISE (5 material defects + 1 trust-root note)
- NOTE: reviewer explicitly conceded the pre-SAR scope, contagion support, 90 m estimand,
  natural-population evaluation and deferred headline gate as now coherent.

### Critique (verbatim)

Not yet sound enough to implement. The pre-SAR scope, contagion support, 90 m estimand, natural-population evaluation, and deferred headline gate are now coherent. Five material defects remain:

1. **§10(a) contradicts the model grid and fit ledger.** The amendment requires the outer contagion baseline to use the same fixed algorithm as the inner model, but the outer count still tunes all four arms over four candidates ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:226>), [count](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:236>)).  
   **Fix:** Remove contagion from the four-candidate grid and count it once per fold/scale; the outer count becomes 936 and the stated total becomes 4,464 before any missing θ calibrators.

2. **The θ sampling contract is impossible.** Eligible populations are nested across thresholds, so “no pixel is ever shared across θ training sets” contradicts independent per-θ draws and the population definitions ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:160>)).  
   **Fix:** Permit overlapping physical pixels while keeping datasets, RNG streams, weights, artifacts, and fitted models isolated by θ.

3. **The 4,680 count omits the declared calibration treatment for θ sensitivities.** Calibration applies without a θ exception, but the sensitivity ledger counts only one LightGBM fit per fold; transferring θ=30 calibrator parameters would confound the sensitivity ([calibration](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:224>), [ledger](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:241>)).  
   **Fix:** Either declare θ sensitivities raw-probability-only, or add and recount per-θ calibrator fitting and selection.

4. **The `ReplaceFileW` recovery “contract” remains underspecified.** It never freezes `lpBackupFileName`, although 1176/1177 path states depend on that argument; moreover, 1177 can leave the staging file under its old name after inheriting placeholder attributes/DACL, so it may become analysis-readable despite a failed call. [Microsoft documents these distinct states explicitly.](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)  
   **Fix:** Freeze the backup argument and paths, then provide a state table mapping every return code plus path/file-ID/DACL combination to committed or uncommitted status and an idempotent recovery action; an analysis-readable 1177 replacement cannot subsequently be classified as rolled back.

5. **The LightGBM correction still freezes unnamed values.** The plan names normalized scaling and Hessian/gain/L1/L2 thresholds but supplies neither the normalization formula nor numeric thresholds; fixed absolute regularization also cannot be invariant to global weight scaling unless those quantities co-scale ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:202>)).  
   **Fix:** State the exact canonical weight normalization and numeric thresholds, and define the invariance test as jointly rescaling weights, Hessian/gain thresholds, and L1/L2 penalties.

The content-addressed seal also needs an explicit trust root: hashes and a git tree SHA establish integrity, not authority, unless the approved tree SHA, complete artifact allow-list, and worker-owned seal store are fixed.

VERDICT: REVISE
### Claude's response (round 5)

**All 5 findings plus the trust-root note accepted; none rejected.** Finding count across rounds:
**15 → 10 → 14 → 13 → 5**, and this round the reviewer explicitly conceded the pre-SAR scope, contagion
support, 90 m estimand, natural-population evaluation and deferred headline gate as coherent. What remained
were bookkeeping and specification gaps rather than structural defects.

| Finding | Change |
|---|---|
| 1 | **Contagion removed from the four-candidate grid.** The §10(a) amendment requires the outer contagion baseline to be the identical fixed algorithm as the inner model, so tuning it contradicted the amendment it rests on. Contagion is now fitted once per (fold, scale); outer becomes `864 + 72 = 936` and the **tabular total is 4464**. |
| 2 | **The impossible θ contract is withdrawn.** Eligible populations are **nested** across thresholds, so "no pixel is ever shared across θ training sets" could never hold. Isolation is now **by artifact, not by pixel**: physical pixels may overlap, while datasets, RNG streams, inclusion probabilities/weights, on-disk artifacts and fitted models are isolated per θ. |
| 3 | **θ sensitivities declared raw-probability-only.** No calibrator is fitted or transferred for them — borrowing the θ=30 calibrator would confound the sensitivity — so they report **rank-based metrics only** (AP, AP-lift, budget recall), never Brier, log-loss or calibration slope/intercept. The ledger is consistent with that declaration. |
| 4 | **`lpBackupFileName` frozen** to a fixed worker-owned path (the 1176/1177 path states depend on it), plus an explicit **state table** mapping every return code × observed (path, file ID, DACL) → committed/uncommitted → idempotent recovery. The 1177 row is treated as **committed-or-exposed and never as rolled back**, because the replacement can become analysis-readable despite a failed call; recovery quarantines the inherited object and re-verifies the seal. Every row tested under both tokens. |
| 5 | **Numbers supplied, and the invariance test corrected.** Canonical normalization `w̃_i = w_i · (n_sample / Σ_j w_j)` so `Σw̃ = n_sample`; thresholds frozen at `min_sum_hessian_in_leaf = 100.0`, `min_gain_to_split = 0.0`, `lambda_l1 = 0.0`, `lambda_l2 = 1.0`. The test now **jointly** rescales weights and the Hessian/L1/L2 quantities — fixed absolute regularization cannot be scale-invariant otherwise — with rescaling-weights-alone asserted to *change* the model as a non-vacuity control. |
| note | **Trust root made explicit.** Hashes and a tree SHA give integrity, not authority, so the seal is now checked against (a) an allow-list of approved tree SHAs, (b) a complete artifact allow-list where extras are as fatal as omissions, and (c) a worker-owned seal store the analysis account cannot write. |


## Round 6 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: 138ee4834f4451b18ebdf305c729dad5866a8f0381773671db9d574af7817240
- verdict: REVISE (2 material blockers)
- NOTE: reviewer verified the fit ledger arithmetic and confirmed theta isolation,
  raw-only sensitivity metrics, seal trust root and pre-SAR scope as mutually consistent.

### Critique (verbatim)

The fit ledger is correct: `864 + 72 + 288 + 2520 + 576 + 144 = 4464`. Theta isolation, raw-only sensitivity metrics, seal trust root, and pre-SAR scope are mutually consistent.

Two material implementation blockers remain:

1. **The `ReplaceFileW` state table is incorrect and incomplete.** With non-NULL `lpBackupFileName`, error 1176 leaves the destination and staging files under their original names; the new payload remains at staging, while the backup represents the old placeholder. Therefore “re-stage from the backup path” restores the wrong content. For 1177, the old placeholder is at the backup path, the exposed replacement remains at staging, and the destination is absent; quarantining it does not recover a canonical committed state and improperly reverses an already-exposed commit. The table also omits the documented “any other error” state despite claiming exhaustive coverage ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:83>), [Microsoft contract](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)).  
   **Fix:** For 1176 retry from intact staging; for 1177 classify as exposed/must-roll-forward, restore the placeholder from backup and forward-publish the same verified staging payload; add a fail-closed row for every other error based on observed names, IDs and DACLs.

2. **The LightGBM invariance tests contradict canonical normalization.** Because `w̃_i = w_i·n/Σw`, globally replacing `w` with `c·w` produces exactly the same `w̃`; therefore weights-only rescaling cannot change the model, and jointly scaling the already-fixed thresholds would instead change the configuration ([plan](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:232>)).  
   **Fix:** Assert that raw global rescaling produces identical normalized weights and models with unchanged thresholds; use a relative-weight perturbation as the non-vacuity control, and test joint scaling only separately at a normalization-bypassed LightGBM adapter boundary.

VERDICT: REVISE
### Claude's response (round 6)

**Both findings accepted; none rejected.** The reviewer independently verified the fit ledger arithmetic
(`864 + 72 + 288 + 2520 + 576 + 144 = 4464`) and confirmed θ isolation, raw-only sensitivity metrics, the
seal trust root and the pre-SAR scope as mutually consistent. Both remaining defects were cases where the
round-5 fix was **actively wrong**, not merely incomplete.

| Finding | Change |
|---|---|
| 1 | **State table corrected on both recovery rows, plus a fail-closed catch-all.** With non-NULL `lpBackupFileName`, **1176** leaves the new payload at *staging* while the backup holds the *old placeholder* — so v6's "re-stage from the backup path" would have republished the wrong content; recovery is now **retry from intact staging**. **1177** leaves the old placeholder at the backup path, the exposed replacement at staging and the destination absent — so quarantining it neither reaches a canonical committed state nor is legitimate, because it reverses an **already-exposed** commit; it is now classified **exposed / must roll forward**: restore the placeholder from backup, then forward-publish the same verified staging payload. An **any-other-error** row was added, since the table claims exhaustive coverage and Microsoft documents states beyond the three named codes. |
| 2 | **Invariance tests inverted to match the normalization.** Since `w̃_i = w_i·(n/Σw)`, a global `w → c·w` yields **identical** `w̃`, so v6's claim that weights-only rescaling changes the model was false, and jointly scaling the already-fixed thresholds would have *changed* the configuration instead of preserving it. Now: (1) global raw rescaling ⇒ identical normalized weights and identical models with **unchanged** thresholds; (2) the non-vacuity control is a **relative** weight perturbation; (3) joint scaling is tested **only** at a normalization-bypassed LightGBM adapter boundary, the sole place co-scaling applies. |


## Round 7 — codex — APPROVED

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0
- session: 019fa356-0b74-7682-8927-0262224a39df (resumed)
- reviewed body_sha256: 030d78fa637b6eb5514649756b4c580982aae2e18359ed1234381bbd4b49f93a
- verdict: APPROVED

### Critique (verbatim)

The plan is sound enough to begin implementation as the defined pre-SAR descriptive stage.

Verified:

- The `ReplaceFileW` 1176 and 1177 recovery directions are now correct and monotonic ([state table](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:90>)).
- The LightGBM normalization and three distinct tests are mutually consistent ([weight contract](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/ANALYSIS-DRIVER-PLAN.md:236>)).
- The fit ledger correctly totals 4,464.
- Theta populations may overlap physically while all statistical and fitted artifacts remain isolated; raw-only sensitivity metrics match the fit ledger.
- Deferred study components are not implicitly used by this stage, and the 168-hour benchmark is a genuine stop gate.

Non-blocking implementation notes:

- Assert at runtime that destination, staging, and backup are on the same volume, as [`ReplaceFileW` requires](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew).
- For an unknown error that leaves an analysis-readable DACL, preserve “exposed/must-forward” status through manual verification; fail-closed must never mean rollback.
- Bind the θ sensitivity’s “single frozen candidate” explicitly before Phase D and include fixed outer contagion as its own benchmark class.

VERDICT: APPROVED
### Claude's response (round 7)

Approved on the final available attempt (8 of 8). The three non-blocking notes are recorded HERE rather
than in the plan body **on purpose**: editing the body after approval would break the hash binding and
downgrade provenance from `approved-final` to `approved-stale`. They are binding on the build:

1. **Assert at runtime that destination, staging and backup share one volume** — `ReplaceFileW` requires
   it, and the plan's atomicity argument silently assumes it.
2. **An unknown error leaving an analysis-readable DACL must preserve exposed/must-forward status through
   manual verification** — fail-closed must never be implemented as rollback.
3. **Bind the θ sensitivity's single frozen candidate explicitly before Phase D**, and give fixed outer
   contagion its own benchmark class (it is no longer in the tuned grid, so it needs its own timing).

---

## Implementation deviation 1 — GFC pinning anchor (Phase A, 2026-07-27)

**Approved plan text (Phase A step 10):** "verify each tile against the **independent published MD5** →
then create the write-once SHA-256 inventory". This originates in Codex round-1 finding #12.

**It cannot be implemented: no such manifest exists.** The official GFC-2024-v1.12 download page
(`storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/download.html`) publishes per-layer URL
listings (`treecover2000.txt`, `lossyear.txt`, `datamask.txt`) and **no checksums of any kind**. Round-1
#12 was accepted without confirming the manifest existed.

**The governing rule is narrower than the plan asserted.** `FORECAST-PLAN.md` §5 freezes
"Pin GFC version+md5 (at download...)" — *record* the md5 at download. It never required verification
against a third-party manifest. §5 as frozen is fully satisfiable.

**Anchor adopted (Josh's decision).** Google Cloud Storage serves, per object and retrievable by `HEAD`
**without** transferring the file:

- `x-goog-hash: md5=<base64>` — server-computed; verified to decode exactly to the `ETag` hex
  (`YYAGoCBYN3xXn1Gkx+otIQ==` -> `618006a02058377c579f51a4c7ea2d21` for `lossyear_10S_060W`).
- `x-goog-generation` — immutable object-version identifier.
- `Content-Length` — cross-check against bytes received.

**What this guarantee is, stated plainly, so it is never overstated later:**

| Threat | Covered |
|---|---|
| Truncated / corrupted transfer (this repo's documented `_download` weakness) | YES — the hash is fetched in a separate request from the bytes |
| Silent re-publication of a tile under the same name | YES — `x-goog-generation` changes |
| Substitution at source | **NO** — the same host serves both the bytes and the hash |

It is therefore **stronger than self-hashing and weaker than an independent anchor**. Any later claim of
"independently verified" GFC provenance is unsupported and must not be made; the correct phrasing is
"pinned to the publisher's server-computed md5 and object generation at download".

**Plan body unchanged**, so the `approved-final` binding to `030d78fa` still holds; this deviation lives
in the log by design.

---

## Implementation deviation 2 — raw-GFC isolation mechanism (Phase 0.7, 2026-07-28)

**Approved plan text (Phase 0 step 7):** "A **dedicated least-privilege local account** owns the raw GFC
directory; the sealed worker runs under it, the interactive analysis account is denied."

**The design is sound; it is unusable on this machine.** Launching *any* process as a second local account
failed six distinct ways on Windows 11 Home:

1. `Start-Process -Credential` -> `Access is denied` (`CreateProcessWithLogonW` refuses to be called from
   an elevated process dropping to a standard user).
2. Scheduled task -> `LastTaskResult = 267011` (never ran).
3. `SeBatchLogonRight` suspected missing -> it was already held, listed by **name** not SID; the grant
   script's own verification only matched the SID form and reported a false `[FAIL]`.
4. Task then reported `LastTaskResult = 0` while producing no output whatsoever.
5. Root cause of (4): `C:\Users\Public` grants write to `NT AUTHORITY\INTERACTIVE` and
   `NT AUTHORITY\SERVICE`; a credentialed task runs as **BATCH**, which is in neither, so the redirect
   targets could not be created.
6. With an explicitly-granted run directory, `cmd` still never executed -- the step marker, the first line
   of the wrapper, was never written, while the scheduler still reported success.

Critically this blocks **analysis time**, not just acquisition: the sealed worker must read the tiles too,
so a design that can never launch as the worker account cannot work at all.

**Mechanism adopted (Josh's decision): the UAC split token.** The directory grants `Administrators` and
`SYSTEM` and nothing else. The interactive user has **no entry**, so an unelevated process -- which is what
analysis code is -- has no access; an elevated one reaches it through `Administrators`.

**No deny ACE.** An explicit deny outranks the `Administrators` allow and locks out elevated access too:
that is exactly what broke acquisition (observed: a 647 MB tile downloaded and verified, then `os.replace`
raised `WinError 5`, because icacls `(R)` covers `SYNCHRONIZE`/`READ_CONTROL` that the rename's open
needs). Absence of a grant is what denies the unelevated user.

**What changed about the guarantee, stated plainly:**

| | Previous design | Adopted |
|---|---|---|
| Distinguishes | principals (worker vs analysis account) | privilege levels (elevated vs not) |
| Analysis code (unelevated) can read tiles | no | no |
| **Any** elevated process can read tiles | no | **yes** |
| Works on this machine | **no** | yes |

It remains an OS mechanism, not a convention. It is weaker in exactly one way: privilege level rather than
identity. `require_enforced()` now refuses an **elevated** caller as well, because an elevated observation
cannot demonstrate the boundary -- only an unelevated process can, and that is the context analysis code
runs in.

**Plan body unchanged**, so the `approved-final` binding to `030d78fa` still holds.

---

## Implementation deviation 3 — static driver availability (Phase B, 2026-07-28)

**Approved plan text (Phase B step 13):** acquire roads (Geofabrik/OSM ≤ T), protected areas (WDPA
historical monthly ≤ T) and terrain (Copernicus DEM), each pinned to a snapshot at or before the issue
date.

Availability was checked **before** writing acquisition code, which is the Phase A lesson (deviation 1 came
from asserting an anchor that did not exist). Two of the three cannot be acquired as written.

**Roads — compliant, with disclosed staleness.** Geofabrik publishes dated yearly extracts back to 2018,
but they are dated **1 January**, not year-end. The issue date is 31 December T, so `2021-01-01` is one
day *after* origin 2020's issue date and is inadmissible. The compliant snapshot is **1 January of T**,
which makes the roads layer **up to twelve months stale**. Accepted and disclosed; roads are slow-moving.
Scope: 11 country extracts spanning the four strata, ~3.6 GB per origin, ~10.8 GB total.

**Terrain — Copernicus rejected entirely; CGIAR-CSI SRTM v4.1 adopted (Josh's decision).**

*Corrected mid-phase.* The first recommendation was GLO-90, on the reasoning that GLO-30 is the 2021
release while "GLO-90 was released in 2019". **That was wrong**, and Josh had already decided on it before
the error surfaced: the AWS Open Data registry states both GLO-30 and GLO-90 "come from Copernicus DEM
**2021 release**". The *release*, not the resolution, is what post-dates the 2020 issue date, so switching
resolutions bought nothing. Same failure mode as deviation 1 — a property was asserted without confirming
the artifact actually had it.

Adopted instead: **CGIAR-CSI SRTM v4.1, 2008 release, 90 m, no authentication** (reachability verified).
It predates every origin by over a decade, so no vintage argument is needed at all. Terrain is the most
static covariate in the set, and a 2008 elevation model is not meaningfully staler than a 2021 one for
slope and elevation. NASADEM (Feb 2020, 30 m) was considered and set aside: it clears the training origin
by only ten months and needs NASA Earthdata credentials the pipeline does not have.

A regression test now asserts that a 2021-release terrain layer is excluded **at any resolution**, so
re-adding Copernicus cannot pass quietly.

**Protected areas — excluded under §3 (Josh's decision).** Protected Planet publishes the **current month
only**; no documented public archive of past monthly releases at stable URLs was found. §3's own rule
applies: excluded from the primary model, available only as a labelled exploratory sensitivity. Rejected
alternatives: an authenticated Earth Engine dependency the pipeline does not have, and using a current
release for historical origins — the latter is a genuine leak risk, since protected-area designation
plausibly correlates with the outcome.

**Resulting frozen primary schema (the intersection across all three origins):**
`roads, terrain, rivers, ecoregion, climate` — with `peat` excluded as region-limited (Asia-only, so
absence would conflate "no peat" with "not surveyed") and `protected_areas` excluded as above. Coverage
is carried as five explicit `*_covered` features so absence is never encoded as `NaN`.

**Plan body unchanged**, so the `approved-final` binding to `030d78fa` still holds.
