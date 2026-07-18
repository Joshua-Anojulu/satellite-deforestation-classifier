# Download-guard review log
Target: DOWNLOAD-GUARD-PLAN.md. Reviewer: codex-cli / gpt-5.6-sol. MAX_ROUNDS=3.

## Round 1 — Codex

## Findings

1. **The skip-cost claim is contradictory and undercounted.** The plan says validation is “only paid once” while also decoding on every skip; the current corpus is 19×3×4 = 228 files, meaning roughly 23–57 GB of compressed input per completed resume, while 20 files/site would be 38–95 GB. A one-tile or overview read is not sufficient: corruption in another band/tile—such as the observed X=7, Y=14 failure—will pass.  
Fix: Fully decode legacy files once, record an atomic validation marker tied to size/mtime, and use that marker for subsequent skips; never substitute sampled reads for full coverage.

2. **Atomicity is left unresolved, but delete-on-failure is insufficient.** A process kill or power loss bypasses cleanup, and a `cube.download()` exception currently retains any nonzero partial file because validation is never reached ([download_timeseries.py](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:184>)).  
Fix: Download to a unique sibling `.part` path, fully validate it, close it, then publish with `os.replace`; remove the temp on every failed attempt.

3. **The invalid-existing-file transition is unspecified.** If the upgraded skip check fails, the bad destination still exists; overwriting behavior is assumed, and if all retries fail the known-bad final path can remain and still fool existence-based counters.  
Fix: Quarantine or unlink an existing file immediately after confirmed decode failure before entering retries.

4. **“Any exception means corrupt” can reject valid files.** Full-array allocation can fail from memory pressure, permissions, transient storage errors, or a broken/unsupported local codec; repeated downloading cannot repair those conditions. The existing verifier sensibly reads one band at a time ([verify_composites.py](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/census/verify_composites.py:31>)).  
Fix: Decode all band block-windows with bounded memory, classify only raster open/decode failures as corrupt, and propagate environmental/resource failures without deleting the file.

5. **“Authoritative” overstates what a full base-resolution read proves.** It catches failures in referenced base-band tiles, but not corrupt overviews/internal masks, a wrong-but-decodable GeoTIFF, unexpected band count or geometry, or corruption that still forms a valid compressed stream.  
Fix: Validate nonzero dimensions and expected band/schema metadata, read masks/overviews if downstream code uses them, and describe the guarantee as “base-pixel decodability” unless an authoritative checksum exists.

6. **Retry semantics need an explicit exception path.** Four attempts are bounded, so this is not infinite, but deterministic local validation failures could trigger four expensive re-downloads; cleanup failures could also mask the actual decode error.  
Fix: Raise a dedicated validation exception inside the existing attempt loop, retry only retryable download/decode failures, preserve the final cause, and guarantee temp cleanup before sleeping or raising.

7. **The plan lacks regression tests for the integrity contract.** This is risky because a header-valid TIFF or first-tile sample can appear healthy while a later encoded tile is truncated.  
Fix: Add tests covering late-tile truncation, valid all-nodata and unusually small rasters, nonzero partial output after download failure, retry success, final-attempt cleanup, and cheap marker-backed resume.

All-nodata cubes and legitimately small cloudy composites should pass a pure decode check; nodata values do not themselves cause `src.read()` to fail. Rasterio’s open is lazy, but the proposed full band read forces decoding. The optional size comparison must remain diagnostic only.

VERDICT: REVISE
### Claude's response — ALL 7 ACCEPTED (v2)

Every finding accepted; the plan was materially wrong in two places that would have caused real harm.
- #4 (decisive): "any exception = corrupt" would DELETE valid files under memory pressure / transient
  storage / permissions and re-download uselessly. v2 adds an exception taxonomy: only RasterioIOError
  / GDAL CPLE_* count as corrupt; MemoryError/PermissionError/OSError propagate WITHOUT deletion. Reads
  band-by-band in bounded block-windows, not one giant src.read().
- #1: decode-on-every-skip is 23-57 GB per resume and a one-tile/overview read misses the observed
  non-first-tile corruption. v2 adds a validation MARKER (size+mtime_ns sidecar): full-decode once,
  then cheap marker-checked skips; never a sampled read.
- #2: delete-on-failure is not crash-safe. v2 downloads to .part, validates, then os.replace (atomic);
  a crash leaves only a .part, never a plausible final.
- #3: v2 unlinks a confirmed-bad existing dest (and stale marker) BEFORE retries.
- #5: "authoritative" overstated. v2 validates dims + band count, calls the guarantee "base-pixel
  decodability + schema", and notes overviews/masks are unvalidated because nothing downstream reads them.
