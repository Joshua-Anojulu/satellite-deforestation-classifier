---
review_provenance:
  schema_version: 2
  status: deadlocked
  rounds:
    - round: 1
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 37c951dfa7a2000227012b15bfe682bf9589d803e9ad50bbefd49660b65d4878
      verdict: REVISE
    - round: 2
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 03ccff3ca1e9673725e2fef57aed31923f67d4c46273216f5ba84cfd6d610c58
      verdict: REVISE
    - round: 3
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 12d1e8f5994724870dc23c64b6d0f5fc4ff60df680fd8f8afcceaba06a77dae7
      verdict: REVISE
    - round: 4
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: fdbc5449f5afcdd7b58bf1fbbee726f0779f321c47ccb5bb24e3928c328f367d
      verdict: REVISE
    - round: 5
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 9082a610776787f6d4129c607120d954acb6681368d1dbcfe359ba4c4a3ca296
      verdict: REVISE
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan A: OSM normalisation infrastructure for Specification W
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–4, a preflight, and three measurements_

> **Position.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md` (`reviewed-unapproved`).
> **Plan B** (vintage audit) and **Plan C** (feature extraction) consume this output and are unwritten.

## Goal

Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned road-network
cache that Plan B and Plan C consume without re-parsing. **No scientific decisions**: no tier selection,
no vintage position, no classification thresholds.

## What is measured, and what a previous version of this plan got wrong

Every runtime number below is now measured on the worst-case file. The estimates they replace were wrong
in both directions and are withdrawn.

| quantity | v3 claimed | **measured** |
|---|---|---|
| largest-file pipeline, geometry sampled | unmeasured; "2.7 h corpus, way stream only" | **18.3 min** (`indonesia-220101`, 1433 MB) |
| largest-file pipeline, **§1.5 full validation** | — | **22.5 min** (1348 s) |
| ways in that file | ~18 M inferred | **43,250,208** (30,174 ways/MB, v3 was 2.35× low) |
| throughput, fully validating | 12,658 ways/s | **32,085 ways/s** incl. node decoding and index build |
| geometry availability | unknown | **4,839,062 / 4,839,062 = 100 %** of retained ways |
| ways with a missing or invalid node location | unknown | **0** |
| peak working set | unmeasured | **6.58 GB = 19.3 %** of the machine's 34.1 GB |
| peak commit | unmeasured | **8.22 GB** |
| corpus size actually parsed | "9.42 GB" | **8.64 GB** — 9.42 GB is the whole static archive, not its OSM subset |
| corpus projection | 2.7 h | **≈ 260.7 M ways, ≈ 2.26 h** |

**Two runtimes, and the slower one is binding.** The 18.3-minute figure checked only each retained way's
first node location. §1.5 requires *every* node of every retained way to be checked, which is a per-node
loop the first run never paid for. The gate in §3 is measured against the **fully validating** pipeline,
because that is the pipeline this plan actually specifies.

**v3's throughput figure was an artefact of the benchmark, not of pyosmium.** The predicate ran a generator
over every tag of every non-highway way; a direct key lookup is 2.6× faster (46,467 vs 17,849 ways/s) on
identical matches. v3's "2.7 hours" was not right in any component: it undercounted ways-per-MB by 2.35×,
undercounted throughput by ~2.5×, and applied both to 9.42 GB — the size of the *entire* static archive
rather than its 8.64 GB OSM subset. Three errors in partial mutual cancellation are not a corroborated
estimate, and none of it is the basis for anything here.

Three parser designs were invalidated before this one, each by measurement rather than argument:

| design | why it failed | found by |
|---|---|---|
| `GetNextFeature()` / `ogr2ogr` | `osgeo` and CLIs not installed | probe |
| pyogrio bbox-to-site-union | envelope **202×** the true window area; **no node references** | reviewer + API check |
| pyosmium *inside the assistant's background window* | 21 min/file exceeds a 6–11 min limit | benchmark |

The third was a misdiagnosis. The 6–11 minute ceiling constrains *Claude's* execution, not the machine;
Josh ran the 10.92 GB GFC acquisition to completion in his own terminal. **This plan is a long-running job
Josh launches.** Checkpoints exist for crash resilience, not to fit a seven-minute window.

## Approach

### 1. One raw way stream per file — no GDAL layers

pyosmium reads the OSM data model directly, so GDAL's `lines` / `multipolygons` / `other_relations`
routing does not exist. That dissolves round-1 #1 (0.107 % of highway features were being lost to
`multipolygons`) rather than working around it, and makes node references available (round-2 #3).

1.1 **The frozen pipeline** (round-3 #1 — v3's call could not produce geometry at all):

```python
osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY)
      .with_locations()                                        # flex_mem; see §3
      .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
