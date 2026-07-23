# Plan Review Log: Fix the Specification W completeness gate's clearobs band-label expectation
Act 1 (grill) complete — plan locked with the user (Josh). MAX_ROUNDS=7.

## Round 1 — Codex (gpt-5.6-sol, xhigh)
VERDICT: REVISE. Findings:
- High-1: `(None,)` is exact-match but any unnamed 1-band raster with finite values passes schema/decode/provenance; gate checks no clearobs semantics. Fix: add clearobs invariants (nonneg integer, resolution/CRS/coverage) + negative test.
- High-2: `0 CHECKSUM` is not evidence — without `--pinned-inventory`, checksum comparison is skipped yet `complete` can be true. Fix: two-pass bootstrap-and-verify; final report via `--pinned-inventory`.
- High-3: gate validates incumbent inventory only by shape, never compares 144 incumbent checksums vs `schedule["verified_existing_inventory"]`; a mutated incumbent could be re-pinned. Fix: compare each run + regression test.
- Medium-4: `--inventory-output` overwrites; a later unpinned run can replace the anchor. Fix: write-once.
- Medium-5: plan misidentified the wrong-description test — it corrupts solar_zenith, not clearobs. Fix: dedicated clearobs negative test.
- Medium-6: fixture derives descriptions from production BAND_SCHEMAS → positive test partly tautological. Fix: assert literal `(None,)` read-back independently.
- Low-8: moving 2016 TIFFs orphans `2016_provenance.json`. Fix: move provenance too.
- Confirmed: skipping `set_band_description` on None is correct; no other code asserts the clearobs name (index+filename consumption).

### Claude's response
Accepted High-2 (two-pass bootstrap→pinned-verify; committed report is the pinned pass), High-3 (cross-check 144 incumbent checksums vs the schedule's frozen inventory every run + regression test), Medium-4 (write-once `--inventory-output`), Medium-5 (dedicated clearobs negative test), Medium-6 (independent literal `(None,)` oracle), Low-8 (move provenance with the TIFFs).
Partially accepted High-1: added ONE scoped invariant — clearobs valid pixels must be `>= 0` (a clear-observation count cannot be negative) + a negative-value test. DECLINED the broader per-band CRS/resolution/coverage/integer-dtype checks: the gate has never validated those for any band, clearobs is float32 (an integer-dtype rule would reject valid incumbent data), and per-band semantic validation belongs in a separate uniformly-applied enhancement, not a rider on a label fix. Logged in the plan's Out-of-scope.

## Round 2 — Codex
VERDICT: REVISE. Closed: High-3, Medium-5, Medium-6, Low-8. Remaining:
- High: non-negativity alone doesn't close the arbitrary-raster hole; clearobs is a sum of booleans → should be integer-valued (float32 storage). Fix: require nonneg AND integer-valued, or narrow the claim.
- High: pinned-verify "records" unspecified — no report field/test; unpinned vs pinned both show CHECKSUM:0. Fix: explicit `checksum_validation` metadata (mode, pinned_inventory_sha256, verified) + test.
- Medium: write-once underspecified/racy; report is written before inventory, so a failed bootstrap rerun could overwrite the pinned report. Fix: exclusive `"x"` mode, preflight before any report, distinct bootstrap path.
- Medium (new): semantic check is only cheap if it reuses the existing decode; a separate read(1) rereads 180 rasters. Fix: fold into `_valid_data_present`.
- Medium (new): verify_composites.py ~239 nonblank lines; additions cross the ~250 ceiling. Fix: extract checksum/inventory validation to a helper.
- Low: `CHECKSUM/INCUMBENT` ambiguous (codes are an exact enum). Fix: reuse `CHECKSUM` with incumbent detail.

### Claude's response
Accepted all. Strengthened the semantic invariant to nonnegative AND integer-valued (values are boolean sums), folded into the existing `_valid_data_present` decode pass (no second read), emitted via a new properly-enumerated `SEMANTIC` code. Added observable pinned verification: `checksum_validation` report metadata (mode/pinned_inventory_sha256/verified) with both-mode tests. Made `--inventory-output` exclusive `"x"` with a preflight before any report write and a distinct bootstrap path. Incumbent mismatch now uses the existing `CHECKSUM` code with an incumbent-specific detail (no new code), asserted exactly in the regression test. Extracting the checksum/inventory logic into a small helper module to keep the gate cohesive/within the module-size norm.

## Round 3 — Codex
VERDICT: REVISE. All Round 2 findings addressed in substance. Remaining:
- High: unpinned bootstrap reports verified:false but gate still sets analysis_allowed=complete → an unpinned archive can advertise analysis-ready. Fix: analysis_allowed = complete AND mode=="pinned" AND verified; keep complete:true for a structurally-valid bootstrap.
- Medium: tests cover pinned/unpinned success but not a FAILED pinned comparison's metadata. Fix: mutation test asserts mode=="pinned", verified false, complete false, analysis_allowed false.
- Low: out-of-scope paragraph stale (still says only "non-negativity"). Fix: describe the accepted nonneg/integer invariant; reserve only CRS/resolution/coverage/dtype for later.

### Claude's response
Accepted all three. analysis_allowed is now gated on pinned+verified (bootstrap keeps complete:true so inventory generation still works). Added the failed-pinned metadata assertions to the mutation test and analysis_allowed assertions to the pinned/unpinned tests. Corrected the out-of-scope paragraph to state the accepted nonnegative+integer-valued clearobs invariant and reserve only CRS/resolution/coverage/dtype for a future uniform enhancement.

## Round 4 — Codex
VERDICT: REVISE. Round 3 findings addressed. Remaining test gaps:
- High: `_artifacts()` builds the schedule with placeholder hashes (kind[0]*64), not hashes of the created TIFFs, so unconditional incumbent verification would make every complete-archive test report 144 CHECKSUM failures. Fix: create TIFFs first, derive incumbent hashes from them, then build schedule/provenance.
- Medium: reusing an incumbent mutation under --pinned-inventory trips both the incumbent-schedule and pinned mismatches (CHECKSUM==2), conflating contracts. Fix: unpinned incumbent mutation for the schedule check; pinned mutation of a newly-scheduled TIFF for failed-pinned metadata.

### Claude's response
Accepted both. Fixture refactor: create synthetic TIFFs first, derive the 144 incumbent inventory hashes from the real files, then build the schedule+provenance so complete-archive tests pass the incumbent check. Split the mutation tests: (a) unpinned incumbent mutation asserts exactly one CHECKSUM issue with incumbent detail; (b) pinned mutation of a newly-scheduled TIFF asserts the failed-pinned metadata (mode pinned, verified/complete/analysis_allowed false) in isolation.

## Round 5 — Codex
VERDICT: APPROVED. All Round 4 findings addressed; no remaining material issues. Plan converged after 5 rounds (MAX_ROUNDS=7).
