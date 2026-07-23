# Plan: Fix the Specification W completeness gate's clearobs band-label expectation
_Locked via grill — by Claude + Josh (2026-07-23)_

## Goal
The 720-TIFF Specification W completeness gate (`risk/census/verify_composites.py`) returns
`complete: false` on two non-data issues, blocking certification of an archive whose data is 100% intact
(all 720 TIFFs decode; 0 CORRUPT, 0 ALL_NODATA, 0 MISSING, 0 PROVENANCE, 0 CHECKSUM). Make the gate pass
by correcting a wrong expectation (not by weakening a real check) and by removing two out-of-frame stray
files, so the certified pinned 720-checksum inventory is written and the archive is analysis-ready.

## Context / evidence
- **180 SCHEMA failures, all `clearobs`** (every one of 36 sites x 5 years). The gate expects the clearobs
  band named `'clearobs'` (`BAND_SCHEMAS['clearobs'] = ('clearobs',)`), but every real clearobs composite —
  **incumbent (prior-study) and newly downloaded alike** — has a single **unnamed** band
  (`descriptions=(None,)`) with valid data (float32, 11.5M valid px, values 20–40 = clear-observation
  counts). `solar_zenith` is named `'sunZenithAngles'` and passes; reflectance/dispersion pass. So this is a
  gate-expectation mismatch, never validated against a real clearobs file, not a data/download defect.
- **clearobs is read by index and filename, never by name.** `risk/prepare.py:198` locates it as
  `f"{year}_clearobs.tif"` and `risk/prepare.py:139` reads `source.read(1)`. No code reads the clearobs band
  *name*. The generic readers already tolerate `None` descriptions with a `band_{i}` fallback
  (`grid.py:86`, `phase0.py:73`, `prepare.py:78`). Naming the band would be cosmetic.
- **2 UNEXPECTED**: `F1_P000.180_M0063.250/2016_clearobs.tif` and `.../2016_reflectance.tif` — leftovers
  from the earlier study, outside the frozen 2018–2022 frame. FEATURE_YEARS are 2018–2020 (read by explicit
  filename), so 2016 files are never read by any downstream code.

## Approach
1. **Gate label fix.** In `risk/census/verify_composites.py`, set `BAND_SCHEMAS['clearobs'] = (None,)`. The
   SCHEMA check then requires exactly one band whose description is `None`, matching the real, valid clearobs
   output of both downloaders. Band-count, full-decode, valid-pixel, and all-nodata checks are unchanged.
2. **Scoped clearobs semantic invariant (Codex r1 High-1 / r2).** clearobs is the temporal SUM of clear
   observation booleans, so valid pixels must be **nonnegative AND integer-valued** (`value == floor(value)`
   despite float32 storage). Enforce both, raising a new, properly-enumerated `SEMANTIC` issue code
   otherwise. This distinguishes a real clearobs count raster from an arbitrary nonnegative fractional
   raster, without inventing per-band CRS/resolution/coverage/dtype rules the gate has never applied
   (out of scope — see Key decisions). Real clearobs values are integral 20–40, so no valid file is rejected.
   **Fold the check into the existing full-decode pass** (extend `_valid_data_present`, which already reads
   every band) so the 180 large clearobs rasters are not read a second time.
3. **Incumbent checksum integrity (Codex r1 High-3 / r2 Low).** During every gate run, cross-check each of
   the 144 incumbent (2018–2020) on-disk checksums against `schedule["verified_existing_inventory"]` (the
   independent hashes frozen when the schedule was created). A mismatch raises the existing enumerated
   `CHECKSUM` code with an incumbent-specific **detail** string (no new code). Add an incumbent-mutation
   regression test asserting that exact code+detail contract.
4. **Write-once inventory + observable pinned verification (Codex r1 Medium-4 / r2 High/Medium).**
   - `--inventory-output` creates the inventory with **exclusive mode (`open(..., "x")`)** so it can never
     overwrite an existing anchor (atomic, not check-then-write). Re-verification goes via `--pinned-inventory`.
   - **Preflight before writing anything:** if `--inventory-output` targets an existing file, fail before any
     report is written, so a re-run cannot clobber a previously committed report. Keep the bootstrap report
     path distinct from the final committed report path.
   - Add explicit report metadata `checksum_validation = {mode: "pinned"|"unpinned", pinned_inventory_sha256:
     <hash|null>, verified: bool}` so a pinned-verified run is distinguishable from an unpinned bootstrap
     (both otherwise show `CHECKSUM: 0`). Test both modes.
   - **Gate `analysis_allowed` on real verification (Codex r3 High).** Redefine
     `analysis_allowed = complete and checksum_validation["mode"] == "pinned" and checksum_validation["verified"]`.
     A structurally-valid bootstrap still sets `complete: true` (so inventory generation works), but only a
     pinned run whose checksums actually matched may advertise the archive as analysis-ready.
   - **Extract** the checksum/inventory logic (incumbent cross-check, pinned compare, write-once, metadata)
     into a small helper module so `verify_composites.py` stays cohesive and within the repo's module-size
     norm (confirm the norm during build).
