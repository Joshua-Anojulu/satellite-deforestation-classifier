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

### Preflight results (Codex finding #16) — read-only, 22 of 36 extracts

Run before revising, because two of my four measured claims had just been falsified by more thorough
measurement. Read-only; nothing written to the archive. Stopped at 22/36 once every finding had reached
100 % consistency — the remaining files were unlikely to change a conclusion, and the largest are
individually infeasible (below).

**1. A `lines`-only read loses data in EVERY file.**

| | |
|---|---|
| files with highway features outside `lines` | **22 / 22 (100 %)** |
| highway features in `lines` | 10,605,634 |
| highway features in `multipolygons` | **11,340 (0.107 %)** |

Small but systematic, across every region and origin. My "roads are ways, ways are lines" reasoning was
tidy and wrong.

**2. The timestamp assertion would reject 21 of 22 archives.** Nearly every extract contains edits made
*during* its nominal snapshot day (`norte-200101` → `2020-01-01 19:22`, `haiti-210101` →
`2021-01-01 13:26`, `haiti-220101` → `2022-01-01 17:51`). Only `centro-oeste-220101` predates its date.
My original 2019-12-31 figure came from a **bbox subset**, not the file.

**3. Whole-file parsing of the largest extracts is infeasible here.** Scan-only cost (bbox read: scans the
whole file, materialises almost nothing) is linear at **0.22 s/MB across a 13× size range**; full
materialisation costs **~8.5×** that.

| extract | size | scan-only | full parse |
|---|---|---|---|
| paraguay-200101 | 79 MB | 24.0 s | 155 s (1.96 s/MB) |
| congo-democratic-republic-200101 | 179 MB | 38.6 s | 335 s (1.87 s/MB) |
| indonesia-200101 | 1016 MB | **219.4 s** | **~32 min (projected)** |
| indonesia-220101 | 1433 MB | — | **~45 min (projected)** |

Observed execution window: **~6–11 minutes** (pass 2 completed one 335 s file and was killed during the
second). So a whole-file parse of any Indonesia extract is 3–7× the available window — finding #12
confirmed by measurement rather than extrapolation.

**Consequence, and it inverts the superseded plan's reasoning.** That plan chose one-pass-per-file over
per-site reads because per-site looked ~9× costlier — a conclusion drawn from a 20 s bbox read I had
mistaken for the dominant cost. Measured properly, **the scan is cheap and linear; materialisation is the
expense.** A bbox read of the 1 GB Indonesia file takes 3.7 minutes and fits the window comfortably.

## Round 2 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed)
- reviewed body_sha256: 03ccff3ca1e9673725e2fef57aed31923f67d4c46273216f5ba84cfd6d610c58
- verdict: REVISE (4 critical, 11 high, 1 medium)

### Critique (verbatim)

Material problems remain. The round-1 provenance, layout, polygon, and basic atomicity corrections are substantially better, but the parser/runtime combination is still not executable within the measured window.

1. **Critical: one per-site shard still exceeds the Indonesia execution window.** At 1,433 MB and 0.22 s/MB, each layer scan costs about 315 seconds; the three-layer unit in [§§1–2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:53>) therefore costs roughly 15.8 minutes before materialisation or publication, already beyond the observed 6–11 minutes.

   **Fix:** Use one direct OSM way-stream pass that dispatches records to every site mask, and make a measured `indonesia-220101` completion below a conservative hard window an entry gate rather than final proof.

2. **Critical: a bbox cannot represent a disjoint site-window union.** The seven Indonesian site boxes have a combined area of about 0.385 deg², but their enclosing bbox is 34.32 deg²—roughly 89× larger—so [the union-bbox fast path](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:66>) may materialize a substantial cross-country corridor; “if it overruns” is not a usable trigger because the process is killed before recording the decision.

   **Fix:** Freeze the shard plan before parsing from measured estimates and use the exact union of disjoint window masks, never their rectangular envelope.

3. **Critical: pyogrio cannot supply the node-reference proof required by deduplication.** Its actual schemas expose reconstructed geometry plus `osm_id`/`osm_way_id`, not raw way-node sequences; `other_relations` contains relation `GeometryCollection`s rather than ways, so [§4.4](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:97>) is impossible through `open_arrow` regardless of whether `pyarrow` is pinned.

   **Fix:** Pin a direct PBF parser such as pyosmium, process only raw ways in one stream with node locations/references, and handle relations under a separate explicit contract if they are wanted.

4. **Critical: “site window” has no completeness boundary.** Plan A promises that Plan C will not reparse, but [§9 deliberately defines no support radius](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:149>); unbuffered site reads omit roads needed near feature edges and omit lineage candidates up to 250 m outside the window.

   **Fix:** Freeze a conservative extraction guard covering at least candidate radius plus tolerance and the maximum downstream road support, or reverse Plan A/Plan C sequencing so Plan C supplies that contract first.

5. **High: the supposedly lossless cache still filters out lifecycle-only roads.** The non-null `highway` predicate in [§1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:55>) excludes `disused:highway`, `proposed:highway`, and similar ways before their full tag maps can be preserved; the plan itself acknowledges this unresolved failure at line 198.

   **Fix:** Freeze the selection predicate as `highway` or any explicitly enumerated lifecycle-highway key, while retaining the full canonical tag map for every match.

6. **High: the geometry relationship rules reject safe cases and accept an underspecified one.** A subset can safely yield the maximal copy, compatible partial overlaps can reconstruct one unique node sequence, and three fragments are not unsafe merely because there are three; conversely, endpoint contact alone does not prove an unambiguous ordered way.

   **Fix:** Reconcile each group as ordered node-ID sequences, accept only a unique consistent global sequence—including identical, subset, overlap, and N-fragment cases—and fail only on ambiguity, branching, coordinate conflict, or gaps.

7. **High: the fail-closed geometry branches are not included in the real overlap preflight.** Only version conflicts are preflighted, so an otherwise legitimate subset or three-region group can still halt after expensive parsing despite being explicitly expected by the state machine.

   **Fix:** Preflight every duplicate group’s version, tags, timestamp, node-sequence relationship, and geometry classification before starting cache construction.

8. **High: area highway ways do not fit the line-based lineage schema.** `multipolygons` supplies polygonal highway areas, but [§6](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:115>) defines line lengths, line buffers, and endpoint-oriented relationships without stating whether a plaza’s perimeter, area, or raw ring is the audited object.

   **Fix:** Preserve polygon ways as a separate geometry class and freeze dimension-appropriate lineage metrics, leaving any conversion to road centreline semantics to Plan B or Plan C.

9. **High: the candidate-generation parameters still constrain Plan B’s scientific decision.** A 250 m radius censors every possible edge beyond it, while a 10 m buffer fixes which realignments receive overlap; Plan B can lower a cutoff but cannot recover omitted pairs or recompute the claimed distributions from the graph, exactly as [the risk section admits](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:200>).

   **Fix:** Demonstrate candidate saturation at wider radii and emit raw distances plus overlap metrics at multiple frozen tolerances, or let Plan B own both tolerance and classification cutoff.

10. **High: the lineage metric formulas and CRS are not deterministic at pair level.** “UTM zone of the way’s centroid” does not say which side chooses the CRS and can make A→B differ from B→A; buffered IoU is an area ratio, while “intersection over each side’s length in geodesic metres” is dimensionally ambiguous, and aggregate coverage is undefined.

   **Fix:** Freeze one symmetric CRS per site or candidate component and specify exact formulas: buffered-area IoU, length-of-A-inside-buffer-B divided by length A, its reciprocal, union-based aggregate coverage, and all origin pairs emitted.

11. **High: `unresolved` still imports classification language into Plan A.** Before Plan B selects a cutoff, a candidate with negligible overlap is neither resolved nor unresolved; only graph degree is objectively known.

   **Fix:** Emit `no_candidate` for degree-zero nodes and candidate-degree/metric distributions for all others, reserving `resolved` and `unresolved` for Plan B.

12. **High: cache identity omits semantic inputs.** [§10.1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:158>) hashes code and dependencies but does not name the PBF hash, site-manifest hash, exact window/mask geometry, shard plan, or polygon inputs; output rehashing cannot detect a valid cached artifact built for different site windows.

   **Fix:** Put every input digest, site/mask specification, shard-plan version, normalization parameters, and stage-specific auxiliary hash into the cache key and completion manifest.

13. **High: the dirty-tree hash reintroduces unrelated invalidation.** Hashing all “dirty working-tree content” means an uncommitted documentation edit invalidates caches even though the proof only checks an unrelated committed documentation change.

   **Fix:** Hash dirty content only for the exact parser, configuration, schema, and dependency files that can affect the stage.

14. **High: the manifest is a valid final commit idea but not yet a shard commit protocol.** One global manifest published last safely commits the final stage, but [per-shard checkpoints](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:165>) require their own commit markers or every shard completed before a kill remains an orphan; this also conflicts with the promise of exactly 36 checkpoint Parquets.

   **Fix:** Publish a hashed manifest last for every shard, a region manifest referencing all shard parts, and a final stage manifest referencing all region/origin outputs; define the 36 checkpoints as logical manifests rather than single files.

15. **High: cache-key locking does not necessarily protect logical publication.** Two different valid cache keys can run concurrently and race if both publish to the same three origin-level destinations; [§10.4](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:164>) only serializes equal keys.

   **Fix:** Keep every artifact under its content-addressed key and update any shared consumer pointer under a separate logical-dataset publication lock.