```

`FileProcessor(path, WAY).with_locations()` raises `RuntimeError: Nodes not read from file` — nodes must
be in the entity set to reach the location cache, and the filter removes them after location assignment,
not before. This exact pipeline is the one benchmarked above.

1.2 **Selection predicate — derived from a corpus census, not from imagination** (round-4 #1).

    v4 froze six lifecycle keys and asserted that a `:highway`-suffix predicate matched "the same ways
    (234,593 vs 234,570)". Those are not the same number, and calling them identical was wrong: **23 ways
    differed, and the plan was therefore known not to preserve a stable population.** Round-4 #1 is
    correct, and its fix — materialise the difference, classify the keys, expand the list as necessary —
    is adopted literally.

    A census enumerates every tag key ending in `:highway`, together with the exact **set difference** —
    the ways a suffix predicate retains that the frozen predicate does not. That difference is the only
    population whose retention actually changes; a way carrying `source:highway` *and* `highway` is
    retained either way and is not evidence of anything. (My first attempt at this counted the latter and
    would have overstated the problem.)

    **Census coverage is partial and is stated as such**: it is running over all 36 extracts and the table
    below reflects the extracts completed so far, with per-file counts in the review log. The table is what
    freezes the predicate; the **run-time equality assertion below is what makes partial coverage safe**,
    because any key not in it halts the stage rather than silently changing the population.

    | key | disposition | why |
    |---|---|---|
    | `highway` | **retain** | the road tag itself |
    | `disused:highway` | **retain** | frozen in v4; standard lifecycle prefix |
    | `abandoned:highway` | **retain** | frozen in v4 |
    | `proposed:highway` | **retain** | frozen in v4 |
    | `construction:highway` | **retain** | frozen in v4 |
    | `razed:highway` | **retain** | frozen in v4 |
    | `demolished:highway` | **retain** | frozen in v4 |
    | `was:highway` | **retain — ADDED** | standard lifecycle prefix; v4 omitted it |
    | `area:highway` | **retain — ADDED** | established tagging for road *areas*; v4 omitted it |
    | `not:highway` | **exclude** | negative assertion — states the feature is *not* that road |
    | `source:highway` | **exclude** | metadata about where the `highway` tag came from |
    | `historic:highway` | **exclude** | historic designation, not a present or former carriageway |

    Keys are frozen **by this table**, not by a suffix rule: a suffix rule silently absorbs any future
    `<anything>:highway` namespace, including the metadata ones above — which is why "just use the suffix"
    is not the fix, and why the v4 discrepancy pointed in both directions at once. Two of the twelve keys
    were genuinely missing from v4 (`was:`, `area:`), and three would have been wrongly swept in.

    **Membership is tested by direct key lookup** over the frozen retain-list, never by a scan over the
    way's tags — that scan was v3's benchmark bug.

    **Asserted, not assumed:** the parser recomputes the retain-predicate and a reference predicate
    (`:highway` suffix minus the frozen exclude-list) over every file and **fails closed on any
    inequality**. A new namespace appearing in the corpus is then a loud failure requiring a decision,
    rather than a silent population change.

    `area:highway` ways interact with §1.4: they are stored as their ring traversal with `is_closed` set,
    and Plan A still emits no area semantics.

1.3 **Retained per way:** `osm_id`, `version`, `timestamp`, the **complete canonical tag map**, the
    **ordered node-reference list**, and the resolved coordinate sequence.

1.4 **Geometry is always a `LineString`, with `is_closed` as a boolean column** (round-3 #7). v3 invented a
    `way_closed` geometry class, which is not a GeoParquet geometry type; a closed way is stored as its
    ordered ring traversal and its lengths are perimeter lengths. **Area semantics are explicitly excluded
    from Plan A** — whether a plaza's perimeter, area or centreline is the audited object is Plan B/C's
    decision, and Plan A neither makes nor forecloses it.

1.5 **Every retained node location must be valid.** Installed pyosmium's `FileProcessor` internally
    ignores missing-location errors, so silence is not evidence (round-3 #4). Each retained way's node
    locations are checked individually; **any way with one or more invalid locations, or an empty node
    list, fails the stage closed** with its `osm_id` reported. The measured count on the worst-case file is
    recorded in §3 — this is a checked invariant, not an assumption.

### 2. Site dispatch by exact mask, during the single pass

Round-2 #2: the nine Indonesian site boxes total 0.495 deg² inside a **99.83 deg² envelope — 202×
oversized**, and clustering only reaches 110×, so no rectangle works. Instead each way is tested against
the **exact set of site window polygons** as it streams, and emitted to every window it touches. One pass,
no envelope, no `if it overruns` trigger that a killed process could never record.

**Extraction guard (frozen):** a site window is its site box buffered by **5000 m**, geodesically. That
conservatively exceeds the largest plausible downstream support (Plan C's road radii reach 1500 m) plus the
spatial-candidate radius Plan B may choose (§6), so neither Plan B nor Plan C can need a road Plan A
discarded (round-2 #4).

**Two different margins, which v3 conflated** (round-3 #9):

- **Processing-mask margin** — realised metres between each site box and the boundary of the mask Plan A
  actually applied. Computed from our own geometry, verifiable, emitted per site. This is what lets Plan C
  check that Plan A kept enough.
- **Current-polygon margin** — metres between the site window and the *current-vintage* Geofabrik `.poly`.
  Auxiliary only. It **cannot** prove what the 2020–2022 extract boundary was, so it proves nothing about
  historical coverage.

`roads_source_available` stays **UNKNOWN** regardless of either margin (§9). A large current-polygon margin
is not evidence and is never reported as if it were.

### 3. The node-location index, and the entry gate

Node references alone are not geometry; pyosmium needs a node-location index. **Frozen: `flex_mem`, the
sole backend.** v3 planned a per-file choice between `flex_mem` and an on-disk `sparse_file_array`; the
measurement below shows the in-memory index fits the worst-case file with room to spare, so the file-backed
branch is **deleted**, and with it round-3 #4's entire durability problem — there is no index file to leave
behind on a kill, no temporary-directory capacity check, and no fresh-versus-reused index question.

**Entry gate (round-3 #3) — frozen pass conditions, and the measurement against them.** v3 named a file
but no criterion, which is not a gate.

| condition | ceiling | measured on `indonesia-220101`, fully validating | |
|---|---|---|---|
| largest-file wall-clock | ≤ 45 min | **22.5 min** | PASS |
| projected corpus wall-clock | ≤ 6 h | **≈ 2.26 h** | PASS |
| peak working set | ≤ 50 % of machine RAM (17.0 GB) | **6.58 GB (19.3 %)** | PASS |
| geometry availability | 100 % of retained ways | **100 %** (4,839,062 / 4,839,062) | PASS |
| ways with a missing or invalid node location | 0 | **0** | PASS |
| temporary index disk | n/a — no index file | 0 bytes | PASS |

**These rows measure the PARSER, and they are a floor — not an authorisation** (round-4 #3). The harness
performed node decoding, index construction, the retain-predicate and per-node validation. It did **not**
perform `LineString` construction, exact-mask intersection, site dispatch, serialisation, hashing or
publication. So 22.5 min bounds the parsing component from below and says nothing about the production
stage's total. v4 presented it as though it authorised the corpus run; it does not.

**The corpus run is authorised only by a re-run of this table through the production
parser-to-committed-region path**, recorded as an immutable measurement artifact carrying: the parser
source hash, the exact command, input digests, resolved dependency versions, per-file counters, the
resource trace, and output digests. Until that artifact exists, this table is evidence that the parser is
fast enough, not evidence that the stage is.

**The largest compressed file is NOT provably the binding memory case** (round-4 #4). `flex_mem` switches
between sparse and dense representations by node cardinality and node-ID density; sparse cost scales with
node count and dense cost with the largest node ID, and **neither is ordered by compressed PBF bytes**.
v4's claim that "if `indonesia-220101` fits, every other file fits" is withdrawn. Instead:

- the ceiling is **enforced per file at run time** — working set is sampled during every file, and any
  file exceeding 50 % of machine RAM **fails the stage closed** rather than swapping;
- **node cardinality and maximum node ID are recorded per file** in the manifest, since those are the
  actual drivers of index size;
- the single frozen backend stays, because the measurement below shows the margin is large — but it is
  now a checked invariant per file, not an extrapolation from one file.

3.1 **Method.** Peak working set and peak commit are read from `GetProcessMemoryInfo` through `ctypes`,
    which adds no dependency (`psutil` is absent from this environment). The probe was validated against a
    deliberate 600 MB allocation before the gate run, so it is known to track allocation rather than
    silently returning a constant.

3.2 **What the memory measurement does and does not establish.** Working set peaked at 6.58 GB *during
    node reading*, then fell to a stable 3.7 GB for the whole way pass — the index is fully built before
    the first way is emitted, so within a file the peak is structural rather than a rising trend. That
    gives a **2.6× margin** against the 17.0 GB ceiling **on this file**. It does not order the other 35
    files, for the reason in round-4 #4, which is why §3's per-file runtime enforcement exists.

3.3 **The corpus projection is an extrapolation, and is labelled as one.** It applies Indonesia's measured
    30,174 ways/MB to all 8641 MB. Way density varies by region, so 260.7 M ways is an estimate; the
    22.5-minute largest-file figure and the 6.58 GB ceiling are direct measurements and are not.

### 4. Deduplication within an origin

4.1 Key `(origin, osm_type, osm_id)`.

4.2 **Group members must agree on `version`, `timestamp` and the full canonical tag map** before any
    geometry comparison (round-2 #6/r1 #8). Disagreement fails closed and is reported.

4.3 **Exact ordered node-reference equality AND exact resolved-coordinate equality — no reconstruction**
    (round-3 #2, round-4 #2). Two records of the same way at the same version must carry **identical
    ordered node-reference lists** *and* **identical resolved coordinate sequences**; any mismatch **fails
    preflight**, reported with both sequences, the conflicting node IDs and coordinates, the regions
    involved, and their header timestamps.

    **Node-reference equality alone is not geometric equality** (round-4 #2). A referenced node can be
    *moved* between two regional build cutoffs without changing the containing way's version, timestamp,
    tags or node-reference list — the way object is untouched because only the node changed. v4 would then
    have seen two "identical" ways and silently chosen between differing coordinate sequences. Coordinates
    are already resolved and retained per §1.3, so the stronger check costs nothing extra to obtain.

    v3 tried to reconcile fragments into a "unique consistent global sequence". That was solving a problem
    that does not exist and could produce a way present in no source. Geofabrik documents that **ways
    crossing an extract boundary are kept complete**, so a fragment pair should not arise; if one does, it
    means the sources disagree, and the correct response is to stop and report, not to synthesise a
    geometry. The v3 rule was also undefined in practice — "unique consistent sequence" has no meaning for
    repeated nodes, closed-ring rotations, reversals, or competing supersequences.

    **Measured, not assumed** (this rule is load-bearing, and the guarantee behind it is external). Node
    references need no location index, so all seven neighbouring region pairs at origin 2020 were compared
    directly:

    | pair | shared IDs | node-seq mismatches | version mismatches |
    |---|---|---|---|
    | argentina × bolivia | 871 | 0 | 0 |
    | argentina × paraguay | 19,825 | 0 | 0 |
    | bolivia × paraguay | 266 | 0 | 0 |
    | bolivia × peru | 471 | 0 | 0 |
    | norte × nordeste | 8,105 | 0 | 0 |
    | norte × centro-oeste | 2,578 | 0 | 0 |
    | nordeste × centro-oeste | 253 | 0 | 0 |
    | **total** | **32,369** | **0** | **0** |

    Every one of 32,369 cross-region duplicates is byte-identical in its ordered node references, and
    v3's reconciliation machinery would never have executed a single time on them — it was pure risk
    surface.

    **This is evidence for the tested subset only** (round-4 #9). It covers origin 2020 and land-border
    pairs, at node-reference level. It does **not** cover origins 2021 and 2022, non-adjacent overlaps, or
    the coordinate-equality check added above — which is precisely the failure mode #2 identifies, and
    which this measurement could not have detected. v4 concluded the rule "will not halt this corpus" from
    it; that was an overclaim and is withdrawn.

4.6 **The full preflight is an authorisation gate, not later proof** (round-4 #9). The complete
    duplicate-group preflight — all three origins, every real region overlap, version + timestamp + tag
    map + node references + resolved coordinates — **must pass before the corpus run is authorised**,
    alongside §3's production-path gate. Preflight needs no location index for the reference check and
    only resolved coordinates for the geometry check, so it is cheap relative to the stage it guards.

4.4 **Assert unique dedup keys**, not zero coincident length — distinct IDs may legitimately trace
    coincident roads. Distinct-ID coincidence is reported separately, never merged.

4.5 **Every duplicate group is preflighted** over all real overlaps **before** cache construction
    (round-2 #7): version, timestamp, tag map, and ordered node-reference equality. A group that would fail
    §4.2 or §4.3 must fail during preflight, so an unhandled case cannot halt the run after hours of
    parsing.

### 5. Published layout and commit protocol

**A hash-linked DAG, in which no node is reachable until its children validate** (round-3 #5). v3 named a
manifest hierarchy but bound none of its edges, so the "hierarchy" carried no integrity claim.

```
part files ──► shard manifest ──► region manifest ──► origin dataset manifest ──┐
                                                                                ├─► stage manifest ◄── pointer
