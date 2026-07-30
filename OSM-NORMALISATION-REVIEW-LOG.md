# Plan A — OSM Normalisation — Review Log

**Task.** Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned
road-network cache consumed by Plan B (vintage audit) and Plan C (feature extraction).

**Plan file.** `OSM-NORMALISATION-PLAN.md`
**Position.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md` (`reviewed-unapproved`),
absorbing its round-3 findings #5 and #7.

## Resolved caps

| Var | Value |
|---|---|
| `MAX_ROUNDS` | 5 |
| `MAX_ATTEMPTS` | 8 |
| `PLAN_FILE` | `OSM-NORMALISATION-PLAN.md` |
| `LOG_FILE` | `OSM-NORMALISATION-REVIEW-LOG.md` |
| reviewer | resolved at Act 2 |

## Act 1 — Grill (Claude ↔ Josh)

Measured before any question was asked:

- **`osgeo` is not installed and `ogr2ogr`/`ogrinfo` are not on `PATH`.** The superseded plan's
  dataset-level `GetNextFeature()`/`ogr2ogr` interleaved design is therefore **not implementable here**.
  Available: pyogrio 0.13.0 bundling GDAL 3.12.4, with `set_gdal_config_options`.
- **The bundled `osmconf.ini` sets `osm_version=no`, `osm_timestamp=no`, `osm_changeset=no` for every
  layer** — confirming Codex's round-3 warning.
- **A repo-local `osmconf.ini` via `OSM_CONFIG_FILE` works through pyogrio**: `osm_version`,
  `osm_timestamp` and `osm_changeset` columns all appear.
- **`osm_changeset` is stripped at source.** Across **77,764 features in two extracts**: 0 nonzero, 0 null.
  Geofabrik removes changeset and user identifiers from public extracts. No configuration restores it, so
  the superseded plan's changeset-based lineage is impossible.
- **`osm_version` (1–75) and `osm_timestamp` are fully populated**, giving substitutes.
- **`max(osm_timestamp)` in the `200101` extract is 2019-12-31 19:55**, strictly before the snapshot date —
  a free provenance check that the dated extract is the state it claims.

Decisions locked with Josh:

| # | Decision |
|---|---|
| 1 | Cross-origin lineage on **`osm_id` + version + timestamp + geometry overlap**, since changeset is unavailable. Unresolved cases counted and reported. |
| 2 | Cache holds **every highway-tagged way**, not just the tiers, as GeoParquet per `(origin, region)` — Plan B's cross-tab decides the tiers, so filtering first would assume the answer. |
| 3 | **Plan A acquires and pins the `.poly` extraction polygons** into a separate auxiliary write-once inventory, and uses them to assert each site's full halo lies inside its regions' union. |
| 4 | **No overlap threshold frozen in Plan A.** It reports the distributions; **Plan B** freezes the cutoff against observed data rather than a number invented in the infrastructure layer. |

Decided by Claude and recorded for the reviewer to attack: only the `lines` layer is read (one traversal,
which makes the interleaved-reading concern moot); dedup keys on `(origin, osm_type, osm_id)`; **version
conflicts halt the run** rather than being resolved by highest-version-wins, because a version difference
between same-date extracts is a provenance failure; same-version fragments are geometrically unioned.

---

## Attempt 1 — codex — NOT A ROUND (cut off mid-turn)

47 exploration items completed, no `turn.completed`, no error events. stderr also shows the read-only
sandbox correctly REJECTING a `powershell.exe -Command` invocation ("blocked by policy") — the
enforcement mechanism firing in anger, not a failure. Josh authorised one unchanged retry.

## Round 1 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
- reviewed body_sha256: 37c951dfa7a2000227012b15bfe682bf9589d803e9ad50bbefd49660b65d4878
- verdict: REVISE (5 critical, 8 high, 3 medium)

### Critique (verbatim)

The environment claims are partly confirmed: `osgeo`, `ogr2ogr`, and `ogrinfo` are unavailable; the custom configuration exposes version/timestamp/changeset; and 504,944 inspected highway lines had zero, non-null changesets. The timestamp and layer-completeness claims are false on the acquired data.

## Findings

1. **Critical: `lines` silently omits highway-tagged ways.** In `haiti-and-domrep-200101`, 156 standalone ways with tags including `service`, `footway`, and `pedestrian` were routed to `multipolygons`; GDAL explicitly separates non-area ways from area ways, so [the claim that all ways are lines](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:36>) is invalid. [GDAL OSM documentation](https://gdal.org/en/stable/drivers/vector/osm.html)

   **Fix:** Replace layer-based GDAL extraction with a pinned pyosmium way callback that streams every raw way once, or explicitly consume every way-bearing GDAL layer and accept multiple traversals.

2. **Critical: one-pass bounded-memory parsing is not executable as specified.** Standard pyogrio reads materialize records in bulk; its streaming path is `open_arrow`, but neither `pyarrow` nor another Arrow consumer is installed or included in [the proposed dependency list](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:129>). [Pyogrio documentation](https://github.com/geopandas/pyogrio/blob/main/docs/source/about.md)

   **Fix:** Freeze the exact streaming API and pin its consumer, or use pyosmium’s documented streaming `way` handler, which also removes GDAL layer-routing ambiguity. [Pyosmium documentation](https://docs.osmcode.org/pyosmium/latest/reference/Handler-Processing/)

3. **Critical: the timestamp provenance assertion rejects valid inputs.** Full reads of `haiti-and-domrep-200101` and `norte-200101` produced maxima of `2020-01-01 19:19:02` and `2020-01-01 19:22:51`, contradicting [the required `< 2020-01-01` predicate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:58>); moreover, maximum feature edit time is only a lower bound on dataset recency and cannot certify a snapshot.

   **Fix:** Parse and record the PBF header’s replication/content timestamp, require it and every feature timestamp to be no later than the issue date, and stop claiming that feature maxima authenticate the named archive date.

4. **Critical: the published cache cannot be both per-region and deduplicated across regions.** The plan promises [36 `(origin, region)` files](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:69>) while deduplication groups records across regions; either the merged way remains in multiple files or one region becomes an arbitrary owner, and the singular `source region` loses provenance.

   **Fix:** Treat the 36 files as parse checkpoints only, then publish three origin-level datasets partitioned by stable ID bucket with a sorted `source_regions[]` field.

5. **Critical: lineage is undefined before Plan B sees it.** “No acceptable candidate” already requires an acceptance rule, yet [no threshold exists](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:95>); candidate search radius, CRS, buffering tolerance, pair cardinality, and split/merge aggregation are also unspecified, while exact intersections of slightly shifted linework will often have zero length.

   **Fix:** Freeze a deliberately high-recall metric candidate-generation contract in Plan A and emit the complete many-to-many candidate graph with pairwise and aggregate coverage metrics; let Plan B choose only the classification cutoff.

6. **High: version-conflict halting is an unresolved entry condition, not a complete policy.** It is not a guaranteed stall—871 overlapping Argentina/Bolivia IDs for 2020 had zero conflicts—but same filename dates do not prove identical regional cutoffs, and [the plan admits a legitimate conflict would block indefinitely](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:156>).

   **Fix:** Preflight every actual overlap before implementation; if any conflict exists, acquire one common-parent extract for that overlap component or revise the source contract before building the cache.

7. **High: generic geometric union is neither exact nor well-defined for an OSM way.** The first 20 inspected Argentina/Bolivia duplicates were identical full ways, not clipped fragments as [the plan assumes](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:76>); union can node intersections, lose vertex order, or return disconnected `MultiLineString`s, and no rule covers identical, subset, overlapping, or three-region cases.

   **Fix:** Retain raw node-reference order, deduplicate identical copies directly, merge only proven endpoint-contiguous fragments, and fail/report every other geometry relationship instead of applying unconditional union.

8. **High: same-version attribute conflicts are missing.** The absorbed round-3 finding required tag conflict handling, but [section 4 checks only version](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:81>); timestamp, highway, access, surface, and lifecycle disagreements could otherwise be silently combined with one geometry.

   **Fix:** Require exact equality of timestamp and the canonical full tag map within every same-ID/version group before geometry deduplication.

9. **High: the tag schema is not lossless enough for an unwritten consumer.** Plan B supposedly defines the cross-tab later, yet Plan A selects a few attributes and promises [that neither successor will reparse](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:22>); “any lifecycle prefix” is not a concrete schema, and lifecycle-only ways may lack a plain `highway` tag.

   **Fix:** Preserve the complete canonical tag map and explicit element type/node references for every selected way, using convenience columns only as redundant projections.

10. **High: newly fetched `.poly` files do not prove historical PBF coverage.** Geofabrik documents `.poly` as the exact boundary used for the current extract, but the inventory pins 2020–2022 PBFs and contains no historical polygon version; fetching the files now cannot establish which polygons produced those archives. [Geofabrik technical documentation](https://download.geofabrik.de/technical.html)

   **Fix:** Obtain and pin polygon artifacts demonstrably contemporaneous with each dated PBF, or mark historical source availability unknown rather than certifying it from current polygons.

11. **High: the halo assertion has no input contract.** It can be evaluated before road features exist, but only after the maximum support is frozen; Plan A disclaims feature decisions and never defines “full halo,” while the existing resolver defaults to the unrelated 51-pixel contagion halo in [static_archive.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/static_archive.py:85>).

   **Fix:** Either freeze the inherited geodesic road halo here explicitly, or have Plan A emit each site’s polygon-coverage margin and let Plan C compare it with its eventual support.

12. **High: per-file checkpoints do not guarantee progress under interruption.** A killed parse of the 1.4 GB Indonesia file commits nothing, and [chunked memory handling plus a region-level checkpoint](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:123>) provides no resumable cursor or durable sub-file progress.

   **Fix:** Benchmark the largest file against the hard execution window and, if it cannot finish, publish independently validated batch/shard parts through a parser with a real resumable position.

13. **High: the atomicity protocol covers a Parquet filename, not the stage.** A kill can occur after output rename but before its checkpoint or manifest, a persistent lockfile can become stale, and the plan does not state that cached outputs are rehashed before reuse.

   **Fix:** Use a cache-key-scoped OS advisory lock, fsync and hash outputs, atomically publish a signed/hashed completion manifest last, and treat that manifest—not file existence—as the sole commit marker.

14. **Medium: `code tree SHA` is the wrong cache identity.** A Git commit SHA misses dirty parser edits but invalidates every checkpoint after unrelated documentation commits, undermining both correctness and convergence.

   **Fix:** Hash the exact parser source, configuration, dependency lock, and dirty working-tree content that can affect output.

15. **Medium: centreline and overlap metrics lack units and semantics.** Projection is declared out of scope even though Plan A computes lengths and intersections, while “zero duplicated centreline length” could incorrectly reject legitimate coincident roads with different OSM IDs.

   **Fix:** Freeze geodesic metre lengths and a deterministic metric matching CRS, assert unique dedup keys rather than zero global coincidence, and report distinct-ID overlap separately.

16. **Medium: the proof is dominated by synthetic fixtures and would miss the failures above.** The proposed tests do not assert real layer routing, real archive timestamp behavior, all-overlap conflict counts, historical polygon identity, or completion time for the largest input.

   **Fix:** Add a read-only preflight over all 36 real PBFs that records layer/type counts, metadata ranges, overlap conflicts, polygon provenance, and largest-file runtime before implementation is approved.

VERDICT: REVISE
### Claude's response (round 1)

**The reviewer independently re-measured and falsified two of my four "measured" claims.** Both
verified here before acceptance:

| Claim | How I measured it | Truth |
|---|---|---|
| all highway ways are in `lines` | bbox read of `lines` only | **169 highway-tagged features in `multipolygons`** in haiti-and-domrep-200101; a lines-only read silently drops them |
| `max(osm_timestamp) < snapshot_date` | **bbox subset** -> 2019-12-31 19:55 | **full read** -> 2020-01-01 19:19; the assertion would reject every valid archive |

The same methodological error twice: measuring a **subset** and stating it as a property of the whole
file. The second was worse than a wrong fact — I turned it into a provenance assertion and described it
as a free integrity check, when it would have failed on every run.

Confirmed correct: `osgeo`/`ogr2ogr` unavailable; the custom `osmconf.ini` exposes version/timestamp/
changeset through pyogrio; and `osm_changeset` is zero with no nulls — across **504,944** lines, a
far larger sample than my 77,664.

**All 16 findings accepted. Revision deferred pending the preflight in finding #16**, which is the
right sequencing: two of my claims died to more thorough measurement, so v2 should be written against
real numbers from all 36 extracts rather than another round of assertions.