5. **Test corrections** in `forecast/tests/test_completeness_gate.py`:
   - **Fixture ordering (Codex r4 High).** The current fixture builds the schedule with placeholder incumbent
     hashes (`kind[0]*64` via `_inventory()`), which the new incumbent cross-check would read as 144 CHECKSUM
     failures on every otherwise-complete test. Refactor the fixture to: create the synthetic TIFFs first,
     derive the 144 incumbent inventory hashes from those actual files, then build the schedule + provenance
     from the real hashes. Every "complete archive" test then passes the incumbent check.
   - Helper (~L52) skips `set_band_description` when the schema entry is `None` (build the band unnamed).
   - **Independent oracle (Codex r1 Medium-6):** the positive test asserts the clearobs read-back equals the
     literal `(None,)`, NOT a value derived from `BAND_SCHEMAS`, so the test is not tautological.
   - **Dedicated clearobs negative test (Codex r1 Medium-5):** the existing wrong-description test corrupts
     `solar_zenith`, not clearobs. Add a test that builds an unnamed clearobs (`descriptions == (None,)`),
     sets band 1 to `"wrong"`, and asserts a SCHEMA failure.
   - Semantic test: a clearobs raster with a **negative** value and one with a **fractional** value each
     assert the new `SEMANTIC` issue fires; a real integral clearobs passes.
   - Checksum-metadata test: a pinned-verify run reports `checksum_validation.mode == "pinned"`,
     `verified == true`, correct `pinned_inventory_sha256`, and `analysis_allowed == true`; an unpinned run
     reports `"unpinned"`, `verified == false`, and `analysis_allowed == false` (even though `complete`).
   - **Separate the two checksum contracts (Codex r4 Medium).** An incumbent mutation trips both the
     incumbent-schedule check and a pinned check at once, conflating them. Use two isolated tests:
     (a) *unpinned* incumbent mutation → exactly one `CHECKSUM` issue carrying the incumbent detail, `complete`
     false; (b) *pinned* mutation of a **newly-scheduled** TIFF → `mode == "pinned"`, `verified is false`,
     `complete is false`, `analysis_allowed is false`, isolating the failed-pinned metadata contract.
6. **Two-pass certification (Codex r1 High-2 / r2 High).** `0 CHECKSUM` alone only means comparison was
   skipped. Run: (a) **bootstrap** the inventory (`--inventory-output`, exclusive), then (b) **verify** by
   re-running with `--pinned-inventory <that inventory>`. The committed report is the pinned-verify pass; its
   `checksum_validation` metadata proves comparison ran (`mode: "pinned"`, `verified: true`) alongside
   `complete: true`.
7. **Move the 2 stray 2016 files AND their provenance (Codex r1 Low-8).** Move `2016_clearobs.tif`,
   `2016_reflectance.tif`, and `2016_provenance.json` together to a site-keyed holding dir *outside* the
   frame site folders (e.g. `<composites>/_out_of_frame/F1_P000.180_M0063.250/`). Reversible; no deletion.
8. **Re-run the forecast test suite** (`forecast/tests`, currently 54 passing) — all must still pass.
9. **Commit** (as the user, no AI trailer): the gate changes, the test changes, the pinned-verify report,
   and the write-once frame inventory. Note the 2016 file move in the message (moved files live under
   ml-data, outside the repo).

## Key decisions & tradeoffs
- **Fix the gate, not the data (Josh).** Accept `(None,)` rather than reprocess 180 clearobs composites to
  add a label nothing reads. Chosen because clearobs is consumed by index+filename; the name is cosmetic and
  re-downloading 180 files would cost hours and CDSE load for zero functional gain.
- **`(None,)` only, not `(None,) or ('clearobs',)` (Josh).** The real data is always unnamed from both the
  old and new downloaders; the stricter single-value expectation keeps the gate exact and would surface any
  *future* unexpected naming change rather than silently tolerating it.
- **Move, not delete, the 2016 files (Josh).** Reversible; preserves real imagery; does not loosen the
  UNEXPECTED guard (which legitimately catches rogue files in a site directory).
- **This does not weaken integrity.** The clearobs name was never a meaningful identity check (the band was
  never named). Identity is still pinned by filename + provenance (site/year/season-window/process-graph,
  with the Specification W schedule stamp required on the 576 new files) and by the band-count, decode,
  valid-pixel, and all-nodata checks, all retained.

## Risks / open questions
- `rasterio`'s `set_band_description` behavior on `None`: the fix sidesteps it by skipping the call, but
  confirm during build that the resulting synthetic band reads back as `descriptions=(None,)`.
- Confirm no *other* code path asserts a clearobs band **name** (grep shows only `_EXPECTED_BAND_COUNTS`
  count checks and index reads; re-confirm during build).
- After moving the 2016 files, confirm the gate's observed set equals exactly the 720 expected (no new
  UNEXPECTED/MISSING introduced by the move).

## Out of scope
- No change to the frozen manifest, schedule, seal, folds, RNG, or any downloaded composite pixel data.
- No re-download or reprocessing of any composite.
- No change to the leakage firewall, the primary 12-site v11 path, or the Specification W selection.
- No modeling/feature work; this only certifies the archive.
- **Broader per-band physical-semantic validation (Codex r1 High-1 / r2, scoped).** The gate now enforces,
  for clearobs only, that valid pixels are nonnegative and integer-valued (justified because clearobs is a
  temporal sum of clear-observation booleans). It will NOT assert per-band CRS, native resolution, spatial
  coverage, or dtype. Rationale: the gate has never validated those for any band; clearobs is stored float32,
  so a dtype rule would reject valid data; and those checks belong in a separate, uniformly-applied
  enhancement with its own plan, not a rider on this label-expectation fix.
