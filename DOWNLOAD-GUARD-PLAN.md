# Plan: harden `_download` against silently corrupt/truncated GeoTIFFs (v3, post-Codex ×3)

> Scope: a data-integrity guard in `risk/download_timeseries.py::_download`. `PLAN.md` is frozen and
> NOT touched. Reviewed by Codex (round 1 REVISE, 7 findings, all accepted — see
> DOWNLOAD-GUARD-REVIEW-LOG.md). v2 incorporates them.

## Problem (observed)

`_download` skips on `exists() and st_size > 0` and only unlinks zero-byte files on error. A
**truncated** file (short byte count, valid header over a corrupt tile) passes both and is retained
forever on resume. Hit this session: two composites 15–34% short passed the guard, were counted
"228/228 complete", and surfaced only on a full read (`TIFFReadEncodedTile() failed` at X=7, Y=14).

## Constraints (from the code)

- `cube.download(dest, format="GTiff")` is synchronous, returns no content-length → **no
  authoritative expected size**. Size can only ever be a diagnostic warning, never a reject.
- The failure mode is a corrupt raster → the gate is "does it fully decode", per band.

## Design (v2)

### Validation predicate `_decodes(path, expected_band_count) -> bool` (Codex #4, #5, r2#1, r2#3)
- Open with rasterio; assert **nonzero width/height** and **`src.count == expected_band_count`**; read
  **every band in bounded block-windows** (not one giant `src.read()` — bounded memory).
