# Plan Review Log: Widen the site frame from 12 to 28

Act 1 (grill) complete — plan locked with Josh 2026-07-20. MAX_ROUNDS=5.
PLAN_FILE=FRAME-WIDENING-PLAN.md  (amends FORECAST-PLAN.md v11)
Reviewer: gpt-5.6-sol @ xhigh reasoning effort, codex-cli 0.144.5.

Act 1 decisions carried in (all Josh's):
1. Per-region generalization estimand SURVIVES; gate thresholds unchanged.
2. K=7 uniform per stratum -> 28 sites (12 existing + 16 new), frozen draw ranks 1-7, ~37 GB.
3. Merge `risk-forecasting` into this branch for the risk/ package (done, 5748aa3, 35 tests pass).
4. Measure the quiet rate at ranks 4-7 BEFORE downloading, as a reviewed step rather than ad hoc.

---

## Round 1 — attempt 1 ABORTED (infrastructure, not review)

First `codex exec` was killed at the skill's 10-minute ceiling while still actively reasoning (16 tool
calls, 40 reasoning blocks — not a hang; xhigh effort on this repo is simply slow). Relaunched detached.

The detached run then died on **network**, not on the review: repeated
`stream disconnected before completion: No such host is known. (os error 11001)` — DNS failures against
`chatgpt.com`, five reconnect attempts exhausted twice, then `turn.failed`. **No verdict was produced.**
Connectivity was re-verified afterwards (DNS resolves, HTTPS reachable) and the thread was RESUMED rather
than restarted, preserving 34 completed tool calls of exploration. Thread `019f7f9a-5503-7052-92c0-a54ac6c96bf4`.

### Two findings Codex surfaced mid-reasoning before it died — BOTH INDEPENDENTLY CONFIRMED by Claude

**F1 — the plan states the wrong selection procedure (real, but null in effect at K=7).**
The plan justified widening as "take ranks 4-7 of the frozen `ordered_draw.csv`". That is not the
procedure that built the frame. `risk/frame.py:385` `select_round_robin` runs "three locked rounds, with
cross-stratum 50-km sequential inhibition": a candidate is accepted only if
`all(distance_km(candidate, previous) >= FRAME_MIN_SEPARATION_KM)` against **every** already-selected site
(`FRAME_MIN_SEPARATION_KM = 50.0`, `risk/config.py:127`). Walking a raw rank order can therefore admit
candidates the real algorithm would have skipped for proximity.

Claude simulated the correct continuation to K=7 (haversine, 50 km, cross-stratum, against all 12
incumbents). **The inhibition never bites at these ranks:** all four strata add exactly ranks 4,5,6,7,
zero proximity skips, deepest rank needed = 7. So the two procedures coincide here and the 16 sites are
unchanged — but the plan still specifies the wrong rule, and the two would diverge at higher K.
*Fix: step 2/3 must say "continue `select_round_robin` at K=7 under the 50-km cross-stratum inhibition",
not "take ranks 4-7", and must record that this empirically yields ranks 4-7 with zero skips.*

**F2 — the downloader will refuse this download outright (hard blocker).**
`risk/download_timeseries.py` carries two deliberate guardrails from the retired study:
- **line 184-185:** `if len(frame_sites) != FRAME_REQUIRED or any(counts[group] != 3 ...)` →
  `RuntimeError("Pre-download manifest does not contain the locked 3x4 frame cohort.")` — a 28-site frame
  is rejected.
- **line 193-194:** `if int(year) > 2020 ... raise AssertionError("Post-2020 imagery reached download
  manifest")` — the 2021/2022 predictor years are blocked.
- **line 187:** each site's `periods` must equal `FEATURE_YEARS` exactly.

Constants to amend (`risk/config.py`): `FRAME_SITES_PER_GROUP = 3` (:126) → 7; `FRAME_REQUIRED = 12`
(:144) → 28; `FEATURE_YEARS = (2018, 2019, 2020)` (:48) → 2018-2022. `REFERENCE_YEAR = 2020` (:49) and
`COMBINED_MINIMUM = 14` (:145) need review, not blind edits.
The plan's step 5 assumed the hardened downloader would simply accept 28 sites and 2018-2022. It will not.
*Fix: add an explicit step amending these constants and the post-2020 assertion, with its own test pass,
before any download is attempted.*


---

## Round 1 — Codex (gpt-5.6-sol @ xhigh) — VERDICT: REVISE, 19 findings

_Resumed thread `019f7f9a-5503-7052-92c0-a54ac6c96bf4`. 1.21M input tokens, 10k reasoning tokens._

The plan is not sound enough to implement. The fixed draw order helps, but it does not cure the leaked test information, outcome-adaptive stopping, or the operational incompatibilities.

## Findings

1. **Critical — the embargo firewall is rhetorical, not technical.** The precheck loads the complete GFC-2024 `lossyear` raster—including 2023/2024 values—into an ordinary accessible array; `PERMITTED_ORIGINS` constrains later calculations, not what is read into memory, which is exactly how the prior breach occurred. [precheck_evaluability.py:52](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/precheck_evaluability.py:52>) [precheck_evaluability.py:142](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/precheck_evaluability.py:142>)

   **Fix —** Put raw GFC access behind a separately reviewed censoring boundary that exposes only loss-through-2022 masks, and add metamorphic tests proving arbitrary changes to 2023/2024 codes cannot change any returned value or output.

2. **Critical — widening does act on leaked test knowledge.** Keeping the tainted site prevents a direct label-based swap, but changing frame size after learning that site’s 2023 failure still changes training data, normalization, the global top-5% target, bootstrap composition, and reported estimates; the claim that a pure superset “does not act” on the leak is false. [FRAME-WIDENING-PLAN.md:119](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:119>)

   **Fix —** Log widening as a protocol deviation, report the original 12-site analysis unchanged, designate the widened result amended/secondary, and reserve confirmatory language for a genuinely untouched later endpoint or holdout.

3. **Critical — the hash freezes candidate order, not K.** Steps 2–3 choose the stopping point from 2021/2022 outcomes, so the final frame is an outcome-adaptively sized prefix; uniform K and “only increases” do not remove optional-stopping bias. This directly conflicts with the plan’s own rejection of outcome-sized frames. [FRAME-WIDENING-PLAN.md:39](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:39>) [FRAME-WIDENING-PLAN.md:124](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:124>)

   **Fix —** Freeze K before scoring ranks 4+, make their precheck strictly non-binding, or estimate quietness from a separate pilot cohort that can never enter the final frame.

4. **Critical — raw ranks are not the frozen selection algorithm.** `select_round_robin` accepts candidates sequentially only when they are at least 50 km from every previously retained site, including other strata; ranks 1–7 happen to leave all 28 sites separated, but raw rank 8 in `sea_peat` is only about 24.5 km from rank 1, so the proposed escalation immediately diverges from the registered algorithm. [frame.py:390](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/frame.py:390>) [FRAME-WIDENING-PLAN.md:51](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:51>)

   **Fix —** Replay the exact cross-stratum sequential-inhibition algorithm, define K as retained sites rather than raw rank, and record every skipped rank and distance decision.

5. **High — the K escalation rule is incomplete and contradicts the rest of the plan.** “Raise K” specifies neither increment, maximum, nor failure action, while every downstream figure remains hard-coded for K=7: 28 sites, 16 additions, 104 site-years, 37 GB, and 756 fits.

   **Fix —** Freeze `K_max`, increment and terminal failure rules before prechecking, then parameterize downstream quantities as `n=4K`, new-download site-years `20K−36`, and inner fits `4K(4K−1)`.

6. **High — K=7 does not provide the claimed one-site margin with 95% joint probability.** At independent quiet probability 0.25, K=7 gives 94.95% joint probability that all four strata merely retain three evaluable sites; four quiet sites leave exactly zero slack, while the joint probability of at least four evaluable sites per stratum is only 74.63%. K=9, not 7, crosses 95% for that stated slack criterion under the same assumptions. [FRAME-WIDENING-PLAN.md:49](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:49>) [FRAME-WIDENING-PLAN.md:124](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:124>)

   **Fix —** Relabel 95% as zero-slack gate survival or size K against the actual “≥1 site of slack in every stratum” target.

7. **High — “observed quiet rate” is undefined and too weak to validate the 25% assumption.** The plan does not say whether a site is quiet based on 2022 alone, either permitted year, both years separately, or the worst year; with only four additions per stratum, even zero quiet sites gives a one-sided 95% upper rate of about 52.7%, and pooling 16 sites assumes homogeneous independent strata.

   **Fix —** Define the estimand and temporal unit exactly, report stratum-specific uncertainty and dependence assumptions, and present survival as a sensitivity curve rather than a measured guarantee.

8. **High — Step 3 checks only one of the regional gate’s three conditions.** Four evaluable sites can contribute as few as 20 components, below the ≥30 gate, and no GFC-only precheck establishes the bootstrap half-width ≤0.10; therefore widening cannot yet be said to restore the complete regional gate. [FORECAST-PLAN.md:224](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:224>)

   **Fix —** Require ≥30 projected components on each permitted origin and describe the amendment as restoring site-count margin only unless a prespecified permitted-origin precision analysis also supports the half-width gate.