- #6: dedicated _CorruptDownload exception; retry only retryable failures; guarantee .part cleanup
  before sleep/raise; preserve underlying cause.
- #7: added 8 regression tests incl. late-tile truncation, all-nodata, small raster, partial-after-
  exception, retry-then-success, final cleanup, marker-backed resume, and environmental-error-not-corrupt.

## Round 2 — Codex

V2 substantially addresses the original findings, but several safety details remain unresolved.

1. **Exception taxonomy is still unsafe.** `RasterioIOError` can wrap permission/open/I/O failures, and GDAL’s `CPLE_*` family includes environmental errors such as open, file-I/O, and out-of-memory failures—not just corrupt decoding. Classifying all of them as corrupt can still delete a valid legacy file.  
Fix: Enumerate corruption-specific cases and explicitly exclude wrapped permission, open-environment, file-I/O, and out-of-memory causes; add tests for wrapped GDAL errors.

2. **The advertised unique temp path is deterministic.** `dest.with_suffix(".tif.part")` produces one fixed path per destination, so concurrent invocations can write, validate, or delete each other’s temp file; a crash also leaves a stale path that may interfere with the next attempt.  
Fix: Use a same-directory UUID/PID temp name or a per-destination lock, and define safe stale-temp cleanup.

3. **Expected band-count plumbing is missing.** `_decodes(path)` has no expected-count argument, while `_download` currently receives only `cube` and `destination`. Importantly, both `reflectance` and `dispersion` are six-band cubes; `clearobs` and `solar_zenith` are one-band ([download_timeseries.py](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/risk/download_timeseries.py:99>)).  
Fix: Pass `expected_band_count` explicitly from `download_manifest`—6 for reflectance/dispersion and 1 for clearobs/solar—and test both cases plus a mismatch.

4. **Environmental-error cleanup is contradictory.** The plan says cleanup occurs before every raise, but also says environmental exceptions propagate “without deletion.” Preserving an existing `dest` is correct; leaving an uncommitted `.part` after `MemoryError` is not.  
Fix: State explicitly that environmental failures never delete an existing final file, but always best-effort-clean the current process’s uncommitted temp before propagating.

5. **Marker handling needs fail-closed/versioned semantics.** A non-atomic or malformed `.ok` write could currently abort resume, and `{size, mtime_ns}` does not identify which validator/schema produced the marker.  
Fix: Write markers through temp-plus-replace, include a validator version and expected band count, and treat missing, malformed, unknown-version, or mismatched markers strictly as cache misses.

6. **The regression suite misses the most important new branches.** The truncation test must prove an early tile reads successfully before a later tile fails; otherwise it may merely test an unreadable header. Tests are also missing for wrapped permission errors, wrong band count, malformed/mismatched markers, and temp-name collision.  
Fix: Add those assertions and cases before implementation approval.

The no-sampled-read rule, one-time legacy validation, invalid-final unlink, scoped decodability guarantee, all-nodata handling, and bounded retry count are otherwise correctly addressed.

VERDICT: REVISE
### Claude's response — all 6 accepted (v3)

Converging: round-2 findings are refinements of round-1's accepted changes, no new fundamentals.
- r2#1 (decisive refinement): RasterioIOError/CPLE_* wrap permission/OOM/IO too, so class alone can't
  separate corruption from environment. v3 switches to FAIL-SAFE: re-raise anything with an
  environmental cause/errno; classify corrupt ONLY for decode/tile errors; when AMBIGUOUS do not delete.
- r2#2: fixed .part path collides. v3 uses a same-dir pid+uuid4 temp name + stale-temp cleanup.
- r2#3: v3 passes expected_band_count explicitly (reflectance/dispersion=6, clearobs/solar=1); wrong
  count is itself a corruption signal.
- r2#4: v3 — environmental failures never touch existing final dest but always best-effort clean the
  current process's own uncommitted temp before propagating.
- r2#5: v3 writes markers atomically (temp+replace) with validator_version+band_count+size+mtime_ns;
  missing/malformed/unknown/mismatch = cache miss, never abort.
- r2#6: v3 truncation test asserts an early tile reads before a later tile fails; added wrong-band-count,
  wrapped-permission-error, malformed-marker, and temp-collision tests.

## Round 3 — Codex (MAX_ROUNDS reached)

V3 is close, but two safety ambiguities remain.