16. **Medium: the header check proves no lookahead but not the named January snapshot.** A June or November PBF would satisfy `header_timestamp <= 31 Dec T`, and the fallback phrase “replication timestamp / content timestamp” has no precedence or missing-field rule.

   **Fix:** Require an authoritative header field, enforce `feature_max <= header_timestamp <= issue_date`, and validate the header against a nominal archive-date window derived from all 36 real headers.

The “manifest published last” correction is directionally sound, but the hierarchy and cache identity must be frozen before it becomes a real resumable commit contract. No files were modified.

VERDICT: REVISE
### Claude's response (round 2)

All sixteen findings accepted. The parser was replaced wholesale rather than patched: pyogrio cannot
supply node references (#3), so v3 moved to a raw pyosmium way stream, which simultaneously dissolves #2,
#5 and #8. The two sections below are the measurement and the reframing that produced v3.

### Benchmark: pyosmium single-pass way stream (tests round-2 finding #1) — NEGATIVE

pyosmium 4.3.1 installed (`cp314` wheel). `osm.Way.nodes` **does** expose raw node references, so round-2
finding #3 is correct that pyogrio cannot supply them and pyosmium can. But the throughput answer is
negative.

Streaming `indonesia-220101.osm.pbf` (1433 MB), ways only, tags + node references, **no geometry**:

| ways streamed | elapsed |
|---|---|
| 4,000,000 | 357 s |
| 8,000,000 | 821 s |
| 12,000,000 | 1,045 s |
| 16,000,000 | **1,264 s (21 min)** — not finished |
| 18,000,000 | *discarded — see below* |

**The 18M reading of 41,388 s is discarded as invalid.** Every preceding 2M-way interval cost 100–190 s;
11.5 hours for the same increment is not compute. The machine evidently suspended and wall-clock continued
through it. Reporting it as parse time would be wrong.

**Conclusion: >21 minutes and incomplete, against a 6–11 minute window — the single-pass design fails.**
This is also a *floor*: no geometry was reconstructed, which additionally requires an osmium node-location
index at materially greater cost.

**Three parsing designs have now been invalidated by measurement**, each after being specified as sound:

| design | why it failed | how it was found |
|---|---|---|
| `GetNextFeature()` / `ogr2ogr` | `osgeo` and the CLIs are not installed | probe |
| pyogrio bbox-to-site-union | disjoint union envelope 89× oversized; **no node references** | reviewer arithmetic + API check |
| pyosmium single way-stream | **>21 min for one 1.4 GB file**, incomplete, before geometry | this benchmark |

The common thread is that each was specified from what a tool *ought* to do rather than from a measured
run, and each survived until something measured it. Plan A needs a structurally different shape — persisted
per-region intermediates accumulated across multiple bounded runs — not another revision of the same one.

### Reframing after the benchmark — the window was never the pipeline's constraint

The negative benchmark was interpreted wrongly at first. Re-measured, one pyosmium pass over the **entire
corpus** costs **2.7 hours** (12,658 ways/s measured; ~121 M ways projected across 36 files, 9.42 GB),
while the per-site pyogrio alternative costs **7.2 hours for the three Indonesia files alone**.

pyosmium is ~3x cheaper overall. It was rejected for two rounds because 21 min/file exceeds the **6-11
minute background window** — but that window constrains **Claude's background execution**, not the machine
and not the pipeline. Josh ran the 10.92 GB GFC acquisition to completion in his own elevated terminal
with no such ceiling. Three successive designs were therefore shaped around an artefact of the assistant's
tooling, mistaken for a property of the problem.

Adopting a raw way stream also dissolves several findings rather than answering them, because pyosmium
reads the **OSM data model** and not GDAL's rendered layers:

| finding | how it dissolves |
|---|---|
| r1 #1 `lines` omits highway ways (0.107 %) | no GDAL layers exist in a raw way stream |
| r2 #2 disjoint union envelope 202x oversized | dispatch to exact site masks during the single pass |
| r2 #3 pyogrio cannot supply node references | `osm.Way.nodes` exposes them directly |
| r2 #5 lifecycle-only ways filtered out | raw tags are visible before any predicate |
| r2 #8 area highway ways vs line schema | raw ways carry their own closed/open geometry |

Checkpoints remain, but for **crash resilience** rather than to fit a seven-minute ceiling.

## Round 3 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed)
- reviewed body_sha256: 12d1e8f5994724870dc23c64b6d0f5fc4ff60df680fd8f8afcceaba06a77dae7
- verdict: REVISE (2 critical, 5 high, 3 medium)

Trend across rounds: 16 -> 16 -> 10 findings; criticals 5 -> 4 -> 2. The first round where the
reviewer accepted the plan's framing and attacked only its mechanics.

### Critique (verbatim)

Material problems remain. The human-launched-job reframing is legitimate, but the specified parser cannot currently produce geometry, and the reconciliation, lineage, and publication contracts remain incomplete.

1. **Critical: the frozen pyosmium call cannot enable geometry.** [`FileProcessor(path, osmium.osm.WAY)`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:66>) excludes nodes, so `.with_locations()` raises `RuntimeError`; pyosmium explicitly requires nodes to reach the location cache. [Pyosmium documentation](https://docs.osmcode.org/pyosmium/latest/user_manual/04-Working-with-Filters/)

   **Fix:** Use `FileProcessor(path, NODE | WAY).with_locations(index).with_filter(EntityFilter(WAY))`, then benchmark that exact pipeline.

2. **Critical: node-sequence reconstruction is solving a nonexistent fragment problem and can manufacture a way absent from every source.** Geofabrik states that cross-border ways remain complete, so same-origin, same-ID/version records with unequal ordered node lists indicate source inconsistency; “unique consistent global sequence” is also undefined for repeated nodes, closed-cycle rotations, reversals, and competing supersequences. [Geofabrik technical details](https://download.geofabrik.de/technical.html)

   **Fix:** Require exact ordered node-reference equality for duplicate same-version ways and fail preflight on any mismatch instead of reconstructing sequences.

3. **High: the node-index entry gate has no pass condition.** [`indonesia-220101` completion](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:92>) alone is not a gate: it specifies no wall-clock, peak-RSS, temporary-disk, or projected-corpus ceiling, while the 2.7-hour estimate excludes the required node decoding, index creation, geometry, masking, and output.

   **Fix:** Freeze resource ceilings and benchmark the complete largest-file pipeline under each candidate index backend, authorizing the corpus only when runtime, RSS, disk, and extrapolated total all pass.

4. **High: interrupted file-backed indexes are outside the durability contract.** `sparse_file_array` requires managed backing storage, while installed pyosmium’s `FileProcessor` internally ignores missing-location errors; the plan neither defines fresh-versus-reused index files nor requires every retained node reference to have a valid coordinate. [Osmium index documentation](https://docs.osmcode.org/osmium/latest/osmium-index-types.html)

   **Fix:** Create a fresh per-attempt index in a capacity-checked temporary directory, explicitly reject every missing/invalid retained node location, and delete it only after the region commit succeeds.

5. **High: the manifest hierarchy is not yet a crash-consistent commit protocol.** [The stage manifest references regions](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:120>), but does not explicitly bind the three origin datasets, lineage artifacts, schemas, or child-manifest digests; atomic manifest publication, directory durability, validation order, lock order, and atomic pointer replacement are also unspecified.

   **Fix:** Define a hash-linked DAG covering every consumer artifact, publish each manifest via same-directory temporary file → fsync → atomic replace → directory flush, then atomically update the pointer only after full DAG revalidation under a fixed lock order.

6. **High: the 1,000 m lineage graph still constrains Plan B.** [“Saturation curve”](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:135>) has no sampled radii, statistic, denominator, or fail/expand rule, and same-ID ways moved beyond the spatial radius can disappear despite having direct identity evidence.

   **Fix:** Either move candidate generation entirely to Plan B, or include equal-ID edges unconditionally and define a broader superset plus explicit outer-radius saturation criteria that fail closed when unsaturated.

7. **High: the lineage schema remains non-deterministic.** It does not define the candidate distance predicate, “centre,” exact union-based aggregate formula, all origin pairs, site-specific edge key, component construction, or how closed ways participate; moreover, `way_closed` is not a GeoParquet geometry type while the metrics assume line lengths and buffers.

   **Fix:** Freeze a complete edge schema and formulas, storing every raw traversal as an ordered `LineString` plus `is_closed`, with closed-way area semantics explicitly excluded.

8. **Medium: shard manifests do not provide parser resumability.** Pyosmium supplies no durable input cursor here, so a kill during a file still requires rebuilding its node index and rescanning that file; committed output parts reduce rewriting but not lost parsing work.

   **Fix:** Declare the whole input file as the smallest restart boundary and quantify worst-case rework, or introduce a separately committed resumable intermediate with a validated cursor.

9. **Medium: the coverage-margin claim contradicts the historical-polygon caveat.** [Plan A says margins let Plan C verify coverage](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:84>), but current-vintage `.poly` files cannot prove the 2020–2022 extract boundary.

   **Fix:** Separate processing-mask margin from current-polygon margin and keep historical source availability `UNKNOWN` regardless of either value.

10. **Medium: the long-running operating model lacks live observability.** Final per-file counts cannot diagnose a stalled index, disk exhaustion, suspension, or pathological geometry during a multi-hour human-run job.

   **Fix:** Emit a periodic non-authoritative progress journal containing file, node/way counts, rate, RSS, index size, free disk, and last committed manifest.

No files were modified.

VERDICT: REVISE

### Entry gate (round-3 finding #3) — PASSED on wall-clock, INCOMPLETE on resources

Codex's round-3 #1 was confirmed exactly: `FileProcessor(path, WAY).with_locations()` raises
`RuntimeError: Nodes not read from file`. Its prescribed fix works:
`FileProcessor(NODE|WAY).with_locations().with_filter(EntityFilter(WAY))`.

Complete pipeline on the worst-case file, `indonesia-220101` (1433 MB):

| | measured |
|---|---|
| ways streamed | **43,250,208** |
| highway ways | 4,839,062 |
| with valid geometry | **4,839,062 (100 %)** |
| elapsed | **1096 s = 18.3 min** |
| rate | 39,475 ways/s incl. node decoding + location index |
| peak RSS | **NOT MEASURED — `psutil` absent** |

**A prior benchmark of mine was wrong and had driven three rounds of design.** The earlier
"12,658 ways/s, >21 min, single-pass infeasible" figure was inflated by my own predicate, which ran a
generator over every tag of every non-highway way. Measured against a direct key lookup on the same file:

| predicate | rate |
|---|---|
| `any(k.endswith(':highway') ...)` (mine) | 17,849 ways/s |
| direct key lookups | **46,467 ways/s (2.6x)** |

Both matched the same ways (234,593 vs 234,570). So the conclusion that a single pass was infeasible came
from loop overhead, not from pyosmium.

**Two of my projections were also wrong, in opposite directions.** The file holds 43.25 M ways
(**30,182 ways/MB**), not the ~12,840 ways/MB I assumed — low by 2.35x — while my rate estimate was ~3x
too low. The errors partly cancelled, so v3's "2.7 hours" landed near the corrected **2.0 hours** by
coincidence rather than by being right. Corpus: **~284 M ways, ~2.0 hours**, largest file **18.3 min
measured**.

**The gate is therefore only partially satisfied.** Wall-clock and corpus projection pass; **peak RSS and
temporary-disk ceilings remain unverified** because `psutil` is not installed. The run completing without
an OOM kill is weak evidence that the default `flex_mem` index fit in 31.7 GB, and is not recorded as a
ceiling. v4 must either install `psutil` and re-measure, or state the memory ceiling as unverified.

**Pattern worth naming.** Three times this session a measured subset or artefact was stated as a property
of the system: a bbox read for whole-file timestamps, the `lines` layer for all highway ways, and now my
own loop overhead for parser throughput. The reviewer caught the first two; the third surfaced only
because its API correction produced a number 16x off mine.

### Entry gate, second pass — ALL ROWS PASS

The first pass could not supply resource ceilings because `psutil` is absent. Rather than add a dependency
to the analysis environment for a measurement, peak working set is read from `GetProcessMemoryInfo` via
`ctypes`. The probe was validated against a deliberate 600 MB allocation first (0.015 -> 0.644 GB), so it
is known to track allocation rather than return a constant.

The second pass also applies §1.5's **full** per-node validation — every node of every retained way — where
the first pass checked only each way's first node. That is the pipeline the plan specifies, so it is the
binding measurement.

| condition | ceiling | measured | |
|---|---|---|---|
| largest-file wall-clock | <= 45 min | **22.5 min** (1348 s) | PASS |
| projected corpus wall-clock | <= 6 h | **~2.26 h** | PASS |
| peak working set | <= 50 % RAM (17.0 GB) | **6.58 GB (19.3 %)** | PASS |
| geometry availability | 100 % | **4,839,062 / 4,839,062** | PASS |
| ways with missing/invalid node location | 0 | **0** | PASS |
| temporary index disk | n/a | 0 bytes | PASS |

**This deletes a branch of the plan rather than documenting one.** Working set peaked at 6.58 GB during
node reading, then held flat at ~3.7 GB for the entire way pass -- the index is fully built before the
first way is emitted, so the peak is structural, not a trend a bigger file extends. `indonesia-220101` is
the largest extract (1433 MB of 8641 MB total; next largest 1241 MB), giving a 2.6x margin. So `flex_mem`
is frozen as the sole backend and the on-disk `sparse_file_array` branch is removed -- and with it the
whole of Codex's #4: no index file to orphan on a kill, no temp-directory capacity check, no
fresh-versus-reused question.

**A fourth wrong number of mine, found while filling this table.** The corpus was projected over 9.42 GB --
the size of the *entire* static archive, including the non-OSM layers. The OSM subset is **8.64 GB**. So
v3's "2.7 hours" was wrong in all three of its components: ways/MB low by 2.35x, throughput low by ~2.5x,
and the corpus 9 % too large. Partial mutual cancellation is not corroboration.

Cost of the stricter check, stated plainly: 18.3 min -> 22.5 min (+23 %) for validating every node instead
of the first. Worth it -- installed pyosmium ignores missing-location errors internally, so without the
per-node check the plan's geometry-completeness claim would rest on the parser's silence.

### Testing Codex #2's premise instead of trusting it — node-sequence equality, origin 2020

Finding #2 replaced v3's node-sequence reconciliation with exact ordered equality, on the strength of
Geofabrik's documented guarantee that cross-border ways are kept complete. That makes an **external
document** load-bearing for a rule that halts the whole corpus run, so it was measured. Node *references*
need no location index, so this is cheap: `FileProcessor(path, WAY)` with no `.with_locations()`.

All seven land-border region pairs at origin `200101`, 3,524,174 retained ways loaded across 7 regions:

| pair | shared IDs | node-seq mismatches | version mismatches |
|---|---|---|---|
| argentina x bolivia | 871 | 0 | 0 |
| argentina x paraguay | 19,825 | 0 | 0 |
| bolivia x paraguay | 266 | 0 | 0 |
| bolivia x peru | 471 | 0 | 0 |
| norte x nordeste | 8,105 | 0 | 0 |
| norte x centro-oeste | 2,578 | 0 | 0 |
| nordeste x centro-oeste | 253 | 0 | 0 |
| **total** | **32,369** | **0** | **0** |

Every cross-region duplicate is byte-identical in its ordered node references. Two consequences:

1. **The fail-closed rule is safe on this corpus** -- it will not halt on data that actually exists.
2. **v3's reconciliation machinery would never have run once.** It was not merely unnecessary, as #2
   argued; it was pure risk surface, capable only of manufacturing a way present in no source.

This also independently corroborates round-1's observation of 871 conflict-free Argentina/Bolivia IDs,
now at the stricter node-sequence level rather than version level.

Scope limit, stated rather than glossed: origins 2021 and 2022 are unchecked, and only land-border pairs
were compared. The plan's risk section says so.

## Round 4 — codex

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (PINNED, see below) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: fdbc5449f5afcdd7b58bf1fbbee726f0779f321c47ccb5bb24e3928c328f367d
- verdict: REVISE (1 critical, 6 high, 2 medium)

Trend: 16 -> 16 -> 10 -> 9 findings; criticals 5 -> 4 -> 2 -> 1.

**Version gate fired before this round.** The Codex CLI auto-updated to 0.146.0 mid-review, outside the
adapter's `verified_versions: ">=0.130 <0.146"`, which fails closed to UNVERIFIED. 0.146.0 also shipped the
known-broken sandbox layout for this box (helpers in `codex-resources/`, absent from `bin/`). Repairing it
would not have made it *verified*, and the acceptance test's mandatory positive control needs `--yolo`,
which is classifier-blocked for Claude. So round 4 was pinned to the still-installed, still-repaired
0.145.0 release binary — inside the verified range and the exact version rounds 1-3 ran on, preserving CLI,
session and model across all four rounds. Canary re-run in the target repo first: replied BLOCKED, no file
created, `git status` unchanged.

### Critique (verbatim)

Material problems remain. The quantitative parser gate is substantially better, and omitting directory flush is defensible under the plan’s limited durability claim, but several contracts still overclaim their evidence.

1. **Critical: the frozen selection predicate has a measured mismatch.** The review log says the suffix predicate matched 234,593 ways while direct lookup matched 234,570, yet calls them “identical”; until those 23 ways are explained, [§1.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:115>) is known not to preserve the same population.

   **Fix:** Materialize the 23-way set difference, classify its tag keys, expand the frozen direct-key list as necessary, and require equality against a reference predicate over all 36 extracts.

2. **High: identical node references do not imply identical geometry.** A referenced node can move between regional build cutoffs without changing the containing way’s version, timestamp, tags, or node-reference list; [§4](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:201>) could therefore silently choose between differing coordinate sequences.

   **Fix:** Require exact resolved-coordinate-sequence equality as well as node-reference equality, reporting conflicting node IDs, coordinates, regions, and header timestamps.

3. **High: the gate is bound to a validation harness, not demonstrably to the production stage.** The plan attributes 22.5 minutes to full node validation but does not state that the measured path also performed every `LineString` construction, exact-mask intersection, dispatch, serialization, hashing, and publication; no checked-in harness or immutable measurement artifact binds the result to future parser code.

   **Fix:** Rerun the gate through the production parser-to-committed-region path and record its source hash, command, input digest, dependency versions, counters, resource trace, and output digest.

4. **High: compressed file size does not prove that Indonesia is the worst `flex_mem` case.** `flex_mem` switches representations according to node cardinality and ID density; sparse storage scales by node count while dense storage depends on the largest node ID, neither of which is ordered by compressed PBF bytes. [Osmium index documentation](https://docs.osmcode.org/osmium/latest/osmium-index-types.html)

   **Fix:** Keep the single backend, but preflight node cardinality/ID statistics or enforce the memory ceiling independently for every file and remove the claim that largest compressed size proves the binding memory case.

5. **High: the 0.5% saturation rule is a scientific cutoff and does not prove completeness.** A site dominated by many short-distance edges can pass while rare but important renumbered/split roads lie beyond 2 km; [the criterion](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:297>) observes nothing in the 2–5 km guard and directly determines what Plan B may inspect.

   **Fix:** Emit unconditional identity edges plus a queryable spatial index and let Plan B choose spatial candidate generation, or emit the complete guard-bounded superset without an edge-count acceptance threshold.

6. **High: the lineage aggregate output is still not fully specified.** Components span three origins, but `A` and `B` in [§6.5](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:318>) are not keyed to an origin pair, aggregate columns are absent from the frozen edge schema, and `component_id`, buffer parameters, Hausdorff variant, and zero-length policy remain undefined.

   **Fix:** Define a separate aggregate table keyed by site, unordered origin pair, canonical component hash, and tolerance, while freezing geometry-operator parameters and degenerate-geometry handling.

7. **High: the Windows protocol handles returned errors, not abrupt termination.** A kill or power loss during `ReplaceFileW` produces no `winerror` for `classify`; restart may find destination, staging, and backup in any documented intermediate arrangement, while the current helper’s `recover()` merely returns prose and [does not call `FlushFileBuffers`](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/_atomic_publish.py:178>).

   **Fix:** Add an executable startup classifier that validates the three files by digest/identity and deterministically rolls forward or fails closed, and implement a checked `FlushFileBuffers` call before replacement.

8. **Medium: local-NTFS and locking assumptions are not enforced by the reused helper.** Its local/reparse check is not called by `publish_container`, does not inspect reparse-point ancestors or verify the filesystem/drive type, and the plan fixes lock order without naming a crash-releasing Windows lock primitive.

   **Fix:** Make publication itself require a named local-NTFS root, validate its full ancestor chain and volume type, and use handle-held `LockFileEx` locks released automatically on process death.

9. **Medium: the duplicate preflight evidence is overstated.** [The plan concludes the rule will not halt “this corpus”](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:230>) from 2020 land-border pairs while explicitly admitting that 2021, 2022, and other overlaps remain unchecked.

   **Fix:** Describe the measurement as evidence for the tested subset only and make the full three-origin overlap preflight an authorization gate rather than later proof.

The absence of directory flush specifically leaves NTFS namespace changes vulnerable to being lost or reordered across sudden power failure; that limitation is acceptable if the plan promises only atomic visibility and implements the missing restart validation above.

No files were modified.

VERDICT: REVISE
### Claude's response (round 4) — all 9 accepted; the critical was mine

**#1 was a real error, and my first attempt to investigate it was also wrong.** v4's log said two
predicates matched "the same ways (234,593 vs 234,570)" and called them identical. They differ by 23.

First census attempt counted "ways carrying an unfrozen `:highway` key", saw `not:highway`,
`source:highway`, `historic:highway`, and I concluded the suffix predicate was over-matching and my frozen
list was fine. **That accounting was wrong**: most of those ways also carry plain `highway` and are
retained by both predicates, so they prove nothing. Rewritten to isolate the true SET DIFFERENCE — ways the
suffix predicate retains that the frozen predicate does not — the answer points in BOTH directions:

| key | in set difference | disposition | why |
|---|---|---|---|
| `was:highway` | yes | **retain — v4 MISSED IT** | standard lifecycle prefix |
| `area:highway` | yes | **retain — v4 MISSED IT** | established tagging for road areas |
| `not:highway` | yes | exclude | negative assertion: states it is *not* that road |
| `source:highway` | no (co-occurs with `highway`) | exclude | metadata about the tag's provenance |
| `historic:highway` | no | exclude | historic designation, not a carriageway |

Per-file set differences measured so far: norte-200101 = 4 (`not:`), haiti-and-domrep-200101 = 1 (`was:`),
centro-oeste-200101 = 18 (`area:`), haiti-and-domrep-210101 = 1 (`was:`), haiti-and-domrep-220101 = 3
(`area:` 2, `was:` 1).

So Codex was substantially right and my snap reading was half wrong: **two genuine keys were missing**, and
three would have been wrongly swept in by a bare suffix rule. The fix is a frozen per-key disposition
table plus a run-time assertion that fails closed on any unknown `*:highway` namespace.

**The census is slow for the exact reason v3's benchmark was slow** — enumerating `*:highway` keys requires
scanning every tag of every way, the generator cost I diagnosed two rounds ago. Here it is unavoidable.
Coverage is therefore partial (6 of 36 at submission) and the plan says so rather than claiming the corpus.
**The run-time assertion, not the census, is what makes that safe.**

**#2 is a hole I would not have found.** A node can move between regional build cutoffs without touching
the containing way's version, timestamp, tags or node-reference list. So my 32,369-pair result — which
compared node references only — could not have detected it. §4.3 now requires resolved-coordinate equality
too, and #9's point that the result was overclaimed is accepted.

**#7 and #8 verified against the code, not taken on trust.** All three claims hold:
`FlushFileBuffers` appears nowhere in the repo; `assert_local_non_reparse` is called only from
`forecast/tests/test_atomic_publish.py` and never from `publish_container` (which calls
`assert_same_volume` alone) — so the plan's claim that the helper "rejects OneDrive" was **false as a
statement about production behaviour**; and `recover()` returns a state-table string while `classify()`
only maps a *returned* winerror, so abrupt termination leaves nothing to classify.

**#5 is the third consecutive round finding Plan A bounding Plan B's science** — 250 m, then 1000/2000 m
with a saturation curve, then a 0.5 % acceptance test. The cutoff was never the problem; Plan A owning it
was. Plan A now emits identity edges plus a spatial index and generates no spatial candidates at all.

## Round 5 — codex (FINAL — MAX_ROUNDS reached)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: 9082a610776787f6d4129c607120d954acb6681368d1dbcfe359ba4c4a3ca296
- verdict: REVISE (1 critical, 4 high, 1 medium)

Trend across the full loop: **16 -> 16 -> 10 -> 9 -> 6** findings; criticals **5 -> 4 -> 2 -> 1 -> 1**.
The cap was reached while the plan was still converging, not because the argument stalled.

### Critique (verbatim)

Material defects remain.

1. **Critical — “identity edges at any distance” is impossible with 5 km dispatch.** A way moved outside the site window in another origin is discarded before the identity join, so the promised edge cannot exist. The arbitrary-separation test can pass on synthetic inputs while production remains incomplete. [§2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:194>) contradicts [§6.1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:418>).

   **Fix:** Compute per-site identity closure across all origins—retaining every counterpart of any site-relevant `osm_id` regardless of window intersection, with an `outside_window` flag—before publishing identity edges.

2. **High — Plan B is not actually free to choose any radius.** A spatial index over a finite 5 km window is complete only for a defined anchor domain and radius; candidates beyond the boundary are missing, especially for anchors near that boundary. The plan also admits Plan C could exceed the guard, directly contradicting “neither Plan B nor Plan C can need a discarded road.” [§2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:197>) [§6.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:422>) [risk](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:534>)

   **Fix:** Freeze the anchor domain and emit `max_complete_radius_m` per site; require Plans B/C to stay within it or reopen Plan A, and specify a portable index schema—or let Plan B build its own ephemeral index from GeoParquet.

3. **High — the coordinate preflight is ordered before the data needed to run it.** Resolved coordinates are “already retained” only after the node index and parser have produced region records; obtaining them before the corpus run requires another full node-and-way pass, not the claimed cheap preflight. [§4.3](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:290>) [§4.6](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:324>)

   **Fix:** Authorize region-checkpoint parsing first, run coordinate preflight from all committed region checkpoints, then gate deduplication/origin publication—or explicitly budget a separate full-corpus preflight parse.

4. **High — the NTFS startup classifier is still a requirement, not an executable protocol.** “Recognised intermediate arrangement” has no exhaustive existence/digest/file-identity matrix, no explicit expected old/new identities for root manifests and pointers, no backup-cleanup rule, and no requirement to recover while holding the same locks. Concurrent restarts can therefore race, while a surviving backup can interfere with the next replacement. [§5.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:375>) [§5.4](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:394>)

   **Fix:** Freeze the complete three-path state table and idempotent action for every state, including cleanup, and require classification/recovery under the ordered `LockFileEx` locks with deterministic expected digests.

5. **High — 22.5 minutes is still overstated as worst-case restart cost.** The plan correctly calls it a parser floor and says compressed size does not order runtime or memory, then later calls it measured worst-case production rework and calls Indonesia the binding memory case. That unsupported figure is used to reject resumable intermediates. [§3](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:234>) [§10.1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:485>) [risk](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:528>)

   **Fix:** Delete both binding-case claims and base the restart decision on the production-path ceiling or measured maximum committed-region duration, revisiting resumability if that bound is unacceptable.

6. **Medium — `historic:highway` is classified too aggressively.** The assertion cannot protect this case because `historic:highway` is deliberately subtracted from the reference predicate. Its use is documented as inconsistent and can denote a previously valid characteristic, so declaring it categorically “not a present or former carriageway” is itself a scientific decision and can irreversibly hide lineage from Plan B. [predicate table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:157>) [OpenStreetMap lifecycle documentation](https://wiki.openstreetmap.org/wiki/Lifecycle_prefix)

   **Fix:** Retain ambiguous `historic:highway` records with their raw tags and limit exclusion to unambiguous negative or metadata namespaces such as `not:` and `source:`.

VERDICT: REVISE
## Round 6 — codex (FINAL — MAX_ATTEMPTS exhausted)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: a325021d05e30d94f038ecb94f9a5c77c1046ce36dc8f62da420868d14c8a165
- verdict: REVISE (1 critical, 3 high, 2 medium)
- MAX_ROUNDS was raised 5 -> 6 by Josh's explicit decision, to spend the last available attempt.

Full loop: **16 -> 16 -> 10 -> 9 -> 6 -> 6** findings; criticals **5 -> 4 -> 2 -> 1 -> 1 -> 1**.
Attempts: 8 of 8 (one non-round at the start). Both caps now exhausted.

**The count plateaued, and the composition changed.** At least three of round 6's findings are direct
consequences of round 5's fixes rather than pre-existing defects: identity closure (round-5 #1) created
the under-keyed `S` and the anchor-domain gap; retaining `historic:highway` (round-5 #6) created the
proof/table contradiction. The plan is no longer converging on a fixed set of problems - each fix opens
comparable new surface at a finer grain.

### Critique (verbatim)

Material defects remain.

1. **Critical — identity closure is still under-keyed.** `S` is only `set[osm_id]`, but lineage and `outside_window` are site-specific. A way may be inside site A and outside site B; pass 2 also marks every retained counterpart `outside_window=true`, including in-window pass-1 duplicates and tag-changed counterparts that remain geometrically inside. The frozen edge schema does not contain the promised endpoint flags. [§2.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:224>) [§6.1](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:495>) [schema](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:508>)

   **Fix:** Commit a DAG-bound `(site_id, osm_id)` closure table, associate every pass-2 counterpart with those exact sites, store separate `intersects_window`, `selected_by_predicate`, and `closure_only` endpoint flags, and suppress deterministic pass-1 duplicates.

2. **High — `max_complete_radius_m` is not yet a geometric completeness contract.** “Anchor inside the site box” is undefined for a `LineString`: a way merely intersecting the box can extend far outside it, where nearby candidates may lie beyond the mask. The distance metric used to compute the margin is also unspecified relative to Plan B’s projected distance, and closure-only geometries are not explicitly excluded from the spatial index. [§2.3](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:239>) [§6.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:501>)

   **Fix:** Define anchors as geometry clipped to the site box, define `max_complete_radius_m = inf distance(site_box, complement(mask))` in the same or a conservatively bounded metric, and require Plan B’s spatial index to exclude closure-only endpoints.

3. **High — the NTFS table is still neither complete nor fully executable.** It omits the ordinary clean state `D=d_old, S=absent, B=absent`; row 6 accepts an unknown backup despite row 8’s fail-closed rule; `publish S` does not name the operation used when `D` is absent; and `d_old == d_new` makes the digest-only rows ambiguous despite the prose mentioning file identity. Retrying publication twice is not itself idempotent—only a reclassify-then-act recovery entrypoint can be. `ReplaceFileW` normally replaces an existing destination, while error 1177 leaves staging and the old file under separate names. [§5.2](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:429>) [Microsoft `ReplaceFileW` documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)

   **Fix:** Add the clean pre-staging state and equal-digest no-op, express expected file-identity relationships in every row, split row 6 by backup digest, specify its exact atomic rename/placeholder procedure, and test the complete recovery entrypoint twice rather than replaying raw actions.

4. **High — the acceptance proof reverses the predicate decision.** The disposition table now retains `historic:highway`, but the required test still specifies it as excluded; an implementer following the proof would reintroduce the exact irreversible loss round 5 fixed. [table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:167>) [proof](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:648>)

   **Fix:** Change the proof to require `historic:highway` retained and limit excluded fixtures to `not:highway` and `source:highway`.

5. **Medium — runtime evidence is still overstated.** The opening says every runtime is measured on the worst case, while 2.26/4.5 hours are extrapolations, pass 2 has never run with the real `S`, and the production path does not exist. The table nevertheless marks the two-pass projection `PASS`, and the stage ordering production-gates only pass 1. [measurements](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:75>) [gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:275>) [ordering](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:380>)

   **Fix:** Label file observations, corpus extrapolations, and unmeasured quantities separately; remove the projected `PASS`; then production-gate both passes using the committed real closure set before authorizing pass 2 corpus-wide.

6. **Medium — sampling working set cannot guarantee “fail rather than swap.”** Working set counts resident pages and can fall as Windows pages memory out; `PrivateUsage` is the process commit charge. Pass 2 also adds the unmeasured persistent closure set to the node index, which the 6.58 GB measurement did not include. [memory gate](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:296>) [Microsoft memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)

   **Fix:** Enforce the ceiling on `PrivateUsage`/commit—preferably with a Job Object hard limit—while retaining working set only as an observability metric, and measure the real pass-2 peak with `S` loaded.

VERDICT: REVISE
### Post-loop corrections (UNREVIEWED — applied after round 6, seen by no reviewer)

The review loop is closed; both caps are exhausted. Three corrections were nonetheless applied, because
each is an outright internal contradiction rather than a design question, and one of them would actively
mislead an implementer:

1. **round-6 #4** — the proof required `historic:highway` to be EXCLUDED while the disposition table (fixed
   in v6 per round-5 #6) RETAINS it. An implementer following the proof would have reintroduced exactly the
   irreversible loss round 5 identified. The proof now requires it retained, with `not:` and `source:` as
   the only exclusions. My own v6 edit changed the table and missed the proof.
2. **round-6 #5** — the entry-gate table marked the two-pass corpus projection `PASS`. A projection cannot
   pass a gate. Now labelled `EXTRAPOLATED / NOT ASSESSED`.
3. **round-6 #5** — the opening claimed "every runtime number is measured on the worst-case file". It is
   not: corpus figures are extrapolations, pass 2 has never run, and the production path does not exist.
   Replaced with three explicitly separated categories.

**These three are not reviewed.** The remaining four findings (#1 under-keyed closure, #2 anchor-domain
geometry, #3 the NTFS state table, #6 commit-charge vs working-set enforcement) are design work and are
left open for the sign-off decision rather than silently patched.

---

# LOOP 2 — fresh caps, opened after v7

Loop 1 exhausted both caps (rounds 6 of 6, attempts 8 of 8) and resolved **deadlocked** at body
`a325021d`. Josh's decision: apply all four open findings, then review v7 with a fresh budget.

**v7 applied Codex's prescribed fix for each of the four, and they are UNREVIEWED going in:**

| round-6 finding | fix applied in v7 |
|---|---|
| #1 critical — `S` under-keyed | `S = {(site_id, osm_id)}` bound into the manifest DAG; three independent flags (`intersects_window`, `selected_by_predicate`, `closure_only`) replacing one conflated boolean; all six endpoint flags added to the identity-edge schema; pass-1 duplicates suppressed |
| #2 — anchor domain not geometric | anchors are geometry **clipped** to the site box; `max_complete_radius_m = inf distance(site_box, complement(mask))` in the same per-site UTM projection Plan B uses; closure-only endpoints excluded from Plan B's spatial candidate domain |
| #3 — NTFS table incomplete | added row 0 (clean pre-publish, which v6 omitted so a classifier would fail closed on a clean tree); `d_old == d_new` no-op; file identity as a row condition; row 6 split by backup digest with the placeholder step named, since `ReplaceFileW` requires an existing destination; idempotence relocated to the reclassify-then-act **entrypoint** |
| #4 — working set cannot detect swapping | ceiling enforced on **`PrivateUsage`** commit charge, preferably a Job Object hard limit (`forecast/sandbox_process.py` already uses Job Objects); working set demoted to observability only; pass 2 gated on re-measuring peak commit with the real `S` resident |

Resolved caps for loop 2: `MAX_ROUNDS` 3, `MAX_ATTEMPTS` 4. Deliberately tighter than loop 1 — loop 1's
finding count plateaued at 6 with each revision generating comparable new surface, so an open-ended budget
is not obviously the right instrument. If loop 2 plateaus too, that is the answer about this plan's
remaining risk, not a reason to keep spending.

Reviewer re-checked before opening: PATH `codex` is **0.146.0**, still outside `verified_versions`
(`>=0.130 <0.146`) and still shipping the broken sandbox-helper layout on this box. Pinned to the
verified, repaired **0.145.0** release binary again, same session, same model.

## Round 7 — codex (loop 2, round 1 of 3)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: 2ee7ac8fb410df497ede04be658db8ed1f6c6a6cd3507c2cdaaafc2aec6d2894
- verdict: REVISE (1 critical, 3 high, 2 medium)

**The critical was a self-defeating bug in v7's own fix, and it would have failed silently.** v7 suppressed
pass-2 emissions keyed on `(site_id, osm_id)`. But every pair in `S` is in `S` *because pass 1 emitted it
in at least one origin* - so the rule suppresses the other-origin counterpart that pass 2 exists entirely
to recover. Pass 2 would have emitted **nothing**, the identity edges would simply have been absent, and
nothing anywhere would have raised an error. Fixed by keying suppression on
`(site_id, origin, source_region, osm_id)`.

**Two claims of mine were checked against the code and one was wrong.** v7 asserted that a Job Object
memory limit would terminate the process and that `forecast/sandbox_process.py` already exercised the
mechanism. Neither holds: `JOB_OBJECT_LIMIT_PROCESS_MEMORY` makes an over-limit *allocation fail*, and the
helper sets `LimitFlags = 0x2000 | 0x400` (kill-on-close, die-on-unhandled-exception) with **no memory
limit** - `ProcessMemoryLimit` and `JobMemoryLimit` are never assigned. Job Objects are exercised there for
process containment, which is a different purpose. `TerminateJobObject` *is* bound, so the fix has a call
to use.

**Stale measurement language survived a fourth consecutive round** (#6): "worst-case file" after
establishing that bytes do not order memory, a 2.6x margin computed from working set after working set was
demoted from the gate, and 6.58 GB described as a "ceiling". Recomputed from commit charge the pass-1
margin is 2.07x, and the pass-2 gate file should be chosen by maximum observed commit, not compressed size.

### Critique (verbatim)

Material defects remain.

1. **Critical — duplicate suppression still defeats closure.** Every `(site_id, osm_id)` in `S` exists because pass 1 emitted that pair in at least one origin. Suppressing pass 2 whenever that same two-column pair was emitted therefore suppresses the other-origin counterpart that pass 2 exists to recover. [closure](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:239>) [suppression](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:265>)

   **Fix:** Track pass-1 emissions by `(site_id, origin, source_region, osm_id)` and suppress only that exact record while still emitting every missing origin/region counterpart selected through `S`.

2. **High — the flags still produce the wrong Plan C road supply.** A tag-changed counterpart can have `intersects_window=true` but `selected_by_predicate=false`; defining road supply solely on `intersects_window` includes that non-road closure record. It also remains `closure_only=true`, contrary to the proof’s “rather than being stamped closure-only” wording. [flags](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:253>) [supply](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:261>) [proof](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:740>)

   **Fix:** Define road supply and road coverage as `intersects_window AND selected_by_predicate`, define `closure_only = NOT(intersects_window AND selected_by_predicate)` for retained endpoints, and require the tag-changed fixture to carry both `intersects_window=true` and `closure_only=true`.

3. **High — the NTFS classifier still lacks a valid first-publication and identity protocol.** A brand-new manifest starts with `D`, `S`, and `B` all absent, which no row covers. The expected file IDs used after a crash are never durably recorded; row 6b creates a new placeholder whose identity cannot satisfy row 4 after another kill; the unconditional equal-digest no-op can succeed even when `D` is absent; and row 6a restores from `B` immediately before a rule saying never to restore from `B`. [table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:487>) [rules](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:504>)

   **Fix:** Add an all-absent initialization row, condition the equal-digest no-op on a verified destination, either persist expected identities in a flushed transaction intent or remove that unverifiable criterion, and roll verified staging forward by atomic rename rather than exposing an old/empty placeholder.

4. **High — the Job Object limit does not provide the promised termination behavior.** `JOB_OBJECT_LIMIT_PROCESS_MEMORY` causes an over-limit commit attempt to fail; it does not itself guarantee process termination. The reused job helper currently sets only kill-on-close and die-on-unhandled-exception, not any memory limit. [sandbox_process.py](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/forecast/sandbox_process.py:81>) [Microsoft job-limit documentation](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)

   **Fix:** Freeze a supervised child-process design using a process/job commit limit plus explicit memory-limit notification or allocation-failure handling that calls `TerminateJobObject`, and ensure both `S` and the node index are inside the limited job total.

5. **Medium — clipped anchors can cease to be `LineString`s.** Intersecting a winding way with a box can yield a `MultiLineString`, point-only touch, geometry collection, or empty geometry; the plan freezes neither component handling nor projection-versus-clipping order, so two conforming Plan B implementations can generate different candidates. [anchor contract](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:276>)

   **Fix:** Project first into the frozen site UTM, intersect there, retain all positive-length lineal components as the anchor, and explicitly exclude or flag empty and point-only intersections.

6. **Medium — stale measurement claims remain.** The plan still calls Indonesia the “worst-case file” after stating byte size does not order memory, reports a 2.6× margin from working set after demoting working set from the gate, and calls 6.58 GB a “ceiling.” The commit-based pass-1 margin is approximately 2.07×, and the pass-2 pilot should use the file with maximum observed pass-1 commit, not largest bytes. [index claim](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:311>) [memory interpretation](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:366>) [projection](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:372>)

   **Fix:** Rename Indonesia the largest-by-bytes tested file, calculate margin from 8.22 GB commit charge, and select the pass-2 gate file from pass 1’s measured maximum commit rather than compressed size.

VERDICT: REVISE
## Round 8 — codex (loop 2, round 2 of 3)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: adb89de3c6749ca99f46c55d1d2f16cd58f6210e05c7eb8ee4ffa4d1551d75cf
- verdict: REVISE (6 critical, 3 high, 1 medium)

### THE TREND REVERSED, and the cause is localised

| round | findings | criticals |
|---|---|---|
| 1 | 16 | 5 |
| 2 | 16 | 4 |
| 3 | 10 | 2 |
| 4 | 9 | 1 |
| 5 | 6 | 1 |
| 6 | 6 | 1 |
| 7 | 6 | 1 |
| **8** | **10** | **6** |

**Five of the six criticals (#4, #5, #6, #7, #8) are defects in the transaction-intent record that v8
introduced one round earlier to fix round-7 #3.** One fix to the publication protocol produced five
criticals. This is no longer "the reviewer finds progressively smaller problems"; it is a subsystem
generating new failure modes faster than prose can close them.

Meanwhile the reviewer opened with the first positive statement in eight rounds: *"The corrected
suppression key and derived `closure_only` truth table are sound within the acquired corpus."* The
**data-model half is converging. The publication-protocol half is diverging.**

Three of my own errors in v8 worth naming:

1. **#6** — the `init` row says "create S, then row 4's rename". **Row 4 has no rename**; its action is
   `ReplaceFileW`, which requires an existing destination. Row 6 is the rename. I referenced the wrong row
   in my own table, making first publication an impossible transition.
2. **#5** — I stated plainly that the NTFS namespace change can be lost or reordered on power loss, and
   then, in the same section, used the *absence* of the intent's directory entry as proof of a clean tree.
   Directly self-contradictory.
3. **#4** — I added the intent record and never gave it a lifecycle. Nothing deletes it, and terminal row 1
   says "none", so a stale intent poisons the next publication.

And **#10 is the fifth consecutive round of stale language**: "one raw way stream per file" after moving to
two passes, "largest-file wall-clock", a "spatial index" Plan A no longer emits, and a "conservative by
construction" guard that §2.3 already conceded was chosen.

### Critique (verbatim)

Material findings remain. The corrected suppression key and derived `closure_only` truth table are sound within the acquired corpus, but the following still break the contract:

1. **Critical — “any distance” merely moved the boundary.** Pass 2 scans only the 36 acquired extracts, so a counterpart moved outside their union remains silently absent; §6.1’s unqualified promise is false. [§2.2](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:260>)  
Fix: Scope the guarantee to “any distance within the acquired corpus,” emit per-origin presence/coverage, treat absence as UNKNOWN, or acquire globally covering snapshots.

2. **Critical — `max_complete_radius_m` does not establish source completeness.** It measures distance to Plan A’s processing-mask boundary, while historical extract coverage explicitly remains UNKNOWN; it proves only that Plan A added no further truncation. [§2.3](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:314>)  
Fix: Rename it `max_processing_radius_m` and make completeness conditional on separately proven historical source coverage.

3. **High — per-site facts have no defined post-dedup representation.** Flags are keyed by site, but deduplication is keyed only by `(origin, osm_type, osm_id)`, and the promised origin output names only `source_regions[]`; identity edges cannot carry Plan C membership for single-origin ways. [§4.1](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:419>)  
Fix: Publish a manifest-bound `(site_id, origin, osm_type, osm_id)` membership/flag table, or freeze an exact consumer-side rederivation contract.

4. **Critical — the intent record has no lifecycle state.** It is absent from the table, no action deletes it, and terminal row 1 says “none,” leaving a stale intent to poison the next publication. [§5.2](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:534>)  
Fix: Add intent presence/version to every state and delete it last, only after verified `D=d_new`, `S/B` absent, with kill tests around deletion.

5. **Critical — “no intent means pre-publish” contradicts the stated NTFS durability limit.** A power loss may lose or reorder the intent’s directory entry independently of `D/S/B`, so absence cannot establish a clean tree and the classifier does not make that survivable. [durability claim](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:579>)  
Fix: Treat absent intent as clean only after validating the last committed DAG/pointer and finding no transaction remnants; otherwise fail closed and narrow the survivability claim.

6. **Critical — first publication invokes an impossible transition.** `init` has `D` absent but says to create `S` and use row 4, whose action is `ReplaceFileW(D,S,B)` and requires an existing destination. [state table](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:541>)  
Fix: Route flushed first-publication staging through row 6’s `MoveFileExW(S,D)` transition.

7. **Critical — the claimed identity checks are not implementable.** Intent records only the old destination file ID, not staging’s ID, while row 6 accepts `B=any` and then deletes it; a foreign same-digest staging file can satisfy a row and an unrelated backup can be destroyed.  
Fix: Record staging identity and an operation nonce before mutating `D`; permit `B` only absent or verified-old, with every other identity routed to row 8 and never deleted.

8. **High — concurrent first publication is not actually serialized by specification.** Only classification/recovery is explicitly inside the lock critical section; intent absence checking, exclusive creation, staging, publication, cleanup, and intent deletion are not. [lock rule](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:576>)  
Fix: Put the entire transaction under the fixed locks, create intent/staging with `CREATE_NEW`, and test two simultaneous first publishers.

9. **High — the Job Object termination signal is not guaranteed.** Microsoft documents ordinary completion-port messages such as `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT` as non-guaranteed; therefore the supervisor cannot promise to call `TerminateJobObject` on every hard-limit breach. [Microsoft Job Objects documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)  
Fix: Register a guaranteed `JobObjectNotificationLimitInformation` threshold below the 17 GB hard limit before starting the child, terminate on that notification, and treat allocation failure or abnormal exit as stage failure.

10. **Medium — stale overclaims remain.** The plan still says “one raw way stream per file” despite two passes, labels Indonesia’s result “largest-file wall-clock,” says Plan A supplies a spatial index after deleting that output, and calls the chosen 5 km guard “conservative by construction.”  
Fix: Change these respectively to “one stream per file per pass,” “Indonesia parser wall-clock,” “GeoParquet from which Plan B builds an index,” and “chosen processing guard.”

VERDICT: REVISE
## Round 9 — codex (loop 2, round 3 of 3 — FINAL)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: 51b2b12e89b1ed3cd5198d96ad3c26a3fd0ddc1d379323aec2e092db0b79bb74
- verdict: REVISE (2 critical, 4 high, 2 medium)

### Where the findings live, across nine rounds

| round | findings | criticals | of which in §5 commit protocol |
|---|---|---|---|
| 5 | 6 | 1 | 1 |
| 6 | 6 | 1 | 1 |
| 7 | 6 | 1 | 1 |
| 8 | 10 | 6 | **5 of 6 criticals** |
| 9 | 8 | 2 | **4 of 8, incl. both criticals** |

**§5 has produced criticals in three consecutive rounds, each time from my own fix to it.** Round-7 #3
said the state table was incomplete; fixing it produced five criticals in round 8; fixing those produced
four more findings and both criticals in round 9. The data-model half moved the other way over the same
span: round-7's critical (suppression key) is closed, and round 9's data-model findings are a missing
presence schema (#5), an assertion false-negative (#7) and stale labels (#8).

Before round 9 I recommended splitting §5 out of the plan and settling it in code with kill-tests. Josh
chose to keep it in and fix all ten; that was done in v9 and this is the result. Recorded as outcome, not
as argument.

**Round-9 #1 is a chicken-and-egg I built myself:** the intent must be written *before* staging is created,
yet must *contain staging's file ID*. Both cannot hold. #2 is a determinism failure: with
`d_old == d_new`, rows 0 and 1c both match and prescribe opposite actions. #3 is a self-contradiction
between row 3 (`S` then `B`) and the cleanup rule (`B` then `S`), with an uncovered state in between.

**#7 is a real hole in a safety net I had leaned on.** §1.2's assertion compares two *booleans*, so a way
carrying `mystery:highway` **and** ordinary `highway` satisfies both predicates and the unknown namespace
goes undetected. I had told Codex and Josh that this assertion was what made partial census coverage safe.
It is weaker than that: it catches an unknown namespace only on ways that have no ordinary `highway` tag.

**#8 is the sixth consecutive round of stale labels.** This is a pattern in how I edit, not in the design:
each round I correct a claim in one location and leave the same claim standing elsewhere.

### Critique (verbatim)

Material defects remain despite the closure and membership improvements:

1. **Critical — intent creation is impossible as specified.** The intent must be written before staging creation yet must contain staging’s file ID; row 0 explicitly has `S` absent, and first publication also lacks a state for `intent=present, D/S/B=absent`. [§5.2](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:568>)  
Fix: Create, write, flush, and identify staging under the locks before publishing the intent, then treat no-intent staging as an enumerable orphan; alternatively add a provisional-intent phase and all associated crash states.

2. **Critical — `d_old == d_new` makes the table non-deterministic.** With intent present and `D=d_old=d_new`, `S/B` absent, both row 0 and row 1c match but prescribe opposite actions; the no-op exists only in the proof. [state table](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:573>)  
Fix: Resolve verified equal-digest publication under the locks before creating intent, and specify an explicit equal-digest recovery rule.

3. **High — cleanup order contradicts itself and creates an uncovered state.** Row 3 deletes `S` then `B`, while the rule deletes `B` then `S`; a kill after the latter’s first deletion yields `intent present, D=d_new, S=d_new, B absent`, which matches no recoverable row. [cleanup rule](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:608>)  
Fix: Freeze `S → B → intent` everywhere and test a kill after each deletion.

4. **High — absent-intent remnant detection is not implementable from the recorded data.** The exact staging and backup paths depend on a nonce stored only in the potentially missing intent, yet recovery promises to inspect “any derived path” without defining an enumerable naming rule.  
Fix: Freeze target-prefixed, directory-enumerable transaction filenames and scan them under the locks; any matching remnant must fail closed or enter an explicit orphan-cleanup state.

5. **High — the promised presence/UNKNOWN output still has no schema.** The frozen edge schema contains no presence fields, and a way present in only one origin has no edge on which to emit anything; the membership table records present members but cannot represent absent origins. [§6.1 schema](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:649>)  
Fix: Publish a table keyed `(site_id, osm_id, origin)` with `presence_in_acquired_corpus` and a distinct `global_counterpart_status`; build edges only between present endpoints.

6. **High — the guaranteed memory notification remains under-specified.** “Below 17 GB” does not freeze the actual authorization ceiling, and the proof’s generic over-limit allocation could exercise only the hard-limit allocation-failure path rather than the notification path. [§3](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:407>)  
Fix: Freeze and record an exact soft threshold, then separately test gradual allocation crossing it below 17 GB and a single allocation rejected by the hard limit.

7. **Medium — the unknown-tag assertion has a false-negative case.** Boolean predicate equality does not detect `mystery:highway` when the same way also has ordinary `highway`; both predicates remain true despite the unknown namespace. [§1.2](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:220>)  
Fix: Independently assert that every observed `*:highway` key belongs to the disposition table, including a fixture co-tagged with ordinary `highway`.

8. **Medium — stale overclaims remain.** The measurement table still calls Indonesia the “largest-file pipeline,” the risks still call the chosen guard “conservative,” and §4.6 says the duplicate preflight is step 3 although the table makes it step 4.  
Fix: Relabel the measurements as Indonesia-only, remove “conservative,” and correct the stage reference.

VERDICT: REVISE
---

# LOOP 3 — scoped to §5 (commit protocol) only

Loop 2 exhausted its rounds and resolved **deadlocked**. Josh's decision: a third loop scoped to the
commit protocol alone, leaving the rest of the plan unreviewed rather than unfixed.

Resolved caps: `MAX_ROUNDS` 3, `MAX_ATTEMPTS` 4.

**Why §5 specifically.** Across rounds 7–9 the findings separated cleanly by section:

| round | total | criticals | in §5 |
|---|---|---|---|
| 7 | 6 | 1 | 1 |
| 8 | 10 | 6 | 5 of 6 criticals |
| 9 | 8 | 2 | 4 of 8, both criticals |

Every §5 critical in rounds 8 and 9 was a defect in the previous round's §5 fix. The data-model half
converged over the same span.

**Fixed outside §5 before this loop opened** (not submitted for review, but not left broken):

- **§1.2 census COMPLETE** — all 36 extracts, 34,764,774 retained ways, 18 distinct `:highway` keys, set
  difference 2,740. The table frozen from five extracts was missing `destroyed:` (278 in the difference),
  `former:` (25), `removed:` (3) and `disabled:` (3) — **309 ways would have been silently dropped**.
- **§1.2 assertion rewritten** (round-9 #7) from predicate equality to **key membership**. The census
  proved the hole is real: `indoor:` (86), `note:` (9) and `collapsed:` (3) occur only alongside ordinary
  `highway`, so they never enter the set difference and boolean equality could never see them. The claim
  that partial census coverage was safe *because* of that assertion was wrong in both halves.
- **§6.3 presence table** (round-9 #5) keyed `(site_id, osm_id, origin)`.
- **§3 soft threshold frozen at 14.0 GB** (round-9 #6); "below 17 GB" froze nothing.
- **Stale labels** (round-9 #8) — sixth consecutive round.

Reviewer re-checked: PATH `codex` is still 0.146.0, outside `verified_versions`. Pinned to 0.145.0 again.

## Round 10 — codex (loop 3, round 1 of 3 — SCOPED TO §5)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75 (resumed; thread_id echoed and matched)
- reviewed body_sha256: de6696c132d1460047c1d829a0a276019521f91b815d40173189ab7f3103dd77
- verdict: REVISE (2 critical, 4 high, 1 medium) — all in §5, as scoped

**Two of the seven are regressions v10 introduced while fixing round 9.**

**#2 is fatal to the fix I was most pleased with.** v10 put the operation nonce in staging *content* as
well as in the intent. But `ReplaceFileW`/`MoveFileExW` publish staging's bytes **unchanged** — so a
per-run nonce either changes `d_new` on every run, destroying deterministic manifests and equal-digest
reuse, or leaves staging's digest disagreeing with the `d_new` the manifest declares. The nonce now lives
only in the intent; staging is authenticated by its recorded file ID plus `d_new`.

**#4 is a field I silently deleted.** Rewriting the intent's contents in v10, I dropped the destination's
pre-mutation file ID — the thing "verified B" was supposed to compare against. The classifier claimed
identity verification with nothing recorded to verify against. Both identities are now stored, and a valid
`B` is defined as digest `d_old` **and** the recorded pre-mutation file ID.

**#1 is an overlap I created in the same edit:** `orphan` accepted `B = any` and deleted it, while row 8
accepts any unverified identity and deletes nothing — the same state meaning two opposite things, and a
path to destroying an unverified backup. `orphan` now requires `B` absent.

**#3 killed target-derived suffixes.** They are enumerable but not collision-free: an artifact legitimately
named `foo.__stg` *is* the staging path for target `foo`. Replaced with a same-volume
`.__txn/<sha256(canonical target path)>/` directory — still enumerable, now collision-resistant.

**#6 is the sharpest.** Write-side DAG validation cannot protect a consumer across a reboot: namespace
changes may reorder, so the pointer's rename can survive while a child manifest's directory entry does
not. Every pointer *dereference* now revalidates the full DAG, with startup recovery first.

**#7 is the seventh consecutive round of stale cross-references** — the proof still named a row 0 that no
longer exists. Regenerated from the current table.

### Critique (verbatim)

§5 still has material defects:

1. **Critical — `orphan` overlaps row 8 and may delete an unverified backup.** `orphan` accepts `B=any`, while row 8 accepts every unverified identity; the same state can therefore mean “delete B” or “delete nothing,” directly contradicting the B-verification rule. [state table](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:609>)  
Fix: Restrict orphan cleanup to `intent absent, S valid-for-target, B absent`; any B without a valid intent must route to row 8 and never be deleted automatically.

2. **Critical — putting the nonce in staging content breaks manifest identity.** `MoveFileExW`/`ReplaceFileW` publishes staging bytes unchanged, so a fresh nonce either changes `d_new` every run—defeating equal-digest reuse and deterministic manifests—or makes staging’s digest differ from the declared `d_new`. [nonce rule](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:582>)  
Fix: Keep the nonce only in intent and authenticate staging using its recorded file ID plus `d_new`; any nonce-removal transformation would require additional committed states.

3. **High — target-derived suffixes are enumerable but not collision-free.** A legitimate target named `foo.__stg` occupies exactly the staging path for target `foo`; recovery for `foo` could classify or delete another target.  
Fix: Reserve and validate the suffix namespace for all targets, or use a dedicated same-volume transaction directory keyed by a collision-resistant hash of the canonical target path.

4. **High — “verified B” remains undefined.** The intent records staging’s file ID but no original destination or expected backup identity, while the classifier claims digest-and-identity comparison and routes an “unverified” B to row 8. [intent fields](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:592>)  
Fix: Record the pre-mutation destination identity and explicitly define which observable digest/path/identity transition authenticates B after each `ReplaceFileW` outcome.

5. **High — equal-digest no-op is not ordered after recovery.** If `D=d_new` but stale intent/staging/backup artifacts remain, the pre-table no-op can return without classifying or cleaning them, causing the next same-target operation to collide with `CREATE_NEW`.  
Fix: Under the locks, recover or fail on all remnants first; permit the no-op only when intent, S, and B are absent and the DAG/pointer validate.

6. **High — the power-loss durability claim lacks a mandatory consumer gate.** Because namespace changes may reorder, the pointer rename may survive while a child manifest’s namespace entry does not; validation only before pointer replacement cannot protect a consumer after reboot. [§5.3](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:652>)  
Fix: Require every pointer dereference to revalidate the complete hash-linked DAG before returning artifacts, with startup recovery completed first.

7. **Medium — the proof still targets the previous table.** It names nonexistent row 0 and does not specifically exercise the new orphan and 2b transitions or the staging-before-intent kill boundary. [proof](<C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:895>)  
Fix: Generate tests from the current state variants and inject a kill before and after every adjacent action, including orphan cleanup and each `S → B → intent` deletion.

VERDICT: REVISE
## Round 11 — codex (loop 3, round 2 of 3 — scoped to §5)

- model: gpt-5.6-sol (reasoning xhigh) · CLI codex-cli/0.145.0 (pinned) · grounding: repo · qualifying: yes
- session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
- reviewed body_sha256: e0c8c4d205cb60b6555f31a39f6b9c8a14ba828998927cb0f1ecba843a8f948b
- verdict: REVISE (4 critical, 2 high, 1 medium) — all §5

It also answered a question I put to it: **NTFS file IDs can be reused after deletion**, so the identity
check v11 strengthened had a hole in it.

**Two of the four criticals were consequences of v11's own fixes:**

- The `.__txn/<sha256>` directory fixed the collision problem (round-10 #3) and **destroyed
  identifiability** — SHA-256 is irreversible, so a scan finds a hash directory and staging bytes but
  cannot recover the target, the cache-key lock, or `d_new`.
- The `orphan` rule **contradicted the plan's own power-loss model**: absence of an intent does not prove
  `D` was never mutated, because reordered namespace persistence can leave staging as the only copy of the
  new payload. The rule would have deleted it.

### §5 findings by round — the reason v12 abandons the design instead of patching it

| round | §5 findings | §5 criticals |
|---|---|---|
| 7 | 1 | 1 |
| 8 | 5 | 5 |
| 9 | 4 | 2 |
| 10 | 7 | 2 |
| 11 | 7 | 4 |

**Five consecutive rounds, and in each one the new criticals came from the previous round's fix.** The
nonce that broke digest determinism, the hashed directory that lost identifiability, the orphan rule that
contradicted the durability model. This is not a run of unlucky oversights: it is a design whose
correctness depends on reasoning about a multi-file namespace under reordering, and prose specification
keeps failing precisely there.

### v12 — remove the thing generating the findings

Publication becomes **immutable content-addressed writes plus one pointer swap**. Every artifact is written
to `<store>/<sha256>` via temp → flush → rename; nothing is ever overwritten, so there is no `d_old`, no
backup, no intent, and no recovery state machine. The single mutable object is the pointer, whose content
is the current stage-manifest digest, and every `ReplaceFileW` outcome for it leaves a pointer naming a
complete DAG. A crash leaves only **unreferenced** artifacts, which recovery never deletes — an offline
mark-and-sweep removes them, and an interrupted sweep is harmless.

Six of round 11's seven findings dissolve rather than being answered: no state machine (#1), no rows (#2),
no transaction slots (#3), nothing deleted on recovery (#4), digest rather than file-ID identity (#5), no
path-derived transaction namespace to canonicalise (#6). #7's snapshot semantics is adopted directly.

The accepted cost is disk — superseded artifacts persist until swept, on a machine already constrained.
Garbage is recoverable; a corrupted publication is not.

**Codex validated two things explicitly**, which is worth recording after five rounds of criticals: the
narrow durability wording is defensible, and consumer revalidation correctly converts reordering into a
hard error rather than a partial read.

### Critique (verbatim)

§5 still has material defects.

1. **Critical: the “complete” table omits clean entry states.** Before an update, `I/S/B` are absent and `D=d_old`; before first publication all four may be absent. Neither state appears in the table, although recovery is mandatory before staging begins. An empty transaction directory created before `S` is another uncovered state. [§5.2 table](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:623>)  
   **Fix:** Add explicit `clean-existing`, externally-authorised `clean-first`, and empty-slot rows.

2. **Critical: `init` and row 6 overlap.** Both accept `intent=present, D=absent, S=d_new, B=absent`; meanwhile the intent supposedly always contains a pre-mutation destination file ID, which cannot exist for `init`.  
   **Fix:** Model `prior_destination` as the tagged union `ABSENT | {digest, volume_id, file_id}` and predicate both rows on that field.

3. **Critical: an intentless hashed slot is enumerable but not identifiable.** After the staging-before-intent crash, scanning yields only a SHA-256 directory and `S`; the hash is irreversible, so recovery cannot recover the target, cache-key lock, `d_new`, or meaningfully evaluate `valid-for-target`.  
   **Fix:** Flush a self-describing owner/pre-intent containing canonical target, cache key, old state, and `d_new` before creating `S`; authenticate `S` by `d_new` afterward.

4. **Critical: the orphan deletion proof contradicts the power-loss model.** Absence of intent does not prove that `D` was never mutated: reordered namespace persistence can leave `D=d_old, S=d_new, B/I=absent` after replacement began. The orphan row then deletes the only new payload, potentially while the pointer names the new DAG.  
   **Fix:** Never delete intentless staging based solely on path layout; require the pre-intent above or fail closed/quarantine after comparing the committed pointer.

5. **High: file identity is inconsistently and partly unjustifiably authoritative.** Rows with `D=d_new` do not require `D` to carry recorded `S` identity, despite the prose claiming identity comparison. Microsoft guarantees that resulting `D` retains the replacement file’s ID, but does not clearly guarantee the proposed backup-ID invariant across every success/failure/retry path; file IDs may also be reused after deletion. [ReplaceFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew), [file-ID semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information)  
   **Fix:** Make digest plus exclusive transaction-path ownership authoritative and IDs diagnostic, or gate implementation on live NTFS tests and require `(volume serial, file ID)` for every applicable `D/S/B` row.

6. **High: “canonical target path” is not a frozen algorithm.** Case aliases, 8.3 names, hard links, and missing first-publication targets can map one NTFS object to different hashes and slots. `GetFullPathName` itself does not canonicalize the supplied name. The plan also does not explicitly apply reparse/volume checks to the sibling `.__txn` chain. [Windows naming rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file), [GetFullPathName](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfullpathnamea)  
   **Fix:** Define canonicalization from an opened parent handle plus validated final component, reject case-sensitive directories and hard-linked targets, reserve `.__txn`, and validate every transaction-path component as local NTFS and non-reparse.

7. **Medium: read-side validation needs snapshot semantics.** Revalidating the DAG does close the integrity gap only if the pointer is read once and consumers use the exact bytes or handles validated; validating paths and reopening them later leaves a TOCTOU gap. [§5.3](</C:/Users/josha/OneDrive/Documents/Satellite Image Classifier/OSM-NORMALISATION-PLAN.md:678>)  
   **Fix:** Freeze one pointer snapshot per read and return artifacts through handles opened and hashed during that traversal.

The narrow durability wording itself is defensible: it promises atomic visibility and flushed contents, not power-loss durability of namespace changes. Consumer revalidation correctly converts reordering into a hard error rather than a partial read. The unresolved classifier and orphan states prevent the recovery protocol from supporting that claim yet.

VERDICT: REVISE