9. **High — the n-dependent amendment inventory is incomplete.** It misses the scientific-scope claim of “~3–5 sites/biome,” misses inner cross-fitting’s “other 10” sites, and does not instantiate bootstrap `S`; these become approximately 7, 26, and respectively 28 pooled/7 regional. [FORECAST-PLAN.md:13](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:13>) [FORECAST-PLAN.md:238](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:238>) [FORECAST-PLAN.md:280](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:280>)

   **Fix —** Add these substitutions to Step 4 and explicitly classify unchanged 3-valued constants such as the evaluable-site gate and SAR pilot so a mechanical replacement cannot corrupt them.

10. **High — the RNG amendment still lacks the exact new key map.** For analysis code 6, `unit_index=2×fold+architecture` now spans 0–55, not 0–27; adding lexicographically interleaved site IDs also changes old sites’ fold indices, so reproducibility requires the final site-to-fold mapping, not merely a wider range. [FORECAST-PLAN.md:162](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:162>)

   **Fix —** Freeze and serialize the complete `site_id → fold_index → code-6 unit_index` table after K is fixed, with collision and order-invariance tests for every analysis code.

11. **High — the §4 audit treatment is not complete.** Holding `n_b=180` while expanding from three to seven possible site strata reduces average allocation from about 60 to 25.7 per site and can increase the survey SE that directly hardens the retention gate; “floors rise from 6 to 14” is only true when all seven sites are non-census strata, and actual allocations cannot be known until test-positive counts exist. [FORECAST-PLAN.md:91](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:91>) [FRAME-WIDENING-PLAN.md:76](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:76>)

   **Fix —** Explicitly freeze whether 180 is retained, assess prospective precision under seven strata, and test the generic variance/allocation code for `N=0`, censuses, floors, caps, redistribution, FPC, and seven-stratum summation.

12. **High — the precheck can silently select K from incomplete or incorrectly mosaicked GFC data.** A failed required seam tile is ignored whenever another tile succeeds, and seam pieces are concatenated by shape without transform-aware placement or full-coverage assertions, potentially splitting or joining components incorrectly. [precheck_evaluability.py:99](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/precheck_evaluability.py:99>)

   **Fix —** Fail closed on every required tile, use transform-aware mosaicking, assert identical layer grids and complete bbox coverage, and add north/south, east/west, and four-tile seam tests.

13. **High — the precheck may select K using a different GFC release from the final study.** The script explicitly pins v1.12 “for the precheck only,” while the study’s version and checksums are deferred; historical loss layers can be revised, so frame selection and final labels could disagree. [precheck_evaluability.py:52](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/precheck_evaluability.py:52>)

   **Fix —** Freeze the exact study GFC release and required tile checksums before any new candidate is scored, verify the candidate/order hashes on every run, and require a one-to-one rank/candidate join.

14. **Critical operational blocker — `risk/download_timeseries.py` cannot execute Step 5.** It requires exactly 12 frame sites with three per group, requires each manifest to contain exactly `FEATURE_YEARS=(2018,2019,2020)`, rejects post-2020 periods, and loops over every manifest site; changing the global tuple to five years would also conflate archive availability with the forecast’s rolling three-year histories and likely download unwanted legacy years. [download_timeseries.py:182](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:182>) [download_timeseries.py:476](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:476>) [config.py:48](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/config.py:48>)

   **Fix —** Introduce a forecast-specific immutable site-year download schedule, decouple archive years from model-history years, validate 28/7-per-stratum, and restrict downloads to the stated 104 missing frame site-years.

15. **High — no step creates the widened frozen manifest.** New candidates need CHIRPS-derived seasonal windows, 2018–2022 periods, cohort labels, rank/provenance fields, and a new hash, but `finalize_analysis_sites` reconstructs only the original selected list and only the global `FEATURE_YEARS`. [frame.py:472](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/frame.py:472>)

   **Fix —** Specify a deterministic amendment-manifest builder that replays selection, computes all new seasonal periods, preserves the original artifact hashes, and freezes the resulting 28-site manifest before downloading.

16. **High — the repo-wide n migration is omitted.** Reused code still fixes `FRAME_SITES_PER_GROUP=3`, `FRAME_REQUIRED=12`, cohort counts of three, and LOSO requirements of 12/11; the plan amends prose but does not state whether these paths are updated or excluded. [config.py:125](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/config.py:125>) [cohort.py:44](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/cohort.py:44>) [models.py:183](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/models.py:183>)

   **Fix —** Inventory every reused frame-size assertion and test, then either parameterize it from the frozen forecast manifest or explicitly prove the module is outside the active implementation path.

17. **High — the proposed integrity check is not a completeness gate.** `verify_composites.py` scans whatever TIFFs happen to exist, cannot detect missing site-years, checks neither expected band counts nor provenance, includes unrelated sites, and exits successfully even after recording corrupt files; a partial archive can therefore “pass.” [verify_composites.py:21](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/census/verify_composites.py:21>) [verify_composites.py:53](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/census/verify_composites.py:53>)

   **Fix —** Verify the manifest-derived final inventory of 560 frame TIFFs—416 newly downloaded—with exact band schemas, provenance and decode checks, and return nonzero for missing, corrupt, or all-nodata artifacts.

18. **High — a partially downloaded lower-K frame is not “usable.”** Step 3 freezes K before downloading, so later analyzing a smaller prefix because downloads failed would be an availability-driven protocol deviation, even if staging is strata-balanced. [FRAME-WIDENING-PLAN.md:100](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:100>)

   **Fix —** Treat every partial archive as resumable but non-analysable; only the complete frozen-K manifest may enter preprocessing or inference.

19. **Medium — the 5.7× compute estimate materially understates work.** Fit count rises 5.7×, but each inner fit grows from roughly 10 training sites to 26, making linear site-fit work about `(756×26)/(132×10) ≈ 14.9×`, before deep architectures, ablations, tuning and two scales.

   **Fix —** Benchmark representative full folds and freeze runtime/storage limits plus a scientifically valid failure action before committing to K.

VERDICT: REVISE
### Claude's response — round 1

**All 19 findings accepted. None rejected.** Two were independently re-derived before acceptance rather
than taken on trust, and both of Codex's numbers were exact:

- **#6 verified.** Binomial at p_quiet=0.25, K=7: P(≥3 evaluable)=0.98712 per stratum → **0.94947** joint;
  P(≥4 evaluable)=0.92944 → **0.74626** joint. Codex's 94.95% / 74.63% confirmed to five digits. **The v1
  plan text was wrong** — it advertised the zero-slack figure as if it were the one-slack margin. One-slack
  survival by K: K=7 → 74.6%, K=8 → 89.5%, **K=9 → 96.1%**, so Codex's "K=9, not 7" is right.
- **#4 verified.** `sea_peat` rank 8 (`F4_M003.120_P0105.500`) is **24.46 km** from rank 1 — inside the
  50 km inhibition radius. Codex's ~24.5 km confirmed. At K=7 inhibition never binds (all strata retain
  exactly ranks 4-7, zero skips), so v1's shortcut was accidentally correct; at K≥8 it breaks immediately.