1. **Stale-temp cleanup can race a live download.** Line 44 says to remove matching temps without defining “stale”; glob-deleting can remove another process’s active PID/UUID temp, defeating the concurrency-safe naming. Marker temp files need the same protection.  
Fix: Never clean arbitrary matching temps inline; remove only files whose embedded PID is no longer alive and which exceed a conservative age, or perform orphan cleanup separately under a lock.

2. **Exception precedence is not fully deterministic.** `IReadBlock` and “not recognized as supported format” can accompany environmental file-I/O or missing-codec conditions. The plan implies environmental causes win, but does not explicitly define precedence when a message matches both categories.  
Fix: Specify: inspect the complete cause/errno chain first; if any environmental indicator exists, propagate; otherwise accept only an enumerated decode signature as corrupt; every unmatched case propagates ambiguously with the final preserved.

3. **Retry wording still contradicts temp cleanup.** Lines 45–46 require cleaning the owned temp on environmental errors, while line 70 says environmental exceptions propagate “without deletion.”  
Fix: Change line 70 to “without deleting the final destination; always best-effort-delete the owned uncommitted temp.”

4. **Tests do not cover the two fail-safe defaults above.** The stale-temp test covers an orphan, not a live concurrent temp, and the wrapped-permission test does not cover an unknown `RasterioIOError` with no recognized cause.  
Fix: Add tests proving live foreign temps survive cleanup and an unclassified Rasterio/GDAL error propagates without deleting the existing final.

Also update the title and design labels from “v2” to “v3.” The explicit band mapping, atomic publication, versioned markers, full-tile validation, retry cap, and valid all-nodata/small-file handling are otherwise sound.

VERDICT: REVISE
### Claude's response — all 4 accepted (v3-final); loop stopped at round cap

Round cap (MAX_ROUNDS=3) reached without a printed APPROVED, but this is CONVERGENCE, not deadlock:
each round's findings shrank and every one was conceded. Round 3's 4 items are precision/wording and
are all incorporated:
- r3#1: "stale" temp now DEFINED — orphan sweep removes a temp only when its embedded PID is dead AND
  it exceeds a conservative age; the write path deletes only its own temp by exact name, never a glob,
  so a live foreign download's temp/marker is never touched.
- r3#2: deterministic exception precedence — inspect the full cause/errno chain FIRST; ANY
  environmental indicator => propagate (environment wins); else only an enumerated decode signature =>
  corrupt; every unmatched case propagates fail-safe with the original preserved.
- r3#3: wording contradiction fixed — env exceptions "propagate without deleting the FINAL dest; always
  best-effort-delete the owned temp."
- r3#4: added tests — live foreign temp survives cleanup; unclassified Rasterio/GDAL error propagates
  without deleting the final.
- title/labels moved to v3.

STATUS: substantively converged. All findings across 3 rounds accepted and incorporated; the last
round's items were mechanical. Not re-submitted for a 4th round (round cap + this session's context is
near-exhausted). This is a REVIEWED, converged plan awaiting the user's implement-or-not decision, NOT
an approved-and-verified one — the difference is that Codex has not seen v3-final.

## Act 3 — Build (codex-build)

### Round 1 — Codex build
Builder: codex-cli 0.144.5, gpt-5.6-sol xhigh. Launched by the user (harness blocked --yolo from Claude). thread_id 019f7550-ceba-7690-af63-a20ff9d7371e. ~11m50s.
Report: implemented v3 spec exactly, no deviations; self-reported 35 passed.
Files: risk/download_timeseries.py (+293/-10), risk/tests/test_download_guard.py (+305, 13 tests).

### Claude's verdict — VERIFIED, ready to commit
- Read full diff: faithful to v3. Fail-safe precedence (env checked before decode via _exception_chain; unmatched RE-RAISES); atomic unique-temp -> os.replace -> versioned marker; marker cache-miss on any mismatch; orphan sweep gated on dead-PID (_pid_is_alive: Windows OpenProcess/WaitForSingleObject + POSIX os.kill) AND >24h age; band-count threaded from _EXPECTED_BAND_COUNTS.
- Ran pytest MYSELF: 35 passed in 1.81s.
- Load-bearing tests are real, not trivial: late-tile truncation asserts an early tile reads then the last tile raises then _decodes False; live-foreign-temp keeps the current (alive) PID and backdates past the age gate, asserting survival; unclassified RasterioIOError propagates and leaves the existing final untouched.
- REAL-DATA smoke test (not just synthetic fixtures): _decodes True for all 4 cube types on actual rondonia composites at the right band counts, wrong count rejected, marker round-trips.
- No stray .ok/.part left in the data dir.
Verdict: spec-faithful, proven on real + synthetic data. Recommend commit.