- **`expected_band_count` is passed in explicitly** (r2#3): `reflectance` and `dispersion` are 6-band,
  `clearobs` and `solar_zenith` are 1-band. `download_manifest` knows the cube name, so it passes the
  count; a wrong band count is itself a corruption signal.
- **Exception handling — FAIL SAFE (r2#1, supersedes v1's class-based taxonomy).** `RasterioIOError`
  and GDAL `CPLE_*` wrap permission/open/file-I/O/OOM causes too, so class alone cannot separate
  corruption from environment. Rule: on a decode exception, **re-raise** anything whose cause chain or
  errno indicates environmental failure (`MemoryError`, `PermissionError`/`EACCES`, `ENOSPC`,
  `EMFILE`, open/seek failures); classify as *corrupt* (return False) **only** for decode/tile-level
  errors (e.g. `TIFFReadEncodedTile`, `IReadBlock`, "not recognized as a supported file format").
  **Deterministic precedence (r3#2):** inspect the complete cause/errno chain FIRST — if any
  environmental indicator is present, propagate (environment wins, even if a decode signature also
  matches); only if none is present AND an enumerated decode signature matches, classify corrupt;
  **every unmatched case propagates** (fail-safe) with the original exception preserved.
  **When ambiguous, do NOT classify as corrupt** — never delete on doubt; a truly corrupt file is
  caught again on the next validated read, whereas a wrongly-deleted good file is gone.
- Guarantee scoped honestly as **"base-pixel decodability + band-count/schema"**, not "authoritative"
  (#5). Overviews/masks unvalidated because no downstream stage reads them; stated explicitly.

### Atomic write + validate + publish (Codex #2, r2#2, r2#4)
In each attempt: download to a **unique same-directory temp** (`f"{dest.name}.{os.getpid()}.{uuid4().hex}.part"`,
not a fixed `.part` — r2#2 concurrency/stale collision); `_decodes(part, expected_band_count)`; on
success `os.replace(part, dest)` (atomic) then write the marker; on decode-failure delete **only this
process's own temp by exact name** (never a glob) and retry.
**Stale-temp cleanup (r3#1):** an orphan sweep, separate from the write path, removes a temp (data or
marker) only when its embedded PID is **no longer alive** AND the file exceeds a conservative age — so
a live foreign download's temp is never deleted.
**Environmental exception (r2#4, r3#3):** propagate **without deleting the final `dest`**, but always
best-effort-delete this process's own uncommitted temp first. A crash leaves only an orphan temp
(swept later), never a plausible-looking final.

### Cheap, trustworthy resume via a validation marker (Codex #1, r2#5)
- After a file validates, write marker `dest + ".ok"` **atomically** (temp + `os.replace`, r2#5)
  containing `{validator_version, expected_band_count, size, mtime_ns}`.
- **Skip path:** skip iff `dest` exists AND a marker exists AND it is well-formed AND its
  `validator_version` is current AND `(size, mtime_ns, expected_band_count)` match. Cheap — no decode.
- **Fail-closed (r2#5):** a missing, malformed, unknown-version, or mismatched marker is treated
  strictly as a **cache miss** → revalidate by full decode; it never aborts the run and never counts
  as validated.
- **Legacy / cache-miss:** `dest` exists but no valid marker → **fully decode once**; pass → write
  marker; fail → unlink `dest`+stale marker and re-fetch. Self-heals existing corrupt files, pays the
  full decode exactly once per file. Never a sampled/overview read (the observed corruption was in a
  non-first tile).

### Invalid-existing-file transition (Codex #3)
On confirmed decode failure of an existing `dest`, `unlink(dest)` (and its stale marker) **before**
entering the retry loop, so a known-bad file can never survive to fool an existence counter.

### Retry semantics (Codex #6)
Dedicated `class _CorruptDownload(Exception)`. Loop: download→validate; on `_CorruptDownload` or a
retryable download error, clean up `.part`, backoff, retry up to `retries`; on the final failed
attempt, ensure no `.part`/bad `dest` remains and `raise` preserving the underlying cause. Environmental
exceptions (#4) propagate immediately without deletion or retry.

### Size signal stays diagnostic only (Codex closing note)
Optional `log`-level warning if a freshly published file is < 50% of the median size of the same cube
name across the site's already-validated years. Never a reject — cloudy years are legitimately small.

## Tests (Codex #7, r2#6) — `risk/tests/test_download_guard.py`, tiny local GeoTIFFs, no network
1. **Late-tile truncation** — write a valid **tiled multi-tile** GeoTIFF, assert an **early tile reads
   OK first**, then truncate the byte stream mid-stream so a **later** tile fails → `_decodes` False.
   (r2#6: proves we test tile corruption, not merely an unreadable header.)
2. **Valid all-nodata raster** → True (nodata does not fail `read`).
3. **Legitimately small raster** → True (size never gates).
4. **Wrong band count** → False (e.g. a 5-band file when 6 expected).
5. **Wrapped environmental error** (r2#6) — `_decodes` encountering a `PermissionError`/`MemoryError`
   wrapped in `RasterioIOError` **propagates** and does NOT delete the existing file.
6. **Nonzero partial after a simulated download exception** → no temp and no bad `dest` remain.
7. **Retry then success** — attempt 1 corrupt, attempt 2 good → good file published + marker written.
8. **Final-attempt cleanup** — all attempts corrupt → raises; neither temp nor `dest` remains.
9. **Marker-backed resume** — validated file with matching marker is skipped without decoding (assert
   `_decodes` not called); markerless existing file decoded once then marked.
10. **Malformed / stale-version marker** (r2#5) — treated as cache miss (revalidates), never aborts.
11. **Temp-name collision** (r2#2) — a leftover stale temp for the dest does not corrupt a fresh
    attempt (unique names + stale cleanup).
12. **Live foreign temp survives cleanup** (r3#4) — a temp whose embedded PID is still alive is NOT
    removed by the orphan sweep.
13. **Unclassified GDAL/Rasterio error propagates** (r3#4) — a `RasterioIOError` with no recognized
    decode signature and no environmental indicator propagates (fail-safe) and does NOT delete the
    existing final.

## Out of scope
No change to what is downloaded, retry count semantics beyond the above, provenance, composite
definitions, `PLAN.md`, or any study parameter. No re-download of existing **good** data (markers make
the first post-upgrade resume validate-once, then cheap thereafter).

## Residual risks
- First resume after the upgrade fully decodes every existing file once (~one read of the corpus).
  Accepted: it is paid once and is the price of a trustworthy resume; thereafter markers make it cheap.
- A wrong-but-decodable GeoTIFF (correct schema, plausible values, subtly wrong data) is NOT caught by
  decodability — only a backend checksum could, and none is exposed. Documented, not solved.