**One partial counter-argument, logged rather than used to dismiss the finding (#2).** The *trigger* to
widen was the 2022 **validation** failure (`amazon_moist` 2/3), which is permitted information under §F,
and that failure justifies widening independently of the leak. But this does not rescue v1's claim that a
pure superset "does not act on" the leak: the leaked fact was known when K was chosen, and frame size
changes training data, normalization, the top-5% target set, and bootstrap composition. **v1's claim is
withdrawn as false.** Codex's remedy is adopted as the default.

**Two findings escalated to Josh rather than silently resolved by Claude**, because both change what the
paper reports and neither is Claude's call:
- **(A) #2** — adopted default: log as protocol deviation, 12-site analysis stays **primary**, 28-site
  result is **amended/secondary**.
- **(B) #6** — adopted default: keep **K=7** and relabel the claim honestly as zero-slack survival. K=9
  buys real slack for ~14 GB more. Josh chose K=7 over K=6 *to buy margin*, so the corrected number may
  change his choice.

**Structural change in v2:** every downstream quantity is now parameterized in K (**sites = 4K**,
**new site-years = 20K−36**, **inner fits = 4K(4K−1)**), so Josh's (B) decision drops in without a rewrite.

**Changes made, by finding:** #1 technical censoring boundary at read time + required metamorphic tests
(replacing the rhetorical `PERMITTED_ORIGINS` firewall); #2 see (A); #3 K/K_max/failure-action frozen
before any new candidate is scored, precheck made strictly non-binding; #4 replay `select_round_robin`,
K counts *retained* sites, skipped ranks recorded with distances; #5 parameterization above + frozen K_max;
#6 see (B); #7 "quiet" defined as worst permitted origin, uncertainty reported, survival presented as a
sensitivity curve (zero observed quiet still leaves a ~52.7% upper bound); #8 scope narrowed to the
site-count arm only, since GFC-only cannot establish ≥30 components or half-width ≤0.10; #9 inventory
extended (scope claim line 13, inner "other 10" line 238, bootstrap S line 280) plus an explicit
do-not-replace list for unrelated 3-values; #10 full `site_id → fold_index → code-6 unit_index` table to be
frozen and serialized, noting code 6 spans 0–55 and that insertion renumbers existing folds; #11 §4
allocation must be frozen and prospective precision assessed, with the warning that widening can *harden*
the retention gate; #12 fail-closed transform-aware mosaicking + seam tests; #13 study GFC release and tile
checksums pinned before scoring; #14 forecast-specific immutable site-year schedule replacing global
constant edits; #15 deterministic amendment-manifest builder (CHIRPS windows, periods, hashes); #16
repo-wide inventory of frame-size assertions with parameterize-or-prove-excluded; #17 manifest-derived
completeness gate (560 TIFFs at K=7, 416 new) with nonzero exit; #18 partial archive resumable but
non-analysable; #19 compute re-baselined at ~14.9× site-fit work, benchmark before committing.


---

## Round 2 — Codex — VERDICT: REVISE, 10 findings (down from 19)

The two conservative defaults are scientifically defensible, but v2 still has several material inconsistencies to close before implementation.

The counter-argument for (A) is not wrong: the permitted 2022 validation failure is independently sufficient reason to consider widening. It remains only a counterfactual mitigation—the leak was known when K was chosen—and changing the frame after validation is still a protocol deviation under the original freeze. The adopted 12-site-primary/widened-secondary treatment handles that appropriately.

The default for (B) is also defensible: K=7 can be retained as a resource-constrained secondary design if 94.95% is presented only as an IID scenario for zero-slack gate survival, not as evidence that margin was restored.

## Remaining findings

1. **Critical — the censoring boundary may still expose the test labels.** Mapping every `lossyear > 22` value to a distinct sentinel reveals exactly which pixels suffer post-2022 loss; perturbing 23 to 24 would leave that leak unchanged and still pass the proposed metamorphic test. [FRAME-WIDENING-PLAN.md:71](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:71>)

   **Fix —** Return only derived loss-through-2022 boolean masks, collapse every post-2022 value into the same state as “not lost through 2022,” and test invariance to moving, adding and removing future-loss pixels—not merely changing 23/24 codes.

2. **High — default (A) is not propagated into the analysis specification.** The plan says the original 12-site analysis remains unchanged and primary, but Step 6 replaces its sample-size constants and renumbers its frozen RNG folds; that would leave only the widened specification and would change the primary’s draws. [FRAME-WIDENING-PLAN.md:21](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:21>) [FRAME-WIDENING-PLAN.md:141](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:141>)

   **Fix —** Preserve `FORECAST-PLAN.md` v11, its 12-site fold map and RNG streams verbatim for the primary analysis, and define the 4K-site secondary as a separately named specification with separate manifests, seed maps and result namespaces.

3. **High — default (B) conflicts with the title and goal.** Under K=7 the adopted claim is zero-slack survival, yet the title and Goal still say the amendment “restore[s] margin,” while the scope paragraph correctly says it cannot establish the regional gate. [FRAME-WIDENING-PLAN.md:1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:1>) [FRAME-WIDENING-PLAN.md:54](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:54>)

   **Fix —** Under the K=7 default, replace remaining “restore/buy margin” language with “increase site-count resilience” and reserve “margin” for an observed or explicitly probabilistic ≥1-slack result.

4. **High — K_max and the failure rule remain unresolved third decisions.** Step 3 says they will be frozen but supplies no values, and “stop and re-plan” could still enlarge K using the newly observed candidate outcomes; logging that change would disclose optional stopping, not cure it. [FRAME-WIDENING-PLAN.md:98](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:98>)

   **Fix —** For the default set `K=K_max=7`, no increment, and a terminal action of abandoning the widened analysis; if a later amendment uses these precheck outcomes to enlarge K, classify that result as outcome-adaptive exploratory work.

5. **High — the 52.7% uncertainty statement is not parameterized correctly.** That bound is for zero quiet among the `K−3=4` additions in one stratum at K=7, not among all `4K−12=16` additions; at K=9 the corresponding stratum-specific bound is about 39.3%. [FRAME-WIDENING-PLAN.md:120](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:120>)

   **Fix —** State the stratum-specific bound as `1−0.05^(1/(K−3))`, give K-specific examples, and report any pooled bound separately with its homogeneity assumption.

6. **High — “worst of two years” is not the quiet probability used in the survival calculation.** A probability that a site is quiet in at least one of two historical years is not the single-year quiet probability for 2023, so it cannot be inserted into the K=7 binomial curve without changing the estimand.

   **Fix —** Keep worst-of-two as a conservative non-binding stability diagnostic, report each origin separately, and label the survival curve’s `q` as an assumed single-test-year rate rather than an estimate from the worst-of-two indicator.

7. **High — the n-dependent inventory is still incomplete and not actually parameterized throughout.** It still omits “each of the 11 non-held-out sites” → `4K−1`, while several rows use 28/27/7 rather than formulas; the RNG range is `0…8K−1`, not generally 0–55. [FORECAST-PLAN.md:238](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FORECAST-PLAN.md:238>) [FRAME-WIDENING-PLAN.md:143](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:143>)

   **Fix —** Express every substitution as a K formula—`4K`, `4K−1`, `4K−2`, pooled `S=4K`, regional `S=K`, and code-6 indices `0…8K−1`—with K=7/K=9 examples only in a separate column.

8. **High — the audit budget remains an unacknowledged unresolved decision.** Section 6 still says to “freeze whether 180 is retained,” despite the user identifying only decisions (A) and (B), and it assesses seven strata even though K=9 remains an option. [FRAME-WIDENING-PLAN.md:169](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:169>)

   **Fix —** Adopt and state a default now—most conservatively retain frozen `n_b=180`—and parameterize the precision assessment for K strata, conditional floors up to `2K`, and mean allocation `180/K`.

9. **High — the widened manifest omits 2021/2022 periods for the existing 12 sites.** Step 7 adds 2018–2022 periods only for new candidates, but the explicit download schedule and final five-year completeness inventory also require frozen 2021/2022 seasonal periods for every incumbent frame site. [FRAME-WIDENING-PLAN.md:179](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:179>)

   **Fix —** Have the amendment builder extend periods through 2022 for all 4K frame sites, then derive the missing-pair schedule by subtracting already verified artifacts.

10. **Medium — the compute gate has impossible ordering.** Step 3 commits K before new candidates are scored, while Step 12 requires representative full-fold benchmarking before K is committed; a real widened fold cannot be benchmarked before its data are downloaded. [FRAME-WIDENING-PLAN.md:104](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:104>) [FRAME-WIDENING-PLAN.md:241](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:241>)

   **Fix —** Freeze K scientifically first, conduct the compute pilot as a non-binding feasibility gate, and predeclare that failure abandons or delays the widened analysis rather than changing K or the model after seeing candidate outcomes.

The selection replay, GFC pinning/mosaicking requirements, download-schedule separation, repo-wide assertion inventory, completeness gate, partial-archive prohibition, and revised compute scaling otherwise address the corresponding round-1 findings at plan level.

VERDICT: REVISE
### Claude's response — round 2

**All 10 findings accepted. None rejected.** Codex also validated both escalated defaults as scientifically
defensible and confirmed Claude's (A) counter-argument is not wrong — the permitted 2022 validation failure
is independently sufficient reason to consider widening; it is a counterfactual mitigation, not a cure, so
the deviation classification stands.

Formulas re-derived before acceptance, all confirmed: `1 − 0.05^(1/(K−3))` = **0.5271 at K=7**, **0.3930 at
K=9**; code-6 RNG range `0…8K−1` = **0–55 at K=7**, 0–71 at K=9.

**The most important catch: v2's own leakage fix still leaked (#1).** v2 censored `lossyear > 22` to "a
sentinel" — but a *distinct* sentinel identifies exactly which pixels suffered post-2022 loss, and
`positive = lossyear == 23` **is** the test label. The metamorphic test v2 specified (perturb 23→24) would
have passed while the leak sat untouched. This is the second time a proposed firewall for this script has
been shown to leak. v3 returns **boolean masks only**, collapses every post-2022 value into the same state
as "not lost through 2022", and tests invariance to **moving, adding, and removing** future-loss pixels.

**Second most important (#2): default (A) was declared but not propagated.** v2 kept the 12-site analysis
"primary" while §6 simultaneously rewrote its constants and renumbered its frozen RNG folds — which would
have destroyed the primary it claimed to preserve. v3 preserves `FORECAST-PLAN.md` v11, its fold map and
its RNG streams **verbatim**, and defines the widened design as **Specification W** with its own manifest,
seed map, fold table, and result namespace. No artifact or seed stream is shared.

**A third decision (C) surfaced and was defaulted (#8):** the §4 audit budget. `n_b = 180` was frozen for 3
strata per biome; at K strata mean allocation falls to `180/K`, raising the survey SE that feeds the
retention gate. **Default adopted: retain the frozen 180**, with the precision assessment parameterized for
K strata, floors up to `2K`, and mean allocation `180/K`. Josh may override — it now joins (A) and (B) at
sign-off.

**Other changes:** #3 all "restore/buy margin" language replaced with "increase site-count resilience", with
"margin" reserved for an explicit ≥1-slack result (title and Goal both corrected); #4 `K = K_max = 7`, no
increment, terminal action **abandon** the widened analysis, plus an explicit statement that disclosure does
not cure optional stopping and any later K enlargement using these outcomes is exploratory; #5 the bound is
stratum-specific over `K−3` additions, stated as a formula with both K values; #6 worst-of-two is kept as a
non-binding diagnostic only, each origin reported separately, and the survival curve's `q` explicitly
labelled an assumed single-test-year rate that must never be estimated from the worst-of-two indicator;
#7 every substitution now expressed as a K formula with numeric columns as illustration only, including the
previously missed `4K−1` at line 238; #9 the manifest builder extends periods through 2022 for **all** 4K
sites, incumbents included, then derives the schedule by subtraction; #10 compute pilot reordered to a
non-binding feasibility gate *after* K is frozen, with failure delaying or abandoning rather than resizing.


---

## Round 3 — Codex — VERDICT: REVISE, 6 findings (19 -> 10 -> 6)

**All three escalated defaults (A), (B), (C) judged scientifically defensible as written.**
Round-2 findings 4-10 confirmed substantively addressed.

Defaults (A), (B), and (C) are scientifically defensible as written:

- **A:** Preserving the 12-site specification as primary and treating Specification W as secondary is appropriately conservative.
- **B:** K=7 is defensible as a resource-constrained secondary design when 94.95% is presented only as an IID zero-slack scenario.
- **C:** Retaining `n_b=180` is defensible because it preserves the frozen audit budget and makes imprecision harder—not easier—to pass through the retention gate.

Round-2 findings 4–10 are substantively addressed. The revised bound, quiet-rate distinction, K formulas, audit decision, incumbent periods, and compute ordering are correct. Several material issues remain.

1. **Critical — the firewall still lacks capability isolation.** The boolean transformation is now mathematically non-leaking, but the raw `lossyear` array still exists inside a module running in the same Python process; a debugger, ad-hoc print, exception-local dump, monkeypatch, or direct `rasterio.open` elsewhere can expose it exactly as before. “Only code permitted” is a convention, not a technical boundary. [FRAME-WIDENING-PLAN.md:110](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:110>)

   **Fix —** Run the reviewed raw-access/censoring utility as a separate non-interactive process whose only persistent output is the allow-listed boolean masks, then run the precheck without network or filesystem access to the raw GFC rasters.

2. **High — Specification W does not actually have a distinct RNG namespace.** The plan requires that no seed stream be shared, but Specification W still inherits seed 42 and the same `(analysis_code, unit_index, replicate)` key structure; primary fold 0 and W fold 0 therefore instantiate identical streams despite having separate fold tables. [FRAME-WIDENING-PLAN.md:42](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:42>) [FRAME-WIDENING-PLAN.md:219](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:219>)

   **Fix —** Give Specification W a frozen specification coordinate or distinct root entropy, such as `(specification_code, analysis_code, unit_index, replicate)`, while leaving the primary’s original key scheme untouched.

3. **High — “no artifact shared” conflicts with the download design and storage accounting.** Both specifications require the same immutable incumbent composites, particularly the 24 missing 2021/2022 site-years, while the 104-site-year calculation assumes those inputs are downloaded once; literal artifact isolation would require duplicate storage or downloads. [FRAME-WIDENING-PLAN.md:46](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:46>) [FRAME-WIDENING-PLAN.md:278](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:278>)

   **Fix —** Permit both specifications to reference the same checksum-pinned read-only raw composites, while prohibiting sharing of manifests, fitted state, normalization, RNG artifacts, predictions and result paths.

4. **High — the prohibited margin claim remains in two places.** The scope paragraph still says the amendment “restores” the evaluable-site condition, and the risk section says larger K “buys margin,” contradicting the binding K=7 language rule. [FRAME-WIDENING-PLAN.md:91](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:91>) [FRAME-WIDENING-PLAN.md:339](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:339>)

   **Fix —** Replace those statements with “targets/increases resilience of the evaluable-site condition”; use “margin” only for a demonstrated or explicitly probabilistic ≥1-slack result.

5. **Medium — the audit precision direction is overstated.** Reducing mean observations per site can raise survey SE, but it does not necessarily do so: adding strata can improve precision when strata are internally homogeneous, and the target population also changes. The later “may harden” wording is correct; the categorical “raises” wording is not. [FRAME-WIDENING-PLAN.md:70](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:70>) [FRAME-WIDENING-PLAN.md:227](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:227>)

   **Fix —** Change “raises the survey SE” to “can raise the survey SE” and let the frozen stratified variance calculation determine the actual direction.

6. **Low — the sign-off heading still says two decisions although A, B, and C now require sign-off.** [FRAME-WIDENING-PLAN.md:15](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:15>)

   **Fix —** Rename the heading to “THREE ITEMS REQUIRING JOSH’S SIGN-OFF.”

The mask semantics and strengthened relocation/addition/removal tests now close the data-transformation leak itself; the remaining critical firewall problem is that raw access has not been isolated from the interactive scoring process.

VERDICT: REVISE
### Claude's response — round 3

**All 6 findings accepted. None rejected.**

**#1 is the third distinct leak vector found in this one script**, and it is the most instructive. v1's
firewall was rhetorical (`PERMITTED_ORIGINS` constrained arithmetic, not reads). v2's fix leaked through
distinct sentinel values. v3's mask semantics closed the transformation itself — and Codex correctly points
out the raw `lossyear` array *still lives in the same Python process*, reachable by debugger, stray print,
exception dump, monkeypatch, or any other `rasterio.open`. "Only this module may open GFC rasters" is a
naming convention, not a boundary. v4 requires **capability isolation**: the censoring utility runs as a
separate non-interactive process whose only persistent output is allow-listed boolean masks, and the
precheck then runs with **no network or filesystem access to the raw rasters at all**. The plan now states
explicitly that a fourth vector should be assumed until isolation is demonstrated.

**#2 was a real hole in (A)'s propagation.** Specification W had its own fold table but still inherited
`SEED = 42` and the same `(analysis_code, unit_index, replicate)` key, so primary fold 0 and W fold 0 would
have produced *identical* streams. v4 adds a frozen `specification_code` coordinate to W's key while
leaving the primary's scheme untouched.

**#3 corrected an over-reach of Claude's own.** "No artifact shared" was too strong: both specifications
need the same incumbent composites, and the 20K-36 accounting assumes each site-year is downloaded once, so
literal isolation would force duplicate downloads for no scientific gain. v4 permits shared
**checksum-pinned read-only raw composites** while prohibiting shared manifests, fitted state,
normalization, RNG artifacts, predictions, and result paths.

**#5 is Codex correcting an overstatement Claude imported from Codex's own round-1 #11.** r1 said widening
"can increase" survey SE; v3 hardened that to "raises". That was wrong in both directions of certainty —
adding strata can *improve* precision when strata are internally homogeneous, and the target population
changes as well. v4 reverts to "can raise" and defers the direction to the frozen stratified variance
calculation. Worth noting that the adversarial process caught Claude over-claiming a *risk*, not just
under-claiming one.

**#4 and #6** were straightforward: two surviving "restore/buys margin" violations of the plan's own
binding language rule (scope paragraph and risks section), and a heading still reading "TWO ITEMS" after
(C) was promoted. Both fixed, plus a third instance found by Claude's own grep sweep — the (B) block
described Josh's K=7 choice as buying margin, now reworded to state that it was chosen *on the mistaken
understanding* that it purchased one-slack margin.


---

## Round 4 — Codex — VERDICT: REVISE, 4 findings (19 -> 10 -> 6 -> 4)

**Codex states it found NO new material defect in the K calculations, sequential-inhibition replay,
audit default, sample-size substitutions, manifest/download accounting, or primary-vs-secondary
statistical treatment.** The scientific design is converged; all four remaining items are
implementation-contract or provenance issues.

The defaults for A, B, and C remain scientifically defensible. Round-3 findings 3–6 are addressed, and the statistical/sample-size design is now internally consistent. Two firewall details and one RNG freeze remain material.

1. **Critical — process separation is specified, but isolation is not yet testable or enforceable.** A privileged child process can still leak raw labels through stdout/stderr, exception tracebacks, crash dumps, temporary files, or unexpected files in its output directory; “only persistent output” does not cover these transient channels. [FRAME-WIDENING-PLAN.md:136](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:136>)

   **Fix —** Require an OS-enforced sandbox, an empty/sanitized stdout-stderr contract, disabled core dumps, an exclusive temporary directory destroyed after success, an exact output-file allow-list, and integration tests that deliberately attempt raw-path and network access from the precheck and require failure.

2. **High — the boolean-mask handoff schema is not concrete enough to prove the isolated precheck can run.** Scoring needs aligned population/eligibility and positive masks plus CRS/transform metadata; meanwhile transform-aware mosaicking and raw-tile checksum verification must now occur inside the privileged utility, not in the unprivileged precheck. Without an exact allow-list, implementation may reintroduce raw `treecover2000`, `datamask`, or `lossyear` access to fill the gap. [FRAME-WIDENING-PLAN.md:145](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:145>) [FRAME-WIDENING-PLAN.md:217](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:217>)

   **Fix —** Freeze the exact output schema—such as aligned boolean `eligible_2020`, `eligible_2021`, `eligible_2022`, `positive_2021`, and `positive_2022` masks with safe georeferencing—and assign all raw checksum, coverage, and mosaicking responsibilities to the isolated utility.

3. **High — `specification_code` is still not actually frozen.** The plan says to “give W” a coordinate “or” use distinct root entropy, but supplies neither a numeric code nor a selected alternative; therefore Specification W’s promised RNG namespace remains unresolved. [FRAME-WIDENING-PLAN.md:49](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:49>)

   **Fix —** Choose and record one exact scheme now, for example `specification_code=1` with W’s key fixed as `(1, analysis_code, unit_index, replicate)`, and add cross-specification collision tests.

4. **Low but provenance-relevant — the purported v4 file still identifies itself as v3.** In a study already tracking multiple deviations and specifications, incorrect version metadata can cause the wrong plan to be cited or implemented. [FRAME-WIDENING-PLAN.md:2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:2>)

   **Fix —** Update the document header to v4 and include round 3 in its revision provenance.

I found no new material defect in the K calculations, sequential-inhibition replay, audit default, sample-size substitutions, manifest/download accounting, or primary-versus-secondary statistical treatment.

VERDICT: REVISE
### Claude's response — round 4

**All 4 findings accepted. None rejected. Running total: 39 findings, 39 accepted, 0 rejected.**

**#1 — isolation was declared but not enforceable.** v4 said "separate process, only persistent output is
masks", which does not cover transient channels: stdout/stderr, exception tracebacks, crash dumps, temp
files, stray output files. v5 specifies a binding contract — OS-enforced sandbox, sanitized stdout/stderr
with tracebacks replaced by non-data-bearing error codes, core dumps disabled, exclusive temp directory
destroyed on success, exact output-file allow-list with any extra file a hard failure, and **integration
tests that deliberately attempt raw-path and network access from the precheck and require failure**. An
isolation claim with no test that tries to break it is not evidence of isolation.

**#2 — the handoff schema was the hole that would have undone #1.** Without an exact allow-list, an
implementer finding the masks insufficient would simply reopen `treecover2000`/`datamask`/`lossyear` to
fill the gap, reintroducing the vector through the front door. Frozen schema: aligned boolean
`eligible_2020/2021/2022` and `positive_2021/2022` plus CRS/transform/shape, nothing else, and
**deliberately no `positive_2023`**. Raw-tile checksums, coverage assertions and transform-aware
mosaicking all move INSIDE the privileged utility, since the unprivileged precheck cannot see raw tiles.

**#3 — `specification_code` was written as "a coordinate OR distinct root entropy", which freezes nothing.**
A choice offered is not a choice made. Frozen: W's key is `(1, analysis_code, unit_index, replicate)`; the
primary keeps its three-coordinate key verbatim; cross-specification collision tests required.

**#4 — the file still called itself v3.** Corrected to v4 with full round provenance. Minor, but in a study
already tracking multiple specifications and deviations, wrong version metadata is how the wrong plan gets
implemented.


---

## Round 5 (FINAL under MAX_ROUNDS=5) — Codex — VERDICT: REVISE, 3 findings

The four round-4 findings are addressed, and A/B/C remain defensible. The scientific/statistical design is otherwise converged. One concrete fourth leakage vector remains in the failure path.

1. **Critical — a failed isolation run can leak before the contract rejects it.** An accidental raw-array print reaches stdout before a post-run “empty stream” check can fail, and the exclusive temporary directory is destroyed only on success; crashes, timeouts, or validation failures can therefore expose console output or leave raw-derived files behind. [FRAME-WIDENING-PLAN.md:136](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:136>)

   **Fix —** Have a trusted supervisor redirect child stdout/stderr into a sealed, never-rendered sink and validate only byte counts, emit its own fixed error codes, and destroy the sandbox/temp directory after every termination path—including failure, crash, timeout, and forced kill.

2. **High — the isolation lifetime conflicts with the eventual test opening.** The plan says the precheck “and every downstream consumer” can never access raw GFC, but both specifications ultimately require the 2023 outcome after all parameters are frozen; without an explicit phase boundary, either final evaluation is impossible or someone will relax the sandbox informally. [FRAME-WIDENING-PLAN.md:140](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/FRAME-WIDENING-PLAN.md:140>)

   **Fix —** State that raw-GFC denial governs the entire frame/precheck/tuning phase, then define a separately logged one-time embargo-lift transition for final 2023 evaluation only after both specifications and all frozen artifacts are sealed.

3. **Medium — the handoff names are frozen but their pixel formulas are not.** “Outcomes at the permitted origins” could be implemented as raw `lossyear==21/22`, which would count losses outside the frozen forest population and change component totals.

   **Fix —** Freeze `eligible_T = datamask==1 ∧ treecover2000≥30 ∧ no loss through T` and `positive_T+1 = eligible_T ∧ lossyear==T+1` explicitly for every emitted mask.

I found no remaining defect in K selection, sequential inhibition, probability calculations, audit allocation, RNG namespace, manifest/download accounting, or primary-versus-secondary treatment.

VERDICT: REVISE
### Claude's response — round 5

**All 3 findings accepted. None rejected. FINAL TOTAL: 42 findings across 5 rounds, 42 accepted, 0 rejected.**

**#1 — the failure path was the fourth leak vector, exactly as predicted.** v4's contract validated that
stdout/stderr were empty *after* the run; an accidental raw-array print has already hit the console by
then. And the exclusive temp directory was destroyed **only on success**, so any crash, timeout, or
validation failure left raw-derived files on disk. v5: a trusted supervisor redirects the child's streams
into a **sealed sink that is never rendered**, validating byte counts only and emitting its own fixed
error codes; the temp directory is destroyed on **every** termination path including forced kill.

**#2 — a design gap Claude missed entirely, and the most valuable finding of the round.** v4 said raw-GFC
denial binds "every downstream consumer" without qualification. But both specifications must eventually
read the 2023 outcome to produce any result at all, so the plan as written made final evaluation
*impossible* — which in practice means someone quietly relaxes the sandbox at the worst possible moment.
v5 defines an explicit phase boundary: denial is absolute through frame selection, precheck, tuning,
calibration and freezing; a **separately logged one-time embargo-lift transition** permits final evaluation
only after both specifications and every frozen artifact are sealed, recorded with timestamp and
sealed-artifact hashes.

**#3 — frozen names are not frozen semantics.** "Outcomes at the permitted origins" could have been
implemented as raw `lossyear == 21/22`, counting losses outside the frozen forest population and silently
changing component totals. v5 freezes the pixel formula for every emitted mask, matching FORECAST-PLAN §4.

## Resolution — MAX_ROUNDS reached WITHOUT approval (not faked)

`MAX_ROUNDS=5` is exhausted and the last verdict is **REVISE**, so this chain did **not** converge to
`APPROVED`. Per the skill's hard rule, that is reported as-is rather than dressed up as convergence.

**But this is not the deadlock the rule was written for.** A deadlock means unresolved disagreement; here
there is none. Every one of the 42 findings was conceded, Claude holds **zero** counter-positions, and the
only argument Claude did advance (round 1 #2, that the widening trigger was the permitted 2022 validation
failure) was logged as mitigation and explicitly *not* used to dismiss the finding — Codex then confirmed
it was correct but non-exculpatory.

Findings per round: **19 -> 10 -> 6 -> 4 -> 3**, and from round 3 onward Codex repeatedly recorded that it
found **no remaining defect in K selection, sequential inhibition, probability calculations, audit
allocation, RNG namespace, manifest/download accounting, or primary-versus-secondary treatment.** Every
round-5 finding lies inside the leakage-firewall implementation contract, which is the single hardest part
of this plan and has now been rebuilt four times (rhetorical -> sentinel -> in-process array -> failure
path). The v5 fixes are applied but **unreviewed by Codex**.

**Josh's options at sign-off:** (i) authorise additional rounds to review v5 and seek APPROVED;
(ii) sign off on v5 as-is, accepting that the last three fixes carry no cross-model review;
(iii) revise scope. Claude's recommendation is **(i)** — the firewall has leaked on every single previous
attempt to close it, and that is not a track record that justifies stopping one round early.

---

## JOSH'S DECISIONS — 2026-07-20. MAX_ROUNDS extended 5 -> 7.

Claude's recommended default was **overridden on both (A) and (B)**. Recorded as Josh's calls.

**(A) OVERRIDDEN — Specification W (widened, 4K sites) is the PRIMARY result**, 12-site analysis secondary,
with prominent main-text disclosure of the deviation. Claude had recommended 12-site-primary and Codex had
validated that default across rounds 2-5; **this reversal is UNREVIEWED and is a first item for round 6.**
Consequence stated in the plan: the primary result is causally downstream of a known test-label leak.

**(B) OVERRIDDEN — `K = K_max = 9`, frozen.** Josh took the K=9 option once the corrected probabilities were
on the table, having originally chosen K=7 believing it bought one-slack margin. K=9 is the smallest K with
>=1-slack survival above 95% (96.1%).

**The K=9 replay vindicates Codex r1 #4 — the inhibition finding was not academic.** Replaying
`select_round_robin` at K=9:

| Stratum | Retained ranks | Skipped |
|---|---|---|
| amazon_moist, congo_moist, dry_forest | 1-9 | - |
| **sea_peat** | 1-7, **9, 10** | **rank 8: 24.46 km from `F4_M002.900_P0105.500`** |

A naive "ranks 1-9" walk would have produced the **wrong frame**. Frozen K=9 quantities: **36 sites
(12 + 24 new) · 144 new site-years · 50.1 GB · 1,260 inner fits · ~32.5x site-fit work · quiet-rate upper
bound 39.3%**.

**(C) NOT answered as posed — Josh asked "why wouldn't it be better to scale?"** Claude's answer: the
question is *computable*, so settling it by intuition either way is the error. Against scaling: the SE
direction is not established (Codex r3 #5 - added strata can improve precision); manual audit workload
triples **720 -> 2,160** samples at K=9; and wider SE costs power not validity, since a larger
`D-hat + 1.96*SE` makes the gate **harder** to pass, so enlarging a frozen safeguard's budget because the
gate looks hard is adjacent to threshold shopping. For scaling: 180 was frozen at 3 strata/biome, and
Josh's (A) choice makes W the headline, so W's audit precision now carries the paper.

**Resolved by a PRE-COMMITTED RULE, frozen before the number is computed:** run the §4 prospective precision
assessment at K=9 with `n_b=180` using the frozen stratified Taylor-linearised variance with FPC (a
design-stage calculation using **no test data**, so it runs inside the embargo); retain 180 if the projected
95% UCB half-width on `D-hat` is <= 0.10; otherwise scale to the smallest value meeting 0.10, capped at 540;
if even 540 fails, report the detector-audit correction **inconclusive** rather than spending more. Fixing
the threshold in advance is what distinguishes this from post-hoc tuning.

**Also swept in v6:** all K=7-dependent figures updated to the frozen K=9 (download section, compute
scaling, Goal paragraph), and the **Language rule revised** — at K=9 an explicitly probabilistic margin
claim becomes defensible, but only carrying the assumed-rate qualifier; the bare word "margin" and
"restores the gate" stay prohibited.


---

## Round 6 — Codex — VERDICT: REVISE, 12 findings (count ROSE from 3; Josh's decisions introduced new surface)

The plan is not yet sound enough to implement. Decision B and the K=9 replay check out, but decision A is not defensible as a primary inferential result, decision C is not computable as written, and the leakage firewall still omits observable channels.

1. **CRITICAL — Specification W cannot validly become the primary test analysis.** K and the frame size were chosen with a 2023 failure known; retaining that site, disclosing the deviation, and reporting the 12-site result do not remove the resulting outcome-conditioned sampling bias or restore nominal test-set inference. The 2022-validation counter-argument is correct as an independent reason to consider widening, but it cannot establish that the actual K=9 decision was unaffected by the known test outcome.  
Fix: Keep the frozen 12-site analysis primary and label W amended/exploratory, or reserve primary inferential status for a genuinely untouched future endpoint.

2. **CRITICAL — Decision C cannot be computed before the embargo lifts.** The §4 variance requires `N_bs` from 2023 positives and `D̂`, `d_i`, and `s²_e,s` from audit outcomes; §4 contains an estimation formula, not an outcome-free “prospective precision assessment.”  
Fix: Freeze an explicit planning model using only pre-2023 quantities—such as historical `N_s`, prespecified detector-rate scenarios, and a worst-case variance bound—or retain a fixed budget.

3. **MAJOR — “95% UCB half-width” is undefined and borrows the wrong 0.10 threshold.** §4 defines a one-sided UCB, not a half-width, while §10’s 0.10 is a two-sided bootstrap half-width for forecasting metrics; these are not the same precision criterion.  
Fix: Define the exact planning quantity, such as `UCB−D̂`, its assumed planning value of `D̂`, and a separately justified precision target.

4. **MAJOR — Decision C sizes the wrong audit quantity.** The stated motivation is the `1.96·SE_survey(TE_corr)` retention gate, but the rule sizes only `D̂`; excellent precision for detector share does not ensure adequate precision for `TE_corr`, whose variance also depends on detector status, target-set membership, and area weights.  
Fix: Require the selected budget to satisfy prespecified planning criteria for both `D̂` and `TE_corr`, or state that the budget addresses only the detector-share gate.

5. **MAJOR — The audit failure action does not fail closed.** “Report the detector-audit correction as inconclusive” does not explicitly say that the detector UCB and corrected-headline retention gates fail and the forecasting claim is withheld.  
Fix: State that failure to meet the precision rule by `n_b=540` makes both audit-dependent gates unevaluable and prohibits retaining the forecasting claim.

6. **CRITICAL — The firewall still has a termination/status side channel.** Metamorphic invariance covers returned files, but not child exit status, supervisor error selection, stdout/stderr byte counts, or file-set behavior; a future-dependent exception or conditional print can therefore reveal at least one test-outcome bit even when its text is sealed.  
Fix: Test invariance of the complete observable transcript—status, supervisor code, stream counts, file names and contents—and keep the sealed sink memory-only or inside the always-destroyed temporary directory.

7. **MAJOR — Isolation enforcement is tested only for the precheck.** The contract denies raw access throughout selection, tuning, calibration, and freezing, but the required integration test attacks only `precheck_evaluability.py`; another downstream executable could run outside the sandbox.  
Fix: Route every pre-lift executable through one mandatory sandbox launcher and test raw-path and network denial for every execution role.

8. **MAJOR — The embargo lift grants unnecessarily broad raw access.** The raw GFC raster also contains 2024 outcomes, so unrestricted final-evaluation access can contaminate the “genuinely untouched later endpoint” and exposes more information than 2023 evaluation requires.  
Fix: Keep evaluators raw-denied and have a post-lift privileged utility emit only frozen `eligible_2022` and `positive_2023` masks while collapsing all post-2023 values.

9. **BLOCKER — The K sweep still contains executable K=7 instructions.** Lines 298–303 still say K may be 7 or 9 and call `K=K_max=7` the adopted default, directly contradicting the frozen K=9 decision.  
Fix: Replace the entire decision block with the single binding rule `K=K_max=9`, no increment, abandonment on failure.

10. **BLOCKER — The audit section contradicts decision C.** Lines 379–388 still freeze `n_b=180` and require evaluation at both K=7 and K=9, while the new rule may select any integer budget through 540 at frozen K=9.  
Fix: Replace that subsection with the finalized K=9 budget-selection algorithm and its exact integer search, allocation, tie, and cap rules.

11. **BLOCKER — The completeness gate still specifies the K=7 archive.** Lines 456–457 require 560 TIFFs, 416 new; at K=9 the correct inventory is 720 total and 576 new, so the proposed gate would encode the wrong manifest.  
Fix: Require `4K×5×4=720` TIFFs, of which `720−144=576` are new.

12. **MAJOR — Other sweep remnants remain operationally misleading.** Line 505 still reports approximately 15× site-fit work rather than 32.5×; lines 509–511 simultaneously call leak-responsive widening and all 2023 reading out of scope; and the RNG section still calls the 12-site specification “primary,” despite W now having that label.  
Fix: Sweep these passages to 32.5×, limit the reading prohibition to the pre-lift phase, describe only further outcome-responsive changes as out of scope, and use “12-site v11” versus “Specification W” consistently.

The verified K=9 values are otherwise correct: retained ranks are 1–9 except `sea_peat` 1–7, 9, 10; one-slack joint survival is 0.960617; there are 36 sites, 24 new sites, 144 new site-years, 1,260 inner fits, approximately 32.45× site-fit work, and the zero-of-six quiet-rate upper bound is 0.393038. The storage value is 50.0625 GiB, or 51.264 decimal GB—not 50.1 GB.

VERDICT: REVISE
### Claude's response — round 6

**11 of 12 accepted and applied. #1 is not Claude's to accept or reject — it is a direct challenge to
Josh's decision (A) and is escalated to him unresolved.**

**#1 — CODEX REJECTS JOSH'S (A) DECISION AS INVALID.** Not "less conservative" — invalid: "Specification W
cannot validly become the primary test analysis... retaining that site, disclosing the deviation, and
reporting the 12-site result do not remove the resulting outcome-conditioned sampling bias or restore
nominal test-set inference." **Claude's independent assessment agrees with Codex.** Disclosure makes a bias
visible; it does not remove it. K=9 was chosen with a 2023 failure known, so W's frame size is
outcome-conditioned and W cannot carry nominal test-set inference. **NOT applied. Josh decides.**

**Three findings are Claude's own errors, all in the (C) rule written this session:**
- **#2 CRITICAL — the (C) rule is NOT COMPUTABLE.** Claude asserted the prospective precision assessment
  "uses no test data and runs inside the embargo". False. §4's variance needs `N_bs` from **2023 positives**
  and `D̂`, `d_i`, `s²_{e,s}` from **audit outcomes**. It is an estimation formula, not a planning one.
- **#3 MAJOR — wrong precision quantity.** Claude borrowed §10's **two-sided bootstrap half-width (0.10)**
  for forecasting metrics and applied it to §4's **one-sided UCB** for the detector share. Different
  quantity, different estimand, different threshold.
- **#4 MAJOR — sized the wrong thing.** The stated motivation is the `1.96·SE_survey(TE_corr)` retention
  gate, but the rule sized only `D̂`.
Rewritten: an explicit planning model over pre-2023 quantities only (historical `N_s`, prespecified
detector-rate scenarios {0.05,0.10,0.20,0.35}, worst-case variance bound), planning quantity defined
explicitly as `UCB(D̂) − D̂_plan`, sized against **both** `D̂` and `TE_corr`, smallest integer `n_b ∈ [180,540]`.

**#5 — now FAILS CLOSED.** If no `n_b ≤ 540` meets the criteria, both audit-dependent gates are declared
**UNEVALUABLE and the forecasting claim is WITHHELD** — not "inconclusive but reported anyway".

**#6 — THE FIFTH FIREWALL VECTOR, exactly as the plan predicted.** v5 tested invariance of *returned
files*; that is not the observable surface. **Exit status, supervisor error-code choice, stream byte counts,
and the file set** are all observable, and a future-dependent exception leaks **one bit** even with text
perfectly sealed. One bit is a leak. Now requires invariance of the **complete observable transcript**.
Sealed sink is memory-only or inside the always-destroyed temp dir. The plan now says: assume a sixth.

**#7** — isolation was tested only against `precheck_evaluability.py` while the contract binds all pre-lift
work. All pre-lift roles now route through **one mandatory sandbox launcher**, with denial tested per role.

**#8** — the embargo lift was too broad: the raw raster also carries **2024**, so unrestricted post-lift
access contaminates the very "untouched later endpoint" a future confirmatory analysis needs. Evaluators
stay raw-denied; a post-lift privileged utility emits only `eligible_2022` and `positive_2023`.

**#9, #10, #11 — three BLOCKERS from an incomplete K sweep, all Claude's.** The K-freeze block still read
`K = K_max = 7`; the audit section still froze `n_b=180` and required evaluation at both K=7 and K=9; and
the completeness gate still encoded the K=7 archive (560/416) instead of **720 total / 576 new**. A
half-finished sweep is worse than none, because it leaves executable instructions contradicting the freeze.

**#12 + unit error** — compute figure corrected ~15× → **32.5×**; the scope section contradicted itself by
declaring all 2023 reading out of scope in a study whose point is to read 2023, now limited to **pre-lift**;
"primary" no longer used as a synonym for the 12-site design (now "12-site v11" vs "Specification W"); and
**storage restated as 51.3 GB decimal / 50.06 GiB** — Claude had computed GiB and labelled it GB.

**Verified by Codex and confirmed correct:** retained ranks 1–9 except `sea_peat` 1–7, 9, 10; one-slack
joint survival 0.960617; 36 sites; 24 new; 144 new site-years; 1,260 inner fits; ~32.45× site-fit work;
zero-of-six quiet-rate upper bound 0.393038.


### Josh's revised decision (A) — 2026-07-20, after round 6

**REVERTED. `FORECAST-PLAN.md` v11 (12-site) is the PRIMARY inferential analysis; Specification W is
AMENDED / EXPLORATORY.** Josh had chosen widened-primary; shown Codex r6 #1 ("cannot validly become the
primary test analysis") and Claude's concurrence, he reverted on the argument. K=9 is unchanged — all 144
site-years are still downloaded; only the inferential label moved.

**Consequence: the (C) problem largely dissolves.** With 12-site v11 primary and preserved verbatim, its
audit is untouched at `180/3 = 60` per site, exactly the allocation the budget was frozen for. The
`180/9 = 20` degradation now applies **only to Specification W**, which is exploratory and can carry wider
intervals without threatening the inferential claim. The budget-selection rule and its fail-closed action
were narrowed to bind **W only**; the primary is unaffected in every branch.


---

## Round 7 (FINAL under extended MAX_ROUNDS=7) — Codex — VERDICT: REVISE, 4 findings

**No new firewall vector — the first round since round 1 without one.** Codex: "The strengthened
pre-lift isolation provisions also address the round-6 firewall findings." It also re-verified K=9,
the inhibited draw, 144 site-years, 720/576 TIFFs, 1,260 fits, 32.5x workload and storage as correct,
and confirmed the (A) revert and the W-only narrowing are scientifically correct.

The A reversal and W-only budget narrowing are scientifically correct, but v7 still has two implementation blockers.

1. **CRITICAL — The obsolete v6 decision-C rule remains live at lines 127–166.** It still calls W primary, invokes the impossible pre-test §4 variance, borrows §10’s 0.10 threshold, lacks fail-closed behavior, and says either K may be chosen; this directly contradicts the replacement at lines 407–439 and could alter the primary audit.  
Fix: Delete the old rule and replace it with a short W-only pointer to the single binding rule in §6, explicitly stating that 12-site v11 retains `n_b=180` unchanged.

2. **BLOCKER — The replacement planning rule is not computationally specified.** It does not define how 2021/2022 `N_s` are combined, the worst-case variance formulas, the planning construction for `TE_corr` and its denominator, either numerical precision threshold, or whether every biome/year must pass; consequently “meeting both planning criteria” cannot be evaluated.  
Fix: Freeze the exact input transformation, formulas, boundary handling, thresholds, and worst-case aggregation across years, biomes, and detector-rate scenarios—or simply retain `n_b=180` for exploratory W and accept its resulting precision.

3. **MAJOR — The post-lift label handoff lacks a frozen schema.** The pre-lift table says there is deliberately no `positive_2023`, while the post-lift phase permits it without freezing its pixel formula or requiring transcript invariance to changes in post-2023 values; this ambiguity affects the primary test population.  
Fix: Add a separate post-lift schema defining `positive_2023 = eligible_2022 ∧ lossyear == 23`, retaining the existing `eligible_2022` formula, and require complete-transcript invariance under every change to loss years after 2023.

4. **MODERATE — `180/3=60 per site` is only a nominal mean.** The preserved v11 allocator uses censuses, floors, caps, and proportional largest-remainder allocation, so individual sites need not receive 60 and the total can be below 180 when populations are exhausted.  
Fix: Call 60 the nominal mean when the full budget is used and explicitly require the complete v11 allocator—not equal allocation—to remain unchanged.

The narrowing itself is otherwise correct: Specification W’s audit budget has no reason to modify the primary’s frozen `n_b=180`, provided the specifications retain separate manifests, RNG streams, audit draws, and results. K=9, the inhibited draw, 144 site-years, 720/576 TIFF inventory, 1,260 fits, 32.5× workload, and storage figures remain correct. The strengthened pre-lift isolation provisions also address the round-6 firewall findings.

VERDICT: REVISE
### Claude's response — round 7

**All 4 accepted and applied. FINAL TOTAL: 58 findings over 7 rounds — 57 accepted, 1 escalated to Josh
(r6 #1), which he resolved by reverting (A). Zero rejected.**

**#1 CRITICAL — Claude left a contradictory duplicate live.** The round-6 rewrite replaced the §6 audit
subsection but left the ORIGINAL (C) decision block at lines 127-166 untouched. That obsolete block still
called W primary, still invoked the impossible pre-test §4 variance, still borrowed §10's 0.10, still
lacked fail-closed, and still said either K could be chosen — a live rule contradicting its own
replacement, and one that "could alter the primary audit". Deleted and replaced with a short pointer.
**This is a half-finished-sweep failure, the same class as r6 #9-#11.** Twice in two rounds.

**#2 BLOCKER — and the fix is a deletion, not an addition.** The round-6 replacement planning rule was
*also* unevaluable: it never defined how 2021/2022 `N_s` combine, the worst-case variance formulas, the
`TE_corr` planning construction and denominator, either numerical threshold, or whether every biome and
year must pass. Codex offered the alternative Claude should have taken first: **just retain `n_b = 180`
for exploratory W and accept its precision.** Adopted. Both unevaluable apparatuses are withdrawn; the
audit rule is now one sentence. **Specification W is EXPLORATORY — building a second unevaluable planning
machine to size its audit budget was complexity for nothing.**

**#3 MAJOR — post-lift schema frozen.** Pre-lift deliberately has no `positive_2023`; post-lift permits it
but its formula was never frozen, leaving the *primary test population* ambiguous. Now frozen as
`positive_2023 = eligible_2022 AND lossyear == 23`, with complete-transcript invariance still required
under changes to loss years after 2023 — so opening 2023 never also opens 2024.

**#4 MODERATE — "180/3 = 60 per site" is a NOMINAL mean, not an allocation.** v11's allocator uses
censuses, floors of 2, caps, and iterative largest-remainder redistribution on remaining capacity, so
individual sites need not receive 60 and the realised total can fall below 180 where populations are
exhausted. Corrected, with an explicit requirement that the **complete v11 allocator** — not equal
allocation — remain unchanged.

**Claude's own post-edit sweep** then found 3 stale references left by the large deletions (a
"pre-committed computational rule" pointer in the decisions header, and two section headings still
describing the withdrawn design). Fixed. Noted because it is evidence for the risk in the Resolution below.

## FINAL RESOLUTION — MAX_ROUNDS=7 exhausted, verdict REVISE. NOT converged.

Reported as-is. The chain never reached APPROVED.

**It is not a deadlock.** 58 findings, 57 accepted by Claude, 1 escalated to and resolved by Josh, **0
rejected**. Claude holds no counter-positions. Findings by round: **19 -> 10 -> 6 -> 4 -> 3 -> 12 -> 4**.
The rise at round 6 is explained: Josh's two decisions opened new surface, and 5 of those 12 were Claude's
own errors introduced that same round.

**What is converged:** the scientific and statistical design. From round 3 onward Codex repeatedly recorded
no remaining defect in K selection, the sequential-inhibition replay, the probability calculations, audit
allocation, the RNG namespace, manifest and download accounting, or the primary-versus-secondary treatment,
and round 7 re-verified every K=9 figure. The leakage firewall — five distinct vectors across five rounds —
drew **no new finding at round 7**.

**What is not:** v8's edits are UNREVIEWED, and they were large (a 39-line deletion plus withdrawal of the
planning apparatus). **Claude has now twice left contradictory remnants after exactly this kind of edit**
(r6 #9-#11, r7 #1). That specific risk is demonstrated, not hypothetical.

**Claude's recommendation: ONE more round.** Not because the design is in doubt, but because the failure
mode most likely to be present in v8 is the one Claude has already committed twice.

---

## Round 8 — Codex — VERDICT: REVISE, 7 findings (consistency sweep, as requested)

**The requested sweep confirmed the predicted failure mode: 7 contradictory remnants from the v6-v8
deletions, no new design defects.** Codex confirmed no live 'W primary' statement, no surviving
D_plan / detector-scenario / 540-cap / prospective-planning / unresolved-C rule, and that remaining
K=7 mentions are historical or explicitly illustrative. The one substantive item (#4) is an audit-logic
error, not a remnant.

The primary label, K=9 constants, and fixed `n_b=180` are mostly consistent, but the requested sweep found several surviving contradictions, including one material audit-rule defect.

1. **Line 140 still treats K as a live choice.** “Either choice drops in” contradicts lines 105 and 314–315, which freeze `K=K_max=9` with no alternative.  
Fix: State that formulas remain parameterized in K but are instantiated only at frozen K=9.

2. **Lines 399–400 reference a nonexistent W-only “budget-selection rule.”** The only rule below is the fixed `n_b=180` rule binding both specifications at line 417.  
Fix: Say that only the consequences of reduced nominal allocation apply to W; the same fixed budget rule applies to both specifications.

3. **Lines 134–135, 398, and 423–424 assert that W receives wider intervals, while lines 401–402 correctly say the direction is not guaranteed.** Added strata can improve or reduce precision depending on population sizes and within-stratum variance.  
Fix: Replace “wider intervals” with “whatever intervals result, potentially wider or narrower.”

4. **Lines 424–426 create an undefined “insufficient precision ⇒ unevaluable” branch.** Under frozen v11, audit imprecision makes the UCB and retention gates harder to pass; it does not make them unevaluable. No separate insufficiency threshold is defined, so this branch permits discretionary relabelling of a failed gate.  
Fix: Apply the unchanged numeric gates at `n_b=180`; wide uncertainty causes failure and claim withholding, while “unevaluable” is reserved for prespecified mathematical undefinedness such as a zero denominator.

5. **Lines 210–228 permit the post-lift `positive_2023` mask, but lines 269–283 again state absolutely that the utility emits no `positive_2023` and returns only loss-through-2022 masks.** Line 212 implies the latter is pre-lift, but the later absolute wording remains operationally contradictory.  
Fix: Label lines 254–288 explicitly as the pre-lift schema and state that the separately defined post-lift schema supersedes only its `positive_2023` prohibition.

6. **Line 352 says faulty mosaicking can “choose K,” contradicting the non-binding precheck and frozen-K rule at lines 314–319.**  
Fix: Say faulty mosaicking can corrupt the diagnostic scores, never choose or change K.

7. **Lines 242–252 call the transcript channel the fifth vector and instruct assuming a sixth, while lines 274–275 revert to calling the boundary history three vectors and assuming a fourth.**  
Fix: Update the latter passage to the current fifth-vector/sixth-assumed accounting or remove the duplicate history.

The sweep found no live statement calling W primary; those occurrences are clearly historical. There is no surviving live `D_plan`, detector-scenario, 540-cap, prospective-planning, or unresolved-C rule. Other K=7 occurrences are historical comparisons or explicitly illustrative table columns.

The substantive narrowing is correct: 12-site v11 retains its complete `n_b=180` allocator unchanged, while W also uses 180 and cannot affect the primary’s allocation, RNG, fitted state, or results. Once finding 4 is corrected, W can simply apply the frozen gates and accept the resulting pass/fail outcome.

VERDICT: REVISE
### Claude's response — round 8

**All 7 accepted and applied. RUNNING TOTAL: 65 findings over 8 rounds, 64 accepted, 1 escalated to Josh
(resolved), 0 rejected.**

Running round 8 was the right call: it existed only to catch the failure mode Claude had committed twice
(r6 #9-#11, r7 #1), and it caught seven more instances of exactly that. Six are pure remnants; #4 is
substantive.

- **#1** — "either choice drops in without a rewrite" survived from the pre-decision K-sweep, contradicting
  the frozen `K = K_max = 9`. Now: formulas stay parameterized in K for provenance, instantiated only at 9.
- **#2** — a dangling reference to a "budget-selection rule below" that was deleted with the planning
  apparatus. Now states the single fixed `n_b = 180` rule binds both; only the *consequence* reaches W.
- **#3 (substantive-adjacent)** — three passages asserted W gets "wider intervals", contradicting the
  correct statement two lines away that the direction is not guaranteed. This is the SAME overreach Codex
  corrected at r3 #5 and r6, resurfaced by Claude in the narrowing prose. All replaced with "potentially
  wider or narrower; the frozen variance calculation decides".
- **#4 SUBSTANTIVE — a discretionary-relabelling hole.** Claude wrote that if W's audit precision is
  "insufficient", W's gates are "unevaluable". Wrong: under frozen v11, imprecision makes the UCB and
  retention gates HARDER TO PASS — it does not make them unevaluable, and no insufficiency threshold was
  defined, so the branch permitted relabelling a failed gate as unevaluable at discretion. Fixed: W applies
  the unchanged numeric gates at 180; wide uncertainty causes FAILURE and claim withholding; "unevaluable"
  is reserved for prespecified mathematical undefinedness (e.g. zero denominator).
- **#5** — the pre-lift schema's absolute "no positive_2023" contradicted the new post-lift schema. Now
  labelled the pre-lift schema explicitly, with the post-lift schema superseding only its positive_2023
  prohibition.
- **#6** — "faulty mosaicking can choose K" contradicted the frozen K and the non-binding precheck. Now:
  it can corrupt the diagnostic scores, never choose or change K.
- **#7** — a duplicate, stale "third vector / assume a fourth" history sat below the current "fifth vector /
  assume a sixth" accounting. Duplicate removed; a single consistent accounting remains.

Claude's own post-edit re-sweep (grep for each fixed token + structural checks: single "Correct boundary:",
single vector accounting, no bare "wider intervals", line count) found no further remnant. That re-sweep is
now part of the procedure specifically because the remnant failure has recurred.


---

## Round 9 — Codex — VERDICT: APPROVED ✅

All seven round-8 findings are resolved. The fresh sweep found no live W-primary designation, alternative K, withdrawn planning rule, 540 cap, conflicting audit budget, or discretionary precision branch.

The primary remains isolated with its original allocator and RNG streams; W uses fixed `n_b=180`, applies the unchanged numeric gates, and remains exploratory. The pre/post-lift schemas and complete-transcript invariance requirements are coherent.

Two non-blocking wording issues remain:

- Line 272 cites the “§4 phase table,” but the phase table is in §1 at lines 208–220.
- Line 426’s “imprecise audit fails” is shorthand; the controlling rule at line 425 correctly makes failure depend on the unchanged numeric inequalities.

Neither creates an alternative implementation path or compromises the scientific protocol. The plan is sound enough to implement.

VERDICT: APPROVED
### Claude's response — round 9 (final)

**APPROVED.** All 7 round-8 remnants confirmed resolved; the fresh sweep found no live W-primary
designation, alternative K, withdrawn planning rule, 540 cap, conflicting audit budget, or discretionary
precision branch. Two non-blocking wording nits (a §4→§1 cross-reference and one shorthand phrase) were
fixed for cleanliness though Codex judged neither blocking.

## CONVERGED — final resolution

**Codex APPROVED at round 9.** Chain ran 9 rounds (5 planned + 4 extended, all extensions authorised by
Josh). Findings by round: **19 → 10 → 6 → 4 → 3 → 12 → 4 → 7 → APPROVED**. Total **67 findings; 66 accepted
by Claude, 1 escalated to Josh (r6 #1, resolved by reverting (A)), 0 rejected.**

The round-6 spike was Josh's two decisions opening new design surface (5 of those 12 were Claude's own
errors introduced that round). The round-8 spike was the consistency sweep catching remnants from the large
v6-v8 deletions — the failure mode Claude committed at r6 #9-#11 and r7 #1. Both spikes were resolved and
re-verified.

**Locked decisions (all Josh's):** (A) 12-site v11 is the PRIMARY inferential analysis, Specification W is
amended/exploratory; (B) K = K_max = 9, frozen; (C) n_b = 180 retained for both specifications.

**Frozen quantities:** 36 sites (12 existing + 24 new, ranks 1-9 per stratum except sea_peat 1-7,9,10),
144 new site-years, 51.3 GB decimal, 1,260 inner contagion fits (~32.5x site-fit work), quiet-rate upper
bound 39.3%.

**No code written, nothing downloaded, FORECAST-PLAN.md v11 untouched.** Awaiting Josh's sign-off before
any implementation.