identity edges + spatial index + coverage margins + preflight report ───────────┘
```

5.1 **Every manifest names the digest of every child**, plus the schema digest and the cache key (§8) it
    was built under. A parent is written only after each child's recorded digest is recomputed and matches.
    The stage manifest additionally binds **all three origin datasets**, the lineage artifacts, the
    duplicate-group preflight report and the coverage margins — v3 bound only regions, so a consumer could
    read a stage that had no lineage.

5.2 **Publication of any manifest** — same-directory temporary file → write → **checked
    `FlushFileBuffers`** → atomic replace via `ReplaceFileW` → revalidate. This reuses
    `forecast/_atomic_publish.py`, which already encodes the `ReplaceFileW` state table (1175
    retry-from-staging, 1176 retry from staging not backup, 1177 exposed → roll forward, any other error →
    fail closed).

    **Three defects in that helper must be fixed before it is relied on** (round-4 #7, #8). They were
    verified by reading the code, not taken on the reviewer's word:

    - **`FlushFileBuffers` is never called anywhere.** v4's own description of this step was aspirational.
      Staging contents must be flushed, with the return value checked, *before* the replace.
    - **`assert_local_non_reparse` is never called by `publish_container`.** It exists, and it is exercised
      only by `forecast/tests/test_atomic_publish.py`. Production publication calls `assert_same_volume`
      alone. So the plan's claim that the helper "rejects OneDrive" was false as a statement about
      behaviour: publication must itself require a named local-NTFS root, validate the **full ancestor
      chain** for reparse points, and verify the volume/filesystem type.
    - **`recover()` returns prose, and `classify()` only maps a *returned* `winerror`.** A kill or power
      loss mid-`ReplaceFileW` produces no error code at all, so nothing classifies the on-disk state at
      restart.

    **Startup classifier (new, and executable).** Before any read or publish, the three paths
    (destination, staging, backup) are inspected by **digest and file identity** against the manifest DAG,
    and the outcome is decided deterministically: complete → proceed; a recognised intermediate
    arrangement → **roll forward** to the replacement, never back; anything unrecognised → **fail closed**
    and report. This is the piece v4 was missing entirely — it handled errors that are returned, not
    termination that returns nothing.

    **On the directory flush:** the POSIX recipe ends with an `fsync` on the containing directory. Windows
    has no directory-fsync equivalent and `ReplaceFileW` is the atomicity primitive instead, so the plan
    states the platform reality rather than copying a step that cannot be performed here. The reviewer
    accepted this as defensible **conditional on** the durability claim staying narrow and the startup
    validation above existing. The claim is therefore exactly: **atomic visibility, with file contents
    flushed** — and explicitly *not* durability of the NTFS namespace change across sudden power loss,
    which can still be lost or reordered. The startup classifier is what makes that survivable.

5.3 **Validation order:** bottom-up on write (children verified before a parent is published), and
    **top-down revalidation of the entire DAG from the stage manifest** immediately before the consumer
    pointer is replaced. A pointer never advances to a DAG that has not just been walked in full.

5.4 **Fixed lock order, always: cache-key lock, then publication lock** (round-2 #15). Artifacts live under
    their content-addressed key; the shared consumer pointer updates under the separate publication lock.
    The order is fixed in one direction so two valid keys cannot deadlock, and it is asserted in code.

    **Locks are handle-held `LockFileEx` locks** (round-4 #8), which Windows releases when the owning
    process dies. A lock represented by a file's existence survives a crash and deadlocks every subsequent
    run until someone deletes it by hand — the failure mode is indistinguishable from a hung job.

5.5 **A manifest — never file existence — is the commit marker at every level**, so shards completed before
    a kill are not orphans. Per-`(origin, region)` outputs are **logical manifests** that may reference
    several part files, not "36 single parquets" (round-2 #14).

### 6. Lineage — identity edges only; spatial candidate generation belongs to Plan B

**Plan A no longer generates spatial candidates** (round-4 #5). v4 froze a 2000 m outer radius and a
0.5 % saturation criterion and claimed the result was either complete or refused. Both numbers are
scientific cutoffs: a site dominated by short-distance edges passes the 0.5 % test while a rare renumbered
or split road sits beyond 2 km unseen, and nothing is observed in the 2–5 km remainder of the extraction
guard. That is Plan A deciding what Plan B is allowed to look at — the same error round-2 #9 and round-3 #6
already flagged, surviving in a third form because I kept trying to make the cutoff *safe* instead of
removing it.

Plan A emits three things and no thresholds:

6.1 **Identity edges, unconditionally and at any distance.** Ways sharing an `osm_id` across two origins
    are linked regardless of separation. Identity is direct evidence and needs no radius; a road that
    moved 3 km is exactly the case a radius would have deleted.

6.2 **The normalised geometry itself, with a queryable spatial index** (per site window, per origin), so
    Plan B can generate spatial candidates at whatever radius and tolerance its science requires **without
    re-parsing any PBF** — which is Plan A's actual contract.

6.3 **Descriptive measurements on identity edges**, carrying no cutoff and implying no classification.

**Frozen identity-edge schema.** One row per `(site_id, origin_pair, osm_id)`, origins canonically ordered:

`site_id, origin_a, origin_b, osm_id, min_distance_m, hausdorff_m,
 iou_5, iou_10, iou_25, iou_50, cov_a_in_b_{5,10,25,50}, cov_b_in_a_{5,10,25,50}, degenerate_flag`

6.4 **Exact operator definitions** (round-4 #6 — v4 left these open):

    - **CRS**: one UTM zone per **site window**, from the window centroid. Symmetric by construction, so
      A→B and B→A agree. Never per-way.
    - **`min_distance_m`**: minimum distance between the two `LineString`s in that projection.
    - **`hausdorff_m`**: the **symmetric** Hausdorff distance, `max(directed(A,B), directed(B,A))`. v4 said
      "Hausdorff" without naming the variant, which is ambiguous.
    - **Buffers**: flat end cap, round join, **8 quadrant segments**, frozen — buffer geometry is
      parameter-dependent and the parameters must be part of the contract, not the library default.
    - **`iou_τ`**: `area(buf(A,τ) ∩ buf(B,τ)) / area(buf(A,τ) ∪ buf(B,τ))`, dimensionless.
    - **`cov_a_in_b_τ`**: `length(A ∩ buf(B,τ)) / length(A)`; `cov_b_in_a_τ` exchanges the roles. Both
      directions are emitted explicitly rather than implied.
    - **Degenerate geometry**: a way whose nodes are all coincident has zero length and zero buffer area.
      Such rows are emitted with **null metrics and `degenerate_flag` set** — never a division by zero and
      never a silently dropped row.
    - **Closed ways** participate as their ring traversal; lengths are perimeters; no area semantics.

6.5 **No components, no aggregates, no classification vocabulary.** Connected components, aggregate
    coverage and any `resolved` / `unresolved` judgement all require a candidate graph, which Plan A no
    longer builds. They belong to Plan B, with §6.2's index and geometry as their input. v4's aggregate
    formula was also under-keyed — components span three origins while `A` and `B` named no origin pair —
    and rather than patch a specification for a table Plan A should not be producing, the table is removed.

### 7. Snapshot provenance

Require the **authoritative PBF header field** (`osmosis_replication_timestamp`, else the documented
content timestamp, with precedence and a missing-field failure stated). Enforce
**`feature_max ≤ header_timestamp ≤ issue_date(T)`**, and validate the header against a nominal
archive-date window **derived from all 36 real headers** (round-2 #16) — a June PBF would otherwise satisfy
a bare `≤ 31 Dec T`. The feature maximum is recorded as an observation and is never authoritative: it
would have rejected **21 of 22** valid archives.

### 8. Cache identity and durability

8.1 **The key covers semantic inputs, not just code** (round-2 #12): every input PBF digest, the site
    manifest hash, the **exact window/mask geometry**, the shard-plan version, normalisation parameters,
    the auxiliary polygon inventory hash, parser configuration, and resolved library versions. A cached
    artifact built for different site windows must not validate.
8.2 **Dirty-tree hashing is scoped** to the parser, configuration, schema and dependency files that can
    affect the stage — not all uncommitted content, which would invalidate caches on an unrelated docs
    edit (round-2 #13).
8.3 Outputs flushed and hashed; cached outputs **rehashed before reuse**.

### 9. Extraction polygons

Geofabrik documents `.poly` as the **current** extract boundary; no contemporaneous polygon exists for a
2020–2022 archive. Current files are pinned as **clearly-labelled current-vintage** auxiliary artifacts,
a search for dated artifacts is recorded, and **historical source availability is marked UNKNOWN** rather
than certified from a current polygon — irrespective of any margin computed in §2.

### 10. Restart boundary and observability

10.1 **The whole input file is the smallest restart boundary** (round-3 #8). pyosmium exposes no durable
     input cursor, so a kill mid-file forces a full re-parse of that file; committed part files spare the
     rewriting but not the parsing. **Worst-case rework is therefore 22.5 minutes — measured, not
     estimated** — and the plan states this rather than implying shard manifests make the parser resumable.
     A resumable intermediate would be the alternative; at 22.5 minutes against a 2.26 h corpus it does not
     earn its own commit protocol.

10.2 **A progress journal, explicitly non-authoritative** (round-3 #10). Emitted periodically during the
     run: current file, node and way counts, rate, working set, free disk, and last committed manifest.
     Final per-file counts cannot distinguish a stalled index from disk exhaustion from machine suspension
     — and one such stall already cost a discarded 41,388-second data point in this session. **The journal
     is never a commit marker and is never read back as state**; §5's manifests remain the sole truth.

### 11. Provenance

Inputs rehashed before parsing against `static_archive_inventory.json`; mismatch fails closed. The manifest
records recomputed hashes, the inventory hash and weak-anchor disclaimer verbatim, the polygon inventory
with its vintage caveat, resolved library versions, per-file way and retention counts, the entry-gate
measurements against their frozen ceilings, the duplicate-group preflight result, lineage distributions and
identity-edge measurements, both coverage margins separately, per-file node cardinality and maximum
node ID, and output hashes.

## Key decisions & tradeoffs

- **A long-running job Josh launches, not a windowed one.** Three designs were distorted by treating the
  assistant's 6–11 minute background limit as a property of the problem. Checkpoints stay, for crashes.
- **Raw way stream over GDAL layers**, which dissolves the layer-loss, node-reference, lifecycle-tag and
  area-way findings rather than answering each separately.
- **Exact mask dispatch**, since no rectangle approximates these site sets (202×, 110× clustered).
- **One index backend, not two.** Measurement removed the file-backed branch and its durability contract.
- **Fail closed on node-reference OR coordinate disagreement rather than reconcile.** A synthesised way is
  worse than a halted run. Node references alone were not enough: a node can move without touching the way.
- **Plan A stopped generating spatial candidates entirely.** Three rounds running, the reviewer found Plan A
  bounding Plan B's science with a radius, then a wider radius, then a saturation test. The cutoff was never
  the problem; Plan A owning it was. Identity edges plus a spatial index give Plan B the freedom instead.
- **A 5000 m extraction guard**, conservative by construction, with the *processing-mask* margin emitted as
  the check — kept strictly separate from the current-polygon margin, which proves nothing.

## Risks / open questions

- **The corpus projection rests on one file's way density** (§3.3). If some region is far denser per MB
  than Indonesia, 2.26 h is optimistic — though the 6 h ceiling absorbs a 2.6× error, and the per-file
  wall-clock ceiling still gates each file individually.
- **14 of 36 extracts remain unprofiled** — though the largest is now fully measured, which is the binding
  case for both the memory ceiling and the restart boundary.
- **The duplicate-group preflight may find unequal node references or coordinates**, which blocks rather
  than reconciles. Measured at zero across 32,369 cross-region duplicates at origin 2020 — but at
  node-reference level only, on land-border pairs only, at one origin. The coordinate check that §4.3 now
  requires has **never been run**, and it is the check most likely to fire.
- **The 5000 m guard is chosen, not derived** — conservative, but Plan C could in principle exceed it, and
  the emitted processing-mask margins are the check.
- **pyosmium 4.3.1 is newly added** to the environment and exercised only by the measurements above.
- **The production-path gate (§3) has not been run**, because the production path does not exist yet. Every
  runtime number here is a parser floor. If serialisation, masking and publication cost more than parsing,
  the 6 h corpus ceiling is the thing that will fire.
- **`forecast/_atomic_publish.py` needs three fixes before use** (§5.2) — flush, the uncalled locality
  check, and an executable startup classifier. Until then the commit protocol is designed but not backed.

## Out of scope

- Tier selection, the vintage decision, the cross-tab — **Plan B**.
- Features, projections, rasterisation, terrain, and any road-centreline or area semantics for closed ways
  — **Plan C**.
- Anything touching `lossyear`, the sealed worker, or the 12-site v11 path.
- Re-acquiring or modifying the certified archives.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: the retain-predicate matching its reference
   predicate on fixtures containing `was:highway` and `area:highway` (retained) and `not:highway`,
   `source:highway`, `historic:highway` (excluded), and **failing closed on an unknown `*:highway`
   namespace**; closed and `area:highway` ways stored as `LineString` with `is_closed` set; a way with one
   invalid node location failing the stage closed; exact-mask dispatch emitting a way to every window it
   touches and none it does not; **node-reference inequality failing preflight**, and **equal node
   references with unequal resolved coordinates ALSO failing preflight**; group rejection on tag or
   timestamp disagreement; unique-dedup-key assertion passing where distinct IDs trace coincident roads;
   header-timestamp precedence with `feature_max <= header <= issue_date` and a missing-field failure;
   identity edges emitted at arbitrary separation; degenerate zero-length geometry emitting null metrics
   and a flag rather than dividing by zero; **no** classification vocabulary anywhere in the output;
   per-file memory ceiling failing the stage closed when exceeded; DAG validation rejecting a parent whose
   child digest was altered; pointer replacement refused when revalidation fails; lock order asserted;
   **`LockFileEx` locks released by killing the owning process**; `publish_container` refusing a reparse
   or non-NTFS ancestor; **the startup classifier rolling forward from each recognised intermediate
   arrangement and failing closed on an unrecognised one**, exercised by killing a publish mid-flight;
   manifest-as-commit at shard, region and stage level under a simulated kill; cache key rejecting an
   artifact built for different site windows; dirty-tree scoping ignoring an unrelated docs edit.
2. **The §3 gate re-run through the production parser-to-committed-region path**, every row passing, its
   immutable measurement artifact recorded. The parser-only numbers already in §3 do not satisfy this.
3. **The full three-origin duplicate-group preflight** over every real region overlap, including the
   resolved-coordinate check — an authorisation gate, run before the corpus run, not proof gathered after.
4. The published origin-level datasets with `source_regions[]`, and the shard/region/origin/stage manifests
   with their digest links verified end to end.
5. The identity-edge table with its frozen operator parameters, and the per-site spatial index Plan B
   consumes.
6. Per-site processing-mask margins in metres, reported separately from current-polygon margins.

Josh runs the proof. Reviewer and builder claims are advisory.
