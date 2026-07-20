# Plan: Widen the site frame from 12 to 4K sites to increase site-count resilience in the regional gate
_v9 (APPROVED) — Locked via grill (Claude + Josh, 2026-07-20), revised against Codex rounds 1 (19 findings), 2 (10),
3 (6), 4 (4), 5 (3), 6 (12), 7 (4) and 8 (7). 64 of 65 findings accepted; r6 #1 escalated to Josh, who reverted (A).
**CODEX APPROVED at round 9 (2026-07-20). 67 findings over 9 rounds; 66 accepted, 1 escalated to Josh, 0 rejected.**
**Decisions (A), (B), (C) RESOLVED BY JOSH 2026-07-20; MAX_ROUNDS extended 5 -> 7 at his direction.**
**(A) 12-site v11 PRIMARY, Spec W exploratory (reverted r6) · (B) K = K_max = 9 · (C) retain n_b = 180.**_
_Defines **Specification W**, an **AMENDED / EXPLORATORY** 36-site design. `FORECAST-PLAN.md` (v11,
Codex-APPROVED at round 9) is preserved **verbatim** and remains the **PRIMARY** inferential analysis._

> **Language rule (Codex r2 #3), UPDATED for K=9.** At K=7 the honest claim was "increased site-count
> resilience", because one-slack survival was only 74.6%. **At K=9 one-slack survival is 96.1%, so an
> explicitly probabilistic margin claim IS now defensible** — but only when stated as: *"under an assumed
> 0.25 IID single-year quiet rate, ≥1 site of slack in every stratum with probability 0.961."* The bare
> word "margin", the phrase "restores the gate", and any claim not carrying the assumed-rate qualifier
> remain prohibited in this plan and the paper. **0.25 is an assumption, never an estimate from these
> data.**

> **Reviewers: the plan under amendment is `FORECAST-PLAN.md`, NOT `PLAN.md`.** `PLAN.md` in this
> worktree is the *retired* risk-forecasting study, merged in for its code and kept only as a record.
> The live log is `FORECAST-REVIEW-LOG.md`; this amendment's log is `FRAME-WIDENING-REVIEW-LOG.md`.

## THREE DECISIONS — ALL RESOLVED BY JOSH, 2026-07-20

_Josh **overrode Claude's recommended default on both (A) and (B)**, and asked for reasoning rather than a
choice on (C), which the (A) revert then largely dissolved. Recorded below as his decisions._

**(A) Widening acts on leaked test knowledge, and the plan can no longer deny it (Codex r1 #2).**
v1 claimed a pure superset "does not act on the leak". That claim is **withdrawn as false**. Even with the
tainted site retained, changing frame size after learning its 2023 failure changes training data,
normalization constants, the global top-5% target set, bootstrap composition, and every reported estimate.

Claude's partial counter, logged: the *trigger* to widen was the **2022 validation** failure
(`amazon_moist` 2/3), which is permitted information under §F, and that failure alone justifies widening
independently of the leak. But this does not rescue v1's claim, because the leaked fact was in the room
when K was chosen and cannot be unlearned.

**DECIDED BY JOSH — and REVISED BY HIM at round 6 after both reviewers dissented. FINAL:**
**`FORECAST-PLAN.md` v11 (12-site) is the PRIMARY inferential analysis. Specification W is AMENDED /
EXPLORATORY.**

Josh initially chose widened-primary, overriding Claude's recommendation. **Codex r6 #1 rejected that as
invalid** — not merely less conservative: *"Specification W cannot validly become the primary test
analysis... retaining that site, disclosing the deviation, and reporting the 12-site result do not remove
the resulting outcome-conditioned sampling bias or restore nominal test-set inference."* **Claude
independently concurred.** Shown both dissents, Josh reverted. The history is kept here deliberately: the
decision was made, challenged by two independent reviewers, and changed on the argument.

**Why disclosure was not enough.** K=9 was selected while a 2023 outcome was known, so W's frame size is
**outcome-conditioned**. Disclosure makes that visible; it does not remove it, and nominal test-set
inference does not survive it. Requirements that follow:

- **12-site v11 carries the inferential claim.** Its frame was fixed before any 2023 outcome was known.
- **Specification W is reported as amended/exploratory**, never as confirmatory, with the deviation
  disclosed **prominently in main text**: what was read (`F1_P000.180_M0063.250`, 4 mapped loss components
  in 2023, below the ≥5 floor), when, how, and that the frame was **extended rather than edited**.
- **Both results are reported**, so a reader can see whether conclusions depend on the widening.
- No confirmatory language attaches to either. Confirmation requires a genuinely untouched later endpoint.
- **All 144 site-years are still downloaded** — K=9 is unchanged. Only the inferential label moved.

Codex separately confirmed Claude's counter-argument is **not wrong**: the permitted 2022 validation failure
is independently sufficient reason to *consider* widening. It remains a counterfactual mitigation only, so
the deviation classification stands regardless.

**Both specifications must stay SEPARABLE, whichever is primary (Codex r2 #2).** An earlier draft declared
the 12-site analysis primary while §6 simultaneously rewrote its sample-size constants and renumbered its
frozen RNG folds, which would have destroyed it. That hazard is unchanged by the relabelling: the 12-site
result is still computed and reported, so it must still be preserved intact. Binding requirement:

- **`FORECAST-PLAN.md` v11 ("the 12-site v11 specification"), its fold map, and its RNG streams are
  preserved VERBATIM.** Nothing in §6 edits them. This is now doubly load-bearing: v11 is the **primary**
  inferential analysis, so any edit to its constants or fold numbering would corrupt the paper's main
  result. Throughout, the two designs are named **"12-site v11" (primary)** and **"Specification W"
  (exploratory)**.
- The widened design is a **separately named specification** — **Specification W** — with its **own**
  manifest, seed map, fold table, and result namespace.
- **Specification W needs a distinct RNG namespace, not merely a distinct fold table (Codex r3 #2).** W
  still inherits `SEED = 42` and the same `(analysis_code, unit_index, replicate)` key structure, so
  primary fold 0 and W fold 0 would instantiate **identical streams** despite separate fold tables.
  **FROZEN NOW (Codex r4 #3), one scheme chosen, no alternatives left open:** Specification W's key is
  **`(specification_code = 1, analysis_code, unit_index, replicate)`**. **12-site v11** keeps its original
  three-coordinate key `(analysis_code, unit_index, replicate)` **verbatim and untouched**, so its frozen
  draws do not move. **Cross-specification collision tests are required**, asserting that no W stream
  coincides with any 12-site v11 stream.
- **Shared raw inputs are permitted; shared derived state is not (Codex r3 #3).** Literal "no artifact
  shared" was wrong: both specifications need the *same* incumbent composites — including the 24 missing
  2021/2022 site-years — and the 20K−36 accounting assumes each is downloaded **once**. Enforcing literal
  isolation would mean duplicate downloads and duplicate storage for no scientific gain. Correct rule:
  both specifications may reference the **same checksum-pinned, read-only raw composites**, while
  **manifests, fitted state, normalization constants, RNG artifacts, predictions, and result paths are
  never shared.**

**(B) K=7 does not deliver the margin it was chosen for (Codex r1 #6, verified exactly).**
Josh chose K=7 believing it gave "95% joint survival at a 25% quiet rate" **with one site of slack**. That
was wrong. Independently recomputed:

| | per stratum | all four strata |
|---|---|---|
| P(≥3 evaluable) — **zero slack, exactly at the floor** | 0.98712 | **0.94947** |
| P(≥4 evaluable) — **one site of slack** | 0.92944 | **0.74626** |

So the 95% figure is **zero-slack gate survival**, not the one-slack margin the choice was premised on.
One-slack survival by K: **K=7 → 74.6%, K=8 → 89.5%, K=9 → 96.1%**. K=9 is what crosses 95% with real
slack, at 36 sites / 144 new site-years / **~51 GB**.

**DECIDED BY JOSH, 2026-07-20 — Claude's default (hold at K=7) was OVERRIDDEN. `K = K_max = 9`, FROZEN.**
Josh originally chose K=7 on the mistaken understanding that it purchased one-slack margin; shown the
corrected figures he moved to K=9, which is the smallest K delivering **≥1-slack survival above 95%
(96.1%)** under the assumed 0.25 IID quiet rate.

**The K=9 frame is NOT "ranks 1–9" — the inhibition binds, and this is where Codex r1 #4 stops being
academic.** Replaying `select_round_robin` at K=9 (verified 2026-07-20):

| Stratum | Retained ranks | Skipped |
|---|---|---|
| amazon_moist | 1–9 | — |
| congo_moist | 1–9 | — |
| dry_forest | 1–9 | — |
| **sea_peat** | 1–7, **9, 10** | **rank 8 rejected: 24.46 km from `F4_M002.900_P0105.500`** |

A naive rank walk would have produced the **wrong frame**. Deepest rank reached: **10**.

**Frozen K=9 quantities:** 36 sites (12 existing + **24 new**) · **144 new site-years** · **51.3 GB**
(decimal; 50.06 GiB) optical · **1,260** inner contagion fits · stratum-specific one-sided 95% upper bound on the quiet rate with
zero observed = **39.3%** (`1 − 0.05^(1/6)`).

The 96.1% remains an **IID scenario under an assumed 0.25 quiet rate**, not an estimate from data.

**(C) Audit budget — RESOLVED. `n_b = 180` retained for both; only Specification W's precision changes.**

Josh asked why scaling the budget would not simply be better. The (A) revert answered it: with **12-site
v11 as the primary**, preserved verbatim, **its audit is untouched — `n_b = 180`, 3 strata per biome,
unchanged allocator.** The `180/9` degradation reaches only **Specification W**, which is exploratory.

**FINAL RULE: `n_b = 180` is retained for BOTH specifications.** W simply accepts whatever intervals
result — potentially wider or narrower, the frozen variance calculation decides — which is appropriate for
an exploratory result. The elaborate pre-committed planning apparatus
drafted at round 6 is **withdrawn in full** — see §6 for the single binding statement and why the earlier
version was not computable. Nothing about the primary's audit changes in any branch.


**Formulas below stay parameterized in K for provenance, but are instantiated only at the frozen `K = 9`.**

## Goal

`FORECAST-PLAN.md` §10 grants a region a per-region generalization estimate only if it has **≥3 evaluable
sites AND ≥30 mapped loss components AND bootstrap half-width ≤0.10**, where an evaluable site has ≥5
mapped loss components in the test origin. The frame carries exactly **3 sites per stratum against a floor
of 3**, so a single quiet site takes a region dark. `forecast/precheck_evaluability.py` measured **zero
margin in all four strata, with `amazon_moist` already failing on the 2022 validation origin (2/3)**.

Increase **site-count resilience** by widening from 3 to **K sites per stratum** (12 → 4K sites), replaying
the frame's own registered selection algorithm. Gate thresholds are unchanged. **At the frozen K=9** this
gives ≥1-slack survival of **96.1%** under an *assumed* 0.25 IID single-year quiet rate. That assumed rate
is not estimated from these data, and the claim must always carry the qualifier (see Language rule).

**Scope honesty (Codex r1 #8, r3 #4):** this amendment **targets the ≥3-evaluable-sites condition only, and
increases its resilience rather than restoring it.** A
GFC-only precheck cannot establish the **≥30 components** condition at the test origin, and cannot
establish the **half-width ≤0.10** condition at all. The plan must not claim to have restored "the
regional gate" — only its site-count arm.

## Approach

### 1. Build a technical censoring boundary for GFC access (Codex r1 #1 — CRITICAL)

v1 treated `PERMITTED_ORIGINS = (2020, 2021)` as the firewall. **It is not a firewall.**
`precheck_evaluability.py:142` reads the full `lossyear` raster — 2023 and 2024 values included — into an
ordinary array, and `PERMITTED_ORIGINS` constrains only what is later computed from it. **That is exactly
how the prior breach happened:** the values were sitting in memory, one `print` away.

**v2's fix was itself still a leak (Codex r2 #1 — CRITICAL).** v2 proposed censoring `lossyear > 22` to
"a sentinel". A *distinct* sentinel value reveals **exactly which pixels suffered post-2022 loss** — and
`positive = lossyear == 23` **is** the test label. Worse, the metamorphic test v2 specified (perturb 23→24)
would pass unchanged while the leak sat there untouched. Withdrawn.

**And v3's boundary was still only a convention (Codex r3 #1 — CRITICAL).** Collapsing post-2022 into a
single state makes the *transformation* mathematically non-leaking, but the raw `lossyear` array still
exists **inside the same Python process**. A debugger, an ad-hoc `print`, an exception-local dump, a
monkeypatch, or simply another `rasterio.open` elsewhere in the process reaches it exactly as before —
which is precisely how the original breach occurred. "Only this module may open GFC rasters" is a naming
convention, not a technical boundary.

**Capability isolation is therefore mandatory** — and must be **enforceable and testable**, not merely
declared (Codex r4 #1). "Only persistent output" does not cover transient channels: a privileged child can
still leak raw labels through **stdout/stderr, exception tracebacks, crash dumps, temporary files, or
stray files in its output directory**.

Binding isolation contract:
- The reviewed raw-access/censoring utility runs as a **separate, non-interactive process under an
  OS-enforced sandbox**.
- **Sealed stdout–stderr sink, validated but never rendered (Codex r5 #1).** A post-run "streams were
  empty" check is **too late** — an accidental raw-array `print` has already reached the console by the
  time it runs. Instead a **trusted supervisor redirects the child's stdout/stderr into a sealed sink that
  is never displayed, logged, or echoed**, and validates **byte counts only**. The supervisor emits its own
  fixed, non-data-bearing error codes; the child's text never surfaces under any outcome.
- **Core dumps disabled.** An **exclusive temporary directory destroyed after EVERY termination path** —
  success, failure, crash, timeout, and forced kill (Codex r5 #1). v4 destroyed it only on success, so any
  abnormal exit left raw-derived files on disk.
- **Exact output-file allow-list.** Any file produced outside it is a hard failure, not a warning.
- The precheck and every downstream consumer run **without network or filesystem access to the raw GFC
  rasters at all**. They physically cannot read what they must not see.

**Isolation has a defined LIFETIME, not an infinite one (Codex r5 #2).** v4 said raw-GFC denial binds
"every downstream consumer", full stop — but both specifications must *eventually* read the 2023 outcome to
produce any result at all. As written the plan made final evaluation impossible, which in practice means
someone relaxes the sandbox informally at the worst possible moment. Explicit phase boundary:

| Phase | Raw GFC access |
|---|---|
| **Frame selection, precheck, tuning, calibration, all freezing** | **DENIED.** Sandbox binding, no exceptions. |
| **Final evaluation** | **Evaluators remain raw-denied.** A post-lift *privileged utility* emits only frozen `eligible_2022` and `positive_2023` masks, collapsing all post-2023 values, via a separately logged one-time transition |

**Frozen POST-LIFT schema (Codex r7 #3).** The pre-lift table deliberately has no `positive_2023`; the
post-lift phase permits exactly one addition, and its pixel formula is frozen here so the primary test
population is never ambiguous:

| Post-lift output | Frozen pixel formula |
|---|---|
| `eligible_2022` | unchanged from the pre-lift definition |
| `positive_2023` | `eligible_2022 ∧ lossyear == 23` |

**Complete-transcript invariance is still required post-lift** — under every change to loss years **after
2023** — so opening 2023 never also opens 2024.

**The lift does NOT grant raw access to evaluators (Codex r6 #8).** The raw GFC raster also carries **2024**
outcomes; unrestricted post-lift access would contaminate precisely the "genuinely untouched later endpoint"
that any future confirmatory analysis depends on, and exposes strictly more than 2023 evaluation requires.
Post-lift, the same sandboxed pattern applies with a widened but still-bounded allow-list:
`eligible_2022` and `positive_2023` only, **every post-2023 value collapsed**.

The embargo lift may occur **only after both specifications and every frozen artifact are sealed** —
manifests, fold tables, RNG maps, K, hyperparameters, calibrators, and the audit design. The transition is
recorded as its own logged event with a timestamp and the sealed-artifact hashes it was conditioned on.
- **The sealed sink is memory-only, or lives inside the always-destroyed temp directory.** It is never a
  durable artifact.
- **MANDATORY SANDBOX LAUNCHER for every pre-lift executable (Codex r6 #7).** Denial binds all of frame
  selection, precheck, tuning, calibration and freezing, so testing only `precheck_evaluability.py` leaves
  every other downstream executable free to run unsandboxed. **All pre-lift roles route through one
  launcher**, and raw-path and network denial is tested **for every execution role**, not just the precheck.
- **Integration tests that deliberately attempt raw-path and network access from EVERY pre-lift role and
  REQUIRE failure.** An isolation claim with no test that tries to break it is not evidence of isolation.

**THE FIFTH VECTOR: the observable transcript itself (Codex r6 #6 — CRITICAL).** v5 tested invariance of
*returned files*. That is not the full observable surface. **Child exit status, the supervisor's choice of
error code, stdout/stderr byte counts, and the set of files produced** are all observable, and a
future-dependent exception or a conditional print leaks **at least one bit** of test outcome even when its
text is perfectly sealed. One bit is enough to be a leak.

**Required:** metamorphic invariance of the **COMPLETE observable transcript** — exit status, supervisor
error code, stream byte counts, file names, and file contents — under moving, adding, and removing
future-loss pixels. If perturbing future loss changes *anything* an outside observer can see, including how
the run failed, the boundary is not closed. This is the fifth vector found in this one script; assume a
sixth.

**Frozen handoff schema (Codex r4 #2).** Without an exact allow-list, an implementer who finds the masks
insufficient will simply reopen `treecover2000`, `datamask`, or `lossyear` to fill the gap — reintroducing
the vector. The utility emits exactly these aligned boolean masks plus safe georeferencing (CRS, transform,
shape), and nothing else:

**Names alone are not a specification (Codex r5 #3)** — "outcomes at the permitted origins" could be
implemented as raw `lossyear == 21/22`, which would count losses **outside the frozen forest population**
and silently change component totals. The pixel formulas are therefore frozen explicitly, matching
`FORECAST-PLAN.md` §4:

| Output | Frozen pixel formula |
|---|---|
| `eligible_T` for T ∈ {2020, 2021, 2022} | `datamask == 1 ∧ treecover2000 ≥ 30 ∧ (lossyear == 0 ∨ lossyear > T−2000)` |
| `positive_T+1` for T ∈ {2020, 2021} | `eligible_T ∧ lossyear == (T+1)−2000` |

Every emitted mask carries the formula it was produced by. **This is the PRE-LIFT schema:** there is
deliberately **no `positive_2023`** and no value-bearing array of any kind. The separately defined post-lift
schema (§1 phase-boundary table) supersedes **only** this `positive_2023` prohibition, and nothing else.
**Raw-tile checksum verification, coverage assertions, and transform-aware mosaicking (§5) all move INSIDE
the privileged utility** — the unprivileged precheck cannot perform them, because it cannot see raw tiles.

Correct boundary:
- A single module is the only code permitted to open GFC rasters, **and it runs in its own process** per the
  isolation requirement above. It returns **derived boolean loss-through-2022 masks only** — never a
  value-bearing array.
- **Every post-2022 value collapses into the SAME state as "not lost through 2022."** Post-2022 loss is
  indistinguishable from no loss at the boundary. No sentinel, no separate category, no count.
- Raw post-2022 codes are never returned, printed, logged, or serialized by any code path.
- **Metamorphic tests (required, strengthened):** assert invariance to **moving, adding, and removing
  future-loss pixels** in a synthetic raster — not merely to changing 23/24 codes. Every returned value and
  emitted output must be bit-identical across all such perturbations. A test that cannot detect an
  arbitrary *relocation* of future loss is not testing the right thing.
- This module is reviewed as its own unit before it is used to score anything.

### 2. Replay the registered selection algorithm — do not walk raw ranks (Codex r1 #4)

v1 said "take ranks 4–7". **That is not the algorithm that built the frame.** `risk/frame.py:390`
`select_round_robin` runs three locked rounds with **cross-stratum 50-km sequential inhibition**: a
candidate is retained only if it is ≥`FRAME_MIN_SEPARATION_KM` (50.0) from **every** previously retained
site, across all strata.

Verified numerically: at K=7 the inhibition never binds — all four strata retain exactly ranks 4,5,6,7,
zero skips — so v1's shortcut coincidentally produced the right 16 sites. **It diverges immediately at
K=8:** `sea_peat` rank 8 (`F4_M003.120_P0105.500`) is **24.46 km** from rank 1 and the real algorithm
rejects it. Any K≥8, including the K=9 option in (B), *requires* the replay.

Therefore:
- **K counts RETAINED sites, never raw rank.**
- Continue `select_round_robin` under the identical inhibition rule against all retained sites.
- **Record every skipped rank with its binding distance and the site it collided with**, as a committed
  artifact.

### 3. Freeze K, K_max, and the failure action BEFORE scoring any new candidate (Codex r1 #3, #5)

v1's step 3 ("confirm K=7, or raise K") made the frame an **outcome-adaptively sized prefix**: K became a
function of observed 2021/2022 outcomes. That is optional stopping, and it is the *same error* v1 already
rejected when it ruled out sizing K per-stratum from observed evaluability.

- **`K = K_max = 9`. FROZEN. No increment. Terminal action on failure is to ABANDON the widened analysis**
  — never to enlarge K. This is the single binding rule; no alternative K remains live anywhere in this plan.
- K was chosen on 2026-07-20 from the *incumbent* 12 sites' behaviour, before any new candidate was scored,
  and that ordering is what keeps it admissible.
- **The step-4 precheck is STRICTLY NON-BINDING.** Its only permitted consequence is **stop and re-plan
  with Josh in a logged amendment**. It may never silently resize the frame.
- **Disclosure does not cure optional stopping.** If any later amendment uses these precheck outcomes to
  enlarge K, the resulting analysis is **outcome-adaptive exploratory work** and must be labelled as such.
  Logging the change would disclose the bias, not remove it.
- All downstream quantities are parameterized, never hardcoded: **sites = 4K**, **new download site-years
  = 20K − 36**, **inner contagion fits = 4K(4K − 1)**.

### 4. Diagnostic precheck over the new candidates (non-binding)

Score the retained new candidates through the §1 censoring boundary on the permitted origins only.

- **Define "quiet" exactly (Codex r1 #7).** The diagnostic indicator is frozen in advance: a site is quiet
  if it falls below the ≥5-component floor on the **worst permitted origin** (`min` over outcomes 2021 and
  2022), matching the existing script's `worst` semantics.
- **The diagnostic indicator is NOT the survival curve's parameter (Codex r2 #6).** P(quiet in at least one
  of two historical years) is **not** the single-year quiet probability for 2023, so a worst-of-two rate
  **must never be substituted into the binomial survival curve** — that silently changes the estimand.
  Therefore: keep worst-of-two as a **conservative, non-binding stability diagnostic**, report **each origin
  separately**, and label the survival curve's `q` explicitly as an **assumed single-test-year rate**, not
  as anything estimated from these data.
- **Report uncertainty, not a point guarantee (Codex r2 #5).** The informative unit is the `K−3` additions
  **within one stratum**, not all `4K−12`. With zero observed quiet, the stratum-specific one-sided 95%
  upper bound is **`1 − 0.05^(1/(K−3))`** = **52.7% at K=7** (4 additions) and **39.3% at K=9** (6). Any
  pooled bound is reported **separately**, with its homogeneity and independence assumptions stated.
- **Present survival as a sensitivity curve over assumed quiet rates**, never as a measured guarantee.
- **Also report projected components per stratum** against the ≥30 arm, flagged as a permitted-origin
  projection and not a test-origin fact.

### 5. Pin the GFC release and verify frame artifacts (Codex r1 #13, #12)

- **Freeze the exact study GFC release and per-tile checksums before scoring any new candidate.** The
  precheck currently pins `GFC-2024-v1.12` "for the precheck only" while the study's version is deferred;
  historical loss layers get revised, so frame selection and final labels could silently disagree.
- **Fix the mosaicking, which can currently corrupt the diagnostic scores** (it can never choose or change K — K is frozen at 9 and the precheck is non-binding). `precheck_evaluability.py:99`
  swallows `RasterioIOError` and continues whenever *another* tile succeeds, so a missing required seam
  tile yields a silently partial array; and seam pieces are joined by **shape matching**, not by transform,
  which can split or merge connected components across a seam. Fix: **fail closed on every required tile**,
  mosaic transform-aware, assert identical grids across layers and complete bbox coverage, and add
  north/south, east/west, and four-tile-corner seam tests.
- Re-verify `candidate_frame.csv` and `ordered_draw.csv` SHA-256 against `analysis_sites.json` on **every**
  run, and require a one-to-one rank↔candidate join.

### 6. Amend `FORECAST-PLAN.md` for n=4K (Codex r1 #9, #10, #11)

**These substitutions apply ONLY to Specification W. `FORECAST-PLAN.md` v11 is left untouched (see (A)).**

**Every substitution is a K formula (Codex r2 #7); the numeric columns are illustration only.**

| v11 line | Current | Specification W | K=7 | K=9 |
|---|---|---|---|---|
| 13 | scope claim "~3–5 sites/biome" | `K` sites/biome | 7 | 9 |
| 126 | pooled "12 frame sites" (corrected-headline target set) | `4K` | 28 | 36 |
| 162/168 | RNG spawn key, LOSO fold index 0–11 | `0…4K−1`; code-6 `0…8K−1` | 0–27; 0–55 | 0–35; 0–71 |
| 178 | normalization from "11 frame training sites" | `4K−1` | 27 | 35 |
| 217 | nested LOSO "the other 11 frame sites" | `4K−1` | 27 | 35 |
| 221 | "Frame-only (12 sampled sites) primary" | `4K` sampled sites | 28 | 36 |
| 238 | inner cross-fitting, "other 10" sites | `4K−2` | 26 | 34 |
| 238 | "each of the 11 non-held-out sites" | `4K−1` | 27 | 35 |
| 240 | "the ordinary 12-site LOSO predictions" | `4K`-site | 28 | 36 |
| 244 | contagion domain "11 non-held-out frame sites" | `4K−1` | 27 | 35 |
| 280 | bootstrap `S` (uninstantiated) | pooled `S = 4K`, regional `S = K` | 28 / 7 | 36 / 9 |

**Constants that must NOT be mechanically replaced.** The evaluable-site gate (≥3), the regional component
gate (≥30), and the SAR pilot site count (3) are unrelated 3-values. A blind find-and-replace corrupts
them. Classify each explicitly as unchanged.

**RNG (Codex r1 #10, r2 #7) — a wider range is not sufficient.** Two distinct problems: for analysis code
6, `unit_index = 2×fold + architecture` spans **`0…8K−1`** (0–55 at K=7, 0–71 at K=9), not `0…4K−1`; and
because fold index is assigned *ascending by held-out site id*, inserting new sites lexicographically
**renumbers the existing sites' folds**. Under (A) that renumbering must not touch the primary — it applies
inside Specification W only. Fix: after K is fixed, **freeze and serialize the complete
`site_id → fold_index → code-6 unit_index` table** for Specification W as a committed artifact, with
collision and order-invariance tests for every analysis code.

**§4 audit allocation — decision (C), FINAL: retain `n_b = 180` for both specifications.**

**The (A) revert largely dissolves this problem.** With **12-site v11 as the primary**, preserved verbatim,
its audit is untouched: 3 strata per biome, mean allocation `180/3 = 60` per site — exactly the original
design the budget was frozen for. **The degradation applies only to Specification W** (9 strata per biome,
`180/9 = 20` per site), which is **exploratory**. The **same fixed `n_b = 180` rule binds both
specifications** (§6); only the *consequence* of the reduced nominal allocation differs, and it reaches W
alone. That reduced allocation **can** raise W's survey SE, but the direction is **not** guaranteed
(Codex r3 #5, r8 #3 — added strata can raise OR lower precision depending on population sizes and
within-stratum variance); the frozen variance calculation decides it. The general floor total is
`2K = 18` per biome.

**v6's rule was not computable and is withdrawn (Codex r6 #2-#4).** It called for a "prospective precision
assessment" using §4's variance — but that formula needs `N_bs` from **2023 positives** and `D̂`, `d_i`,
`s²_{e,s}` from **audit outcomes**. It is an estimation formula, not a planning one, so it could not run
inside the embargo. It also sized only `D̂` while the stated motivation is the `1.96·SE_survey(TE_corr)`
gate, and it borrowed §10's **two-sided** 0.10 bootstrap half-width as if it were §4's **one-sided** UCB.
Three separate errors, all Claude's.

**Its round-6 replacement is ALSO withdrawn (Codex r7 #2).** That planning model never specified how
2021/2022 `N_s` combine, the worst-case variance formulas, the `TE_corr` planning construction and its
denominator, either numerical threshold, or whether every biome and year must pass — so "meets both
planning criteria" was not evaluable either. Building a second unevaluable apparatus to size an
**exploratory** analysis's audit budget is not worth the complexity it adds.

**SINGLE BINDING RULE: `n_b = 180` is RETAINED, unchanged, for BOTH specifications.**
- **12-site v11 (primary):** 3 strata per biome, **nominal** mean `180/3 = 60` per site when the full
  budget is used. The **complete v11 allocator is preserved unchanged** — censuses, floors of 2, caps,
  iterative largest-remainder redistribution on remaining capacity, FPC (Codex r7 #4). Individual sites
  need not receive 60, and the realised total can fall below 180 where site populations are exhausted;
  "60" is a nominal mean, **not** an equal allocation.
- **Specification W (exploratory):** 9 strata per biome, nominal mean `180/9 = 20` per site, **accepting
  whatever intervals result** (potentially wider or narrower — Codex r8 #3). W applies the **unchanged
  numeric §4/§10 gates at `n_b = 180`**: wide uncertainty makes those gates **HARDER TO PASS**, so a W audit that misses the
  unchanged numeric inequalities **fails the gate and W's forecasting claim is withheld** (Codex r8 #4). "Unevaluable"
  is reserved strictly for prespecified mathematical undefinedness — e.g. a zero denominator — not for a
  gate that is merely hard to pass. Either way the primary is untouched.

Unit-test the allocator for `N=0`, censuses, floors, caps, iterative redistribution, FPC, and K-stratum
summation at K=9.

**§10 block bootstrap.** Site-clustered resampling unit counts change; re-derive CI widths rather than
carrying them over.

### 7. Build the widened frozen manifest (Codex r1 #15)

No step in v1 actually produced the artifact the downloader consumes. `risk/frame.py:472`
`finalize_analysis_sites` reconstructs only the original selected list and only the global `FEATURE_YEARS`.

Specify a deterministic **amendment-manifest builder** that replays selection (§2), assigns cohort labels
and rank/provenance fields, **preserves the original artifact hashes**, and emits a newly hashed 4K-site
manifest. Freeze that manifest before any download.

**It must extend periods for ALL 4K sites, not only the new ones (Codex r2 #9).** v2 computed CHIRPS-derived
seasonal windows and 2018–2022 periods for new candidates only — but the **incumbent 12 sites also need
frozen 2021 and 2022 seasonal periods**, both for the download schedule (§8) and for the five-year
completeness inventory (§11). Without them the incumbents' new years have no defined acquisition windows
and the schedule cannot be derived. Correct order: **extend periods through 2022 for every one of the 4K
frame sites, then derive the missing (site, year) schedule by subtracting already-verified artifacts.**

### 8. Give the forecast study its own download schedule (Codex r1 #14 — BLOCKER)

`risk/download_timeseries.py` **cannot execute this download today**:
- **:182–185** requires exactly `FRAME_REQUIRED`=12 frame sites at 3 per group → `RuntimeError`.
- **:187** requires each site's periods to equal `FEATURE_YEARS` exactly.
- **:193–194** `AssertionError("Post-2020 imagery reached download manifest")` for any year > 2020.
- **:476** loops over every manifest site, including the 7 legacy sites.

**Do not simply widen the global constants.** Changing `FEATURE_YEARS` to five years conflates *archive
availability* with the forecast's *rolling three-year model histories*, and would pull unwanted legacy-site
years. Instead: introduce a **forecast-specific immutable site-year download schedule** — an explicit list
of exactly the (site, year) pairs missing — decouple archive years from model-history years, validate
4K sites at K per stratum, and restrict the run to precisely those **20K − 36** site-years.

### 9. Migrate every reused frame-size assertion (Codex r1 #16)

Reused code still hardcodes the old frame: `risk/config.py:125-126,144` (`FRAME_GROUP_ORDER`,
`FRAME_SITES_PER_GROUP=3`, `FRAME_REQUIRED=12`), `risk/cohort.py:44` (cohort counts of 3),
`risk/models.py:183` (LOSO 12/11). Inventory **every** such assertion and test, then either parameterize it
from the frozen forecast manifest or **prove in writing that the module is outside the active
implementation path**. Silence here means a stale assertion fires mid-run, or worse, does not.

### 10. Download — 144 site-years, 51.3 GB at the frozen K=9

| Cohort | Sites | Years each | Site-years |
|---|---|---|---|
| Existing frame | 12 | 2021, 2022 | 24 |
| New frame | 4K − 12 | 2018–2022 | 20K − 60 |
| **Total** | **4K** | | **20K − 36** |

At a measured **356 MB per site-year** (`dispersion.tif` 253 MB, `reflectance.tif` 101 MB, `clearobs` and
`solar_zenith` ~1.3 MB each): **K=9 (frozen) → 144 site-years → 51.3 GB decimal (50.06 GiB)**. Disk is not
binding (348 GB free); CDSE throughput and flakiness are.

**A partial archive is resumable but NOT analysable (Codex r1 #18).** v1's "staging strata-balanced so a
partial run still yields a usable frame at some lower K" contradicts freezing K — analysing a smaller
prefix because downloads failed is an availability-driven protocol deviation. Staging stays
strata-balanced for operational sanity, but **only the complete frozen-K manifest may enter preprocessing
or inference.**

### 11. Completeness gate, not an existence scan (Codex r1 #17)

`risk/census/verify_composites.py` is **not** the check v1 claimed. It scans whatever TIFFs happen to
exist, so it cannot detect a *missing* site-year; it checks neither band schema nor provenance; it sweeps
in unrelated sites; and it **exits zero even after recording corrupt files**. A half-downloaded archive
passes it.

Replace with a manifest-derived completeness gate asserting the exact expected inventory — at the frozen
K=9, **`4K × 5 × 4 = 720` frame TIFFs, of which `720 − 144 = 576` are new** (12 × 3 × 4 = 144 already
held) — with
exact band schemas, provenance checks, full decode, and a **nonzero exit** on any missing, corrupt, or
all-nodata artifact.

### 12. Re-baseline compute before committing (Codex r1 #19)

Inner contagion fits go 132 → **4K(4K−1)** = **1,260 at the frozen K=9** (9.5×), and each inner fit trains
on `4K−2` = **34** sites instead of ~10, so linear site-fit work rises roughly **(1260×34)/(132×10) ≈ 32.5×**
— before deep architectures, ablations, tuning, and two evaluation scales. **This is the single largest
feasibility risk in the plan** and the pilot in §12 is what tests it.

**Ordering correction (Codex r2 #10).** v2 required benchmarking representative full folds *before*
committing K, while §3 commits K *before* any new candidate is scored — and a real widened fold cannot be
benchmarked before its data exist. That ordering is impossible. Correct sequence: **freeze K on scientific
grounds first**; run the compute pilot afterwards as a **non-binding feasibility gate**; and **predeclare
that pilot failure delays or abandons the widened analysis** rather than changing K, the model, or the
architecture after candidate outcomes have been seen.

## Key decisions & tradeoffs

**Widening replays a registered algorithm; it does not walk a convenient order.** The defensibility rests
on `select_round_robin` being replayed exactly under 50-km cross-stratum inhibition against a candidate
permutation whose SHA-256 still matches the recorded hash — not on rank arithmetic. Contrast the rejected
alternative of lowering the ≥5 floor, which selects a threshold to fit an observed result.

**The existing 12 sites are all retained**, so the tainted site `F1_P000.180_M0063.250` stays in and no
label-based swap occurs. This is necessary but, per (A), **not sufficient** to call the amendment
leak-free.

**K is frozen before new candidates are scored, and the precheck cannot resize the frame.** This is what
separates a pre-registered widening from an outcome-adaptive one.

**`risk-forecasting` was merged into this branch** (`5748aa3`, conflict-free, 35 tests passing) because the
forecasting study reuses the whole `risk/` package.

## Risks / open questions

- **The root cause is buffered, not fixed.** The frame was screened on 2016–2020 activity
  (`recent_loss_2016_2020`, independent of `FEATURE_YEARS` by design — `risk/config.py:54-56`) while the
  study predicts 2023 activity, and frontier activity moves. Larger K increases resilience against that
  drift; it does not correct the misalignment. A high measured quiet rate at the new ranks would be evidence
  the **screen** is the problem and that raising K treats a symptom.
- **Widening may harden the §4 retention gate** by shrinking per-site audit allocations (finding #11). It
  is not yet established that widening is net-positive for the audit.
- **SAR is unsized.** All figures here are optical only.
- **`sea_peat` has only 147 candidates** and is where inhibition first binds (rank 8 at 24.46 km). At K=9
  it is the stratum most likely to need deep ranks.
- **CDSE flakiness.** 144 site-years is ~6× the largest run attempted so far.
- **Compute at ~32.5× site-fit work** (1,260 inner fits × 34 training sites) is the single largest
  feasibility risk in the plan and may force a hardware or scope rethink on an 8 GB VRAM laptop.

## Out of scope

- **Any FURTHER outcome-responsive change** to the frame, K, or any frozen parameter. (The widening itself
  is outcome-responsive and is disclosed as such — see (A); what is excluded is compounding it.)
- **Lowering the ≥5 component floor or the ≥3 evaluable-sites gate** — threshold shopping, rejected twice.
- **Reading the 2023 test outcome PRE-LIFT** — at any step, for any reason, until the §1 embargo-lift
  transition. Post-lift reading is the point of the study and is governed by §1's phase boundary.
- Re-screening the candidate frame on a new criterion (considered, deferred).
- Changing the finished detector paper on `main`, or reviving any retired PIF / annulus design.
