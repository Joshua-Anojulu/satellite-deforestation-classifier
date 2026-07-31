---
review_provenance:
  schema_version: 2
  status: in-progress
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
    - round: 6
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: a325021d05e30d94f038ecb94f9a5c77c1046ce36dc8f62da420868d14c8a165
      verdict: REVISE
    - round: 7
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 2ee7ac8fb410df497ede04be658db8ed1f6c6a6cd3507c2cdaaafc2aec6d2894
      verdict: REVISE
    - round: 8
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: adb89de3c6749ca99f46c55d1d2f16cd58f6210e05c7eb8ee4ffa4d1551d75cf
      verdict: REVISE
    - round: 9
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: 51b2b12e89b1ed3cd5198d96ad3c26a3fd0ddc1d379323aec2e092db0b79bb74
      verdict: REVISE
    - round: 10
      schema_version: 2
      reviewer: codex
      model: gpt-5.6-sol
      cli: codex-cli/0.145.0
      grounding: repo
      qualifying: true
      scope: "section 5 only"
      session: 019fb141-c01f-7c23-a6ba-537d2d2bfb75
      body_sha256: de6696c132d1460047c1d829a0a276019521f91b815d40173189ab7f3103dd77
      verdict: REVISE
  loop_2_note: "rounds 1-6 exhausted both caps and resolved deadlocked at body a325021d; v7 applied all
    four open findings unreviewed; a second loop with fresh caps opens at round 7"
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan A: OSM normalisation infrastructure for Specification W
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–5, a preflight, and three measurements_

> **Position.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md` (`reviewed-unapproved`).
> **Plan B** (vintage audit) and **Plan C** (feature extraction) consume this output and are unwritten.

## Goal

Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned road-network
cache that Plan B and Plan C consume without re-parsing. **No scientific decisions**: no tier selection,
no vintage position, no classification thresholds.

## What is measured, and what a previous version of this plan got wrong

**Three categories, kept separate** (round-6 #5): *file observations* measured directly on
`indonesia-220101`; *corpus extrapolations* computed from them; and *unmeasured* quantities. v6's claim
that "every runtime number is measured on the worst-case file" was false — the corpus figures are
extrapolations, pass 2 has never run, and the production path does not exist. The estimates the
observations replace were wrong in both directions and are withdrawn.

| quantity | v3 claimed | **measured** |
|---|---|---|
| `indonesia-220101` pipeline, geometry sampled | unmeasured; "2.7 h corpus, way stream only" | **18.3 min** (1433 MB) |
| `indonesia-220101` pipeline, **§1.5 full validation** | — | **22.5 min** (1348 s) |
| ways in that file | ~18 M inferred | **43,250,208** (30,174 ways/MB, v3 was 2.35× low) |
| throughput, fully validating | 12,658 ways/s | **32,085 ways/s** incl. node decoding and index build |
| geometry availability | unknown | **4,839,062 / 4,839,062 = 100 %** of retained ways |
| ways with a missing or invalid node location | unknown | **0** |
| peak working set | unmeasured | **6.58 GB = 19.3 %** of the machine's 34.1 GB |
| peak commit | unmeasured | **8.22 GB** |
| corpus size actually parsed | "9.42 GB" | **8.64 GB** — 9.42 GB is the whole static archive, not its OSM subset |
| corpus projection, **one pass** | 2.7 h | **≈ 260.7 M ways, ≈ 2.26 h** (§2.2 needs two) |

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

### 1. One raw way stream per file per pass — no GDAL layers

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

    **The census is COMPLETE: all 36 extracts, 34,764,774 retained ways, 18 distinct `:highway` keys.**
    The exact **set difference** — ways a suffix predicate retains that the frozen predicate does not —
    is **2,740**. That difference is the only population whose retention actually changes; a way carrying
    `source:highway` *and* `highway` is retained either way. (My first attempt at this accounting counted
    the latter and would have overstated the problem.)

    | key | corpus | in set difference | disposition |
    |---|---|---|---|
    | `highway` | — | — | **retain** (the road tag itself) |
    | `abandoned:highway` | 18,383 | 0 | **retain** |
    | `area:highway` | 2,444 | 2,403 | **retain** — road areas |
    | `disused:highway` | 1,330 | 0 | **retain** |
    | `construction:highway` | 1,249 | 0 | **retain** |
    | `proposed:highway` | 1,069 | 0 | **retain** |
    | `demolished:highway` | 345 | 0 | **retain** |
    | `destroyed:highway` | 338 | **278** | **retain** |
    | `was:highway` | 31 | 15 | **retain** |
    | `former:highway` | 25 | **25** | **retain** |
    | `razed:highway` | 20 | 0 | **retain** |
    | `removed:highway` | 3 | **3** | **retain** |
    | `disabled:highway` | 3 | **3** | **retain** |
    | `collapsed:highway` | 3 | 0 | **retain** |
    | `source:highway` | 3,986 | 0 | exclude — provenance metadata |
    | `not:highway` | 308 | 13 | exclude — negative assertion |
    | `indoor:highway` | 86 | 0 | exclude — indoor navigation, not a carriageway |
    | `note:highway` | 9 | 0 | exclude — free-text note |
    | `historic:highway` | 3 | 0 | **retain** — ambiguous, and excluding it is irreversible (round-5 #6) |

    **Freezing this table from a partial census would have silently dropped 309 ways.** v6–v9 froze it from
    the first five extracts and were missing `destroyed:`, `former:`, `removed:` and `disabled:` — all four
    standard lifecycle prefixes, all four appearing in the set difference. The plan asserted that partial
    coverage was safe because the run-time assertion would catch anything new. That was wrong twice over:
    the census found real keys the table lacked, and the assertion as specified could not have caught three
    of them (below).

    **The assertion is on KEY MEMBERSHIP, not on predicate equality** (round-9 #7). Comparing the frozen
    predicate against a reference predicate is a comparison of two **booleans**, so a way carrying
    `mystery:highway` **and** ordinary `highway` satisfies both and the unknown namespace passes
    undetected. This is not hypothetical: `indoor:highway` (86), `note:highway` (9) and
    `collapsed:highway` (3) occur **only** on ways that also carry `highway`, so they never enter the set
    difference and a boolean-equality check would never see them. The parser therefore asserts directly
    that **every observed `*:highway` key is present in the disposition table above**, independent of any
    predicate, and **fails closed** on a key that is not — including on a way co-tagged with ordinary
    `highway`.

    Keys are frozen **by this table**, not by a suffix rule: a suffix rule silently absorbs any future
    `<anything>:highway` namespace, including the metadata ones above.

    **Exclusion is limited to unambiguously non-road namespaces** (round-5 #6). `historic:highway` is
    documented as inconsistently used and can mark a previously valid carriageway, so excluding it is
    exactly the kind of scientific call Plan A's Goal forbids — and it is irreversible, since the record
    never reaches Plan B. Only provenance metadata (`source:`, `note:`), a negative assertion (`not:`) and
    a non-carriageway navigation namespace (`indoor:`) are dropped.

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
    list, fails the stage closed** with its `osm_id` reported. The measured count on the largest-by-bytes
    tested file is
    recorded in §3 — this is a checked invariant, not an assumption.

### 2. Site dispatch, and identity closure — TWO passes, not one

Round-2 #2: the nine Indonesian site boxes total 0.495 deg² inside a **99.83 deg² envelope — 202×
oversized**, and clustering only reaches 110×, so no rectangle works. Each way is tested against the
**exact set of site window polygons** as it streams, and emitted to every window it touches. No envelope,
no `if it overruns` trigger that a killed process could never record.

2.1 **Extraction guard (frozen):** a site window is its site box buffered by **5000 m**, geodesically.

2.2 **Window dispatch alone cannot deliver §6.1's identity edges, and v5 claimed it could**
    (round-5 #1). This was a flat contradiction inside v5: §2 discards every way outside the window, while
    §6.1 promised identity edges "at any distance". A way that moved 8 km between origins is dropped by the
    first pass and can never appear in the join. Worse, v5's proof line ("identity edges emitted at
    arbitrary separation") would have **passed on synthetic fixtures while production silently omitted
    exactly the cases the edge exists to catch** — a green test over a hole.

    **Identity closure — keyed by `(site_id, osm_id)`, not by `osm_id`** (round-6 #1). v6 made `S` a bare
    set of IDs, which cannot express the thing the flag is for: a way may be **inside** site A's window and
    **outside** site B's. A single `outside_window` boolean on the record is therefore meaningless — it is
    a property of the (site, way) pair, not of the way.

    - **Pass 1 — site relevance.** Stream all 36 extracts, apply the §1.2 retain-predicate and window
      dispatch. Emit region checkpoints, and accumulate the **closure table `S = {(site_id, osm_id)}`** —
      every way touching a given site window in any origin, associated with that exact site. `S` is
      **published as a first-class artifact bound into the manifest DAG** (§5.1), so pass 2's inputs are
      versioned and reproducible rather than being incidental process state.
    - **Pass 2 — closure.** Stream all 36 extracts again. For each `(site_id, osm_id) ∈ S`, retain that
      way **for that site** regardless of window intersection. A counterpart is associated only with the
      sites that actually claim it, never with all sites.

    **Three independent flags, because v6's single boolean conflated three different facts** (round-6 #1):

    | flag | meaning |
    |---|---|
    | `intersects_window` | the geometry actually meets this site's mask |
    | `selected_by_predicate` | §1.2 retained it on its own tags |
    | `closure_only` | present solely to complete an identity edge |

    **`closure_only` is DERIVED, and the road supply needs both flags** (round-7 #2):

    - `closure_only := NOT (intersects_window AND selected_by_predicate)`
    - **Plan C's road supply and all coverage statistics are defined on
      `intersects_window AND selected_by_predicate`** — not on `intersects_window` alone, which v7 used and
      which would have admitted a tag-changed record that is inside the window but is no longer a road.

    A tag-changed counterpart inside the window therefore carries `intersects_window = true`,
    `selected_by_predicate = false`, **and `closure_only = true`** — all three at once. v7's proof line
    said such a record should carry `intersects_window = true` "rather than being stamped closure-only",
    which contradicted the semantics; it is both, and the two flags answer different questions.

    **Suppression is keyed by `(site_id, origin, source_region, osm_id)` — NOT by `(site_id, osm_id)`**
    (round-7 #1). v7's rule was self-defeating and would have made pass 2 emit **nothing at all**: every
    pair in `S` is there *because pass 1 emitted it in at least one origin*, so suppressing on that pair
    suppresses the other-origin counterpart pass 2 exists to recover. The closure would have been silently
    inert and the identity edges simply absent — with no error anywhere.

    Only the **exact record** pass 1 already wrote is skipped. Every missing origin/region counterpart
    selected through `S` is still emitted. The suppression key must therefore carry origin and region,
    which are precisely the dimensions the closure operates across.

    Two passes is the honest cost of the promise. Retaining every highway way corpus-wide instead would
    avoid the second pass but multiply the output by roughly an order of magnitude, and disk is already
    constrained on this machine.

2.3 **The completeness domain is frozen and emitted, because an index over a finite window is not
    complete for every anchor** (round-5 #2). v5 told Plan B it was free to choose any radius, which a
    5 km window cannot honour: an anchor near the window edge has neighbours outside it.

    - **Anchor domain (frozen): geometry CLIPPED to the site box** (round-6 #2). v6 said "any anchor
      inside the site box", which is undefined for a `LineString` — a way merely *intersecting* the box can
      run far outside it, and its distant portion has neighbours beyond the mask. The anchor is therefore
      the way's geometry **intersected with the site box**, so every point of every anchor is inside the
      box by construction.

      **Clipping is not closed over `LineString`, and the order is frozen** (round-7 #5): intersecting a
      winding way with a box can yield a `MultiLineString`, a point-only touch, a geometry collection, or
      empty. **Project first into the frozen site UTM, intersect there**, then retain **every
      positive-length lineal component** as the anchor. Point-only and empty intersections are excluded and
      flagged, never silently dropped. Without this, two conforming Plan B implementations would generate
      different candidate sets from the same input.
    - **`max_processing_radius_m = inf distance(site_box, complement(mask))`**, computed from the realised
      mask — the largest radius for which a query centred anywhere in the box cannot reach outside the
      data Plan A retained. Emitted per site.
    - **It measures Plan A's own processing boundary and nothing more** (round-8 #2). v8 named it
      `max_processing_radius_m`, claiming a source completeness the plan cannot support: §9 leaves historical
      extract coverage **UNKNOWN**, so this value proves only that *Plan A added no truncation beyond the
      mask*. Completeness stays conditional on separately proven historical source coverage, and the name
      no longer implies otherwise.
    - **The metric is stated, not assumed compatible.** It is computed in the **same per-site UTM
      projection §6.4 freezes**, which is the projection Plan B measures distance in. If Plan B ever
      measures in a different metric, the radius must be re-derived as a conservative lower bound rather
      than reused — a completeness guarantee expressed in one metric is not a guarantee in another.
    - **Closure-only endpoints are excluded from Plan B's spatial candidate domain** (round-6 #2). They are
      not a sampled neighbourhood: they exist only where an identity edge demanded them, so treating them
      as spatial candidates would silently bias candidate generation toward ways that happen to have
      identity counterparts.
    - **Plans B and C must stay inside `max_processing_radius_m` or reopen Plan A.** That is a stated
      contract, not a hope. v5's Risks section admitted Plan C "could in principle exceed" the guard while
      §2 claimed neither plan could need a discarded road; the admission was right and the claim is
      withdrawn.
    - **No bespoke index format is frozen.** Plan A publishes GeoParquet; Plan B builds its own ephemeral
      spatial index from it.

**Two different margins, which v3 conflated** (round-3 #9):

- **Processing-mask margin** — realised metres between each site box and the boundary of the mask Plan A
  actually applied. Computed from our own geometry, verifiable, emitted per site.
- **Current-polygon margin** — metres between the site window and the *current-vintage* Geofabrik `.poly`.
  Auxiliary only. It **cannot** prove what the 2020–2022 extract boundary was.

`roads_source_available` stays **UNKNOWN** regardless of either margin (§9). A large current-polygon margin
is not evidence and is never reported as if it were.

### 3. The node-location index, and the entry gate

Node references alone are not geometry; pyosmium needs a node-location index. **Frozen: `flex_mem`, the
sole backend.** v3 planned a per-file choice between `flex_mem` and an on-disk `sparse_file_array`; the
measurement below shows the in-memory index fits the largest-by-bytes tested file with room to spare, so the file-backed
branch is **deleted**, and with it round-3 #4's entire durability problem — there is no index file to leave
behind on a kill, no temporary-directory capacity check, and no fresh-versus-reused index question.

**Entry gate (round-3 #3) — frozen pass conditions, and the measurement against them.** v3 named a file
but no criterion, which is not a gate.

| condition | ceiling | measured on `indonesia-220101`, fully validating | |
|---|---|---|---|
| `indonesia-220101` **parser** wall-clock, pass 1 | ≤ 45 min | **22.5 min** | PASS |
| projected corpus wall-clock, **both passes** (§2.2) | ≤ 12 h | *≈ 4.5 h — EXTRAPOLATED, not measured* | **NOT ASSESSED** |
| peak commit charge (`PrivateUsage`) | ≤ 50 % of machine RAM (17.0 GB) | **8.22 GB (24.1 %)** — pass 1 only | PASS, pass 1 |
| peak commit charge **with `S` resident** (pass 2) | ≤ 17.0 GB | *never measured* | **NOT ASSESSED** |
| peak working set *(observability only)* | — | 6.58 GB | not a gate |
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

- the ceiling is **enforced on commit charge, not working set** (round-6 #6). Sampling `WorkingSetSize`
  cannot detect the failure it was meant to prevent: working set counts *resident* pages, so when Windows
  begins paging the process out the number **falls**. A swapping run would have looked healthier, not
  worse. Enforcement is on **`PrivateUsage`** (`PROCESS_MEMORY_COUNTERS_EX`);
- **a Job Object memory limit does not terminate anything by itself, and v7 claimed it did**
  (round-7 #4). `JOB_OBJECT_LIMIT_PROCESS_MEMORY` makes an over-limit *allocation fail*; it does not kill
  the process. v7 also said the mechanism "exists and is exercised" in
  `forecast/sandbox_process.py` — that helper sets `LimitFlags = 0x2000 | 0x400` (kill-on-close,
  die-on-unhandled-exception) and **no memory limit at all**; the struct's `ProcessMemoryLimit` and
  `JobMemoryLimit` fields are never assigned. Job Objects are exercised there for process containment, a
  different purpose;
- **the frozen design is a supervised child, and the notification must be the guaranteed one**
  (round-8 #9). The parsing work runs in a child assigned to a job carrying
  **`JOB_OBJECT_LIMIT_JOB_MEMORY`** — job-wide, so the node index *and* the resident `S` count against one
  total. But v8 relied on the supervisor being *told* about the breach, and Microsoft documents ordinary
  completion-port messages such as `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT` as **not guaranteed to be delivered**,
  so "the supervisor calls `TerminateJobObject` on every breach" was not a promise v8 could keep.
  Instead a **`JobObjectNotificationLimitInformation` soft threshold of exactly 14.0 GB is registered before
  the child starts** — that notification is guaranteed, unlike the completion-port message — and the
  supervisor terminates on it. 14.0 GB is the frozen authorisation ceiling; 17.0 GB remains the hard limit
  and is a backstop only. v9 said merely "below 17 GB", which froze nothing (round-9 #6).
  **Allocation failure and abnormal child exit are both treated as stage failure**, so the hard limit
  remains a backstop rather than the detection mechanism. `sandbox_process.py` already binds
  `TerminateJobObject`, so the call exists even though no memory limit does;
- working set is retained as an **observability metric only** — useful in the §10.2 journal, never a gate;
- **node cardinality and maximum node ID are recorded per file** in the manifest, since those are the
  actual drivers of index size;
- the single frozen backend stays, because the measurement below shows the margin is large — but it is
  now a checked invariant per file, not an extrapolation from one file.

3.1 **Method.** Peak working set and peak commit are read from `GetProcessMemoryInfo` through `ctypes`,
    which adds no dependency (`psutil` is absent from this environment). The probe was validated against a
    deliberate 600 MB allocation before the gate run, so it is known to track allocation rather than
    silently returning a constant.

3.2 **What the memory measurement does and does not establish.** Commit charge peaked at **8.22 GB** on
    `indonesia-220101`, giving a **2.07× margin** against the 17.0 GB ceiling **on that one file**.
    (Working set peaked at 6.58 GB and then fell to ~3.7 GB for the way pass — retained here as
    observability only, since §3 demoted it from the gate; v7 still computed its margin from it, which
    round-7 #6 caught.) 8.22 GB is a **measurement, not a ceiling** — the ceiling is 17.0 GB, enforced.
    None of this orders the other 35 files, which is why §3's per-file enforcement exists.

3.3 **The corpus projection is an extrapolation, and is labelled as one.** It applies Indonesia's measured
    30,174 ways/MB to all 8641 MB. Way density varies by region, so 260.7 M ways is an estimate; the
    22.5-minute figure and the 8.22 GB peak commit are direct measurements of one file and are not.

### 4. Deduplication within an origin

4.1 Key `(origin, osm_type, osm_id)`.

    **Site membership and the §2.2 flags are per-site and would not survive this key** (round-8 #3).
    Deduplication collapses regional copies into one record per `(origin, osm_type, osm_id)`, and the
    published origin dataset names only `source_regions[]` — so a single-origin way has nowhere to carry
    which sites contain it, and identity edges cannot supply it either. Plan A therefore publishes a
    **manifest-bound membership table** keyed `(site_id, origin, osm_type, osm_id)` carrying
    `intersects_window`, `selected_by_predicate` and `closure_only`. It is a first-class DAG node (§5.1),
    not something a consumer is expected to re-derive.

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

4.6 **Preflight runs from committed region checkpoints — it cannot precede them** (round-5 #3). v5 called
    the coordinate preflight cheap because coordinates are "already retained per §1.3". They are retained
    only *after* the node index and parser have produced region records, so running it before the corpus
    run would require its own full node-and-way pass — the opposite of cheap. The gate ordering was
    simply wrong, and the fix is to reorder rather than to re-cost it:

    | stage | gated by |
    |---|---|
    | 1. Pass 1 parsing → region checkpoints | §3's production-path gate, measured on the largest-by-bytes file |
    | 2. **Pass 2 gate** — re-measured with the real committed `S` resident, on **the file with pass 1's maximum observed commit charge**, not the largest by bytes (round-7 #6) | pass 1 committed; commit ceiling re-verified |
    | 3. Pass 2 closure → `closure_only` records | the pass-2 gate passing |
    | 4. **Duplicate-group preflight** (step 4), reading committed checkpoints only | passes 1–2 committed |
    | 5. Deduplication and origin-level publication | **preflight clean** |

    Preflight at step 4 reads Parquet, never a PBF, so it genuinely is cheap — but only because it now
    runs after the parse instead of before it. It covers all three origins and every real region overlap:
    version, timestamp, tag map, node references, and resolved coordinates. **A dirty preflight blocks
    publication**, which is the property v5 wanted; it does not block parsing, which it never could.

### 5. Published layout and commit protocol

**A hash-linked DAG, in which no node is reachable until its children validate** (round-3 #5). v3 named a
manifest hierarchy but bound none of its edges, so the "hierarchy" carried no integrity claim.

```
part files ──► shard manifest ──► region manifest ──► origin dataset manifest ──┐
                                                                                ├─► stage manifest ◄── pointer
identity edges + GeoParquet geometry + coverage margins + preflight report ─────┘
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

    **Startup classifier — the complete state table** (round-5 #4). v5 said "a recognised intermediate
    arrangement → roll forward", which names a requirement and specifies nothing. That is the same failure
    as v3's "unique consistent global sequence": a phrase standing where a decision procedure belongs.

    Let **D** = destination, **S** = staging, **B** = backup, and let `d_old` / `d_new` be the digests the
    manifest DAG expects before and after this publish. Classification compares **digest and file
    identity**, never mere existence:

    **Transaction files live in a dedicated same-volume directory, keyed by a hash of the target**
    (round-10 #3). Target-derived *suffixes* are enumerable but not collision-free: a legitimate artifact
    named `foo.__stg` occupies exactly the staging path of target `foo`, so recovery for `foo` could
    classify or delete an unrelated file. Frozen instead, per published directory:

    ```
    <dir>/.__txn/<sha256(canonical target path)>/{staging, backup, intent}
    ```

    - the `.__txn` directory is **enumerable** — recovery scans it with no prior knowledge, which is what
      round-9 #4 required
    - the key is **collision-resistant** and derived from the canonical target path, so no real artifact
      name can occupy a transaction slot
    - it is on the **same volume** as the destination, so `ReplaceFileW` and `MoveFileExW` remain valid

    **The nonce lives ONLY in the intent** (round-10 #2). v10 put it in staging *content* as well — which
    is unworkable, because `ReplaceFileW`/`MoveFileExW` publish staging's bytes **unchanged**: a per-run
    nonce would either change `d_new` on every run, destroying deterministic manifests and equal-digest
    reuse, or leave staging's digest disagreeing with the declared `d_new`. Staging is authenticated by
    **its recorded file ID plus `d_new`**, never by embedded content.

    **The intent records both identities** (round-10 #4). v10 dropped the destination's file ID when the
    fields were rewritten, leaving "verified B" undefined — the classifier claimed identity comparison with
    nothing to compare against. The intent contains: target path, `d_old`, `d_new`, **staging's file ID**,
    **the destination's pre-mutation file ID**, and the nonce.

    **`B` is authenticated by that recorded pre-mutation identity**: after a successful `ReplaceFileW`, the
    backup is the file that *was* the destination, so a valid `B` has digest `d_old` **and** the recorded
    pre-mutation file ID. Anything else is unverified.

    **Frozen order, entirely under the §5.4 locks:**

    1. recover first — see the no-op rule below
    2. create `staging` with `CREATE_NEW`, write, **flush**, read back its file ID
    3. write `intent` with both identities, **flush**
    4. mutate `D`
    5. clean up in the frozen order `S → B → intent`

    A crash between 2 and 3 leaves staging with no intent — an enumerable orphan, safe to delete **only**
    because without an intent nothing has touched `D`.

    **The equal-digest no-op runs AFTER recovery, not before it** (round-10 #5). v10 decided it first, so a
    tree with `D = d_new` but stale remnants would return success without cleaning them, and the next
    operation on that target would then collide with `CREATE_NEW`. The no-op is permitted **only** when
    intent, `S` and `B` are all absent **and** the DAG and pointer validate; otherwise recovery runs first.

    | # | intent | D | S | B | interpretation | action |
    |---|---|---|---|---|---|---|
    | orphan | absent | any valid | valid-for-target | **absent** | crash before intent | delete S |
    | init | present | absent | `d_new` | absent | first publication | **`MoveFileExW(S → D)`** |
    | 1 | absent | `d_new` | absent | absent | complete | none |
    | 1c | present | `d_new` | absent | absent | complete; intent pending | delete intent |
    | 2 | present | `d_new` | `d_new` | verified `d_old` | replaced; temporaries pending | delete S, B, intent |
    | 2b | present | `d_new` | absent | verified `d_old` | replaced; B and intent pending | delete B, then intent |
    | 4 | present | `d_old` | `d_new` | absent | not started | `ReplaceFileW(D, S, B)` |
    | 5 | present | `d_old` | `d_new` | verified `d_old` | backup taken, replace not done | `ReplaceFileW(D, S, B)` |
    | 6 | present | absent | `d_new` | absent **or** verified `d_old` | D unlinked; replacement verified | **`MoveFileExW(S → D)`**, then B, then intent |
    | 7 | present | absent | absent | verified `d_old` | destination lost, no replacement | **fail closed**; operator restores from B |
    | 8 | any other combination, or ANY unverified identity | | | | unrecognised | **fail closed**, delete nothing |

    **`orphan` requires `B` absent** (round-10 #1). v10's orphan row accepted `B = any` and deleted it,
    which both overlapped row 8 — the same state meaning "delete B" and "delete nothing" — and could
    destroy an unverified backup, contradicting the B-verification rule outright. A `B` present without a
    valid intent now routes to row 8 and is **never** deleted automatically.

    **Rules:**

    - **Absent intent does not by itself establish a clean tree.** Recovery enumerates `.__txn` and
      validates the last committed DAG and pointer; a lone staging remnant is the `orphan` row, and
      anything else fails closed.
    - **Never restore from B when S holds `d_new`.**
    - **The ENTIRE transaction runs under the §5.4 locks**, with `CREATE_NEW` for staging and intent, so
      two simultaneous first publishers cannot both proceed.
    - **Cleanup order is `S → B → intent` everywhere**, with row 2b covering the state between deletions.
    - **Idempotence belongs to the recovery ENTRYPOINT** (`reclassify → act`); the proof invokes it twice
      from every row and injects a kill before and after every adjacent action.

    **On the directory flush:** the POSIX recipe ends with an `fsync` on the containing directory. Windows
    has no directory-fsync equivalent and `ReplaceFileW` is the atomicity primitive instead, so the plan
    states the platform reality rather than copying a step that cannot be performed here. The reviewer
    accepted this as defensible **conditional on** the durability claim staying narrow and the startup
    validation above existing. The claim is therefore exactly: **atomic visibility, with file contents
    flushed** — and explicitly *not* durability of the NTFS namespace change across sudden power loss,
    which can still be lost or reordered. The startup classifier is what makes that survivable.

5.3 **Validation order, on write AND on read** (round-10 #6). Bottom-up on write (children verified
    before a parent is published), and top-down revalidation of the entire DAG immediately before the
    consumer pointer is replaced.

    **But write-side validation alone cannot protect a consumer across a reboot.** Because NTFS namespace
    changes may reorder under power loss, the pointer's rename can survive while a child manifest's
    directory entry does not — so a pointer validated at write time can dereference, after a crash, to a
    DAG that is no longer complete. v10 validated only before pointer replacement and called that
    sufficient; it is not.

    **Every pointer dereference therefore revalidates the complete hash-linked DAG before returning any
    artifact, with startup recovery (§5.2) completed first.** A consumer that cannot validate the DAG gets
    an error, never a partial read. This is what makes the narrow durability claim survivable rather than
    merely stated.

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

6.1 **Identity edges at any distance WITHIN THE ACQUIRED CORPUS — the promise is scoped, because pass 2
    can only scan what was acquired** (round-8 #1). v8 promised "any distance" without qualification, which
    is false: pass 2 streams the 36 extracts, so a counterpart that moved outside their union is silently
    absent. The guarantee is explicitly bounded by the corpus, **absence is emitted as `UNKNOWN` rather
    than as "no counterpart exists"**, and per-origin presence is emitted alongside every edge so a
    consumer can tell those apart. Extending the guarantee would require globally covering snapshots, which
    Plan A does not acquire.

    Within that bound, and delivered by §2.2's closure pass rather than assumed: Ways sharing an `osm_id` across two origins are linked regardless of separation, because
    pass 2 retains counterparts outside the window specifically so the edge can exist. Each edge records
    all three §2.2 flags **for both endpoints**, so a closure-only counterpart is never mistaken for a
    road the site actually contains. Identity is direct evidence and needs no radius; a road
    that moved 8 km is exactly the case a radius — or a window — would have deleted.

6.2 **The normalised geometry itself as GeoParquet**, from which Plan B builds its own ephemeral spatial
    index (§2.3), bounded by the per-site `max_processing_radius_m`, so
    Plan B can generate spatial candidates at whatever radius and tolerance its science requires **without
    re-parsing any PBF** — which is Plan A's actual contract.

6.3 **A presence table, because §6.1's UNKNOWN needs somewhere to live** (round-9 #5). v9 promised
    per-origin presence and `UNKNOWN` absence but put neither in any schema, and a way present in only one
    origin has no edge to carry them. Frozen as its own manifest-bound table keyed
    `(site_id, osm_id, origin)`:

    - **`presence_in_acquired_corpus`** — whether that `osm_id` appears in that origin anywhere in the 36
      extracts
    - **`global_counterpart_status`** — deliberately distinct, and **always `UNKNOWN`** in Plan A: absence
      from the acquired corpus is not absence from OSM (§6.1)

    **Edges are built only between present endpoints.** A missing counterpart is represented by the
    presence table, never by a half-populated edge row.

6.4 **Descriptive measurements on identity edges**, carrying no cutoff and implying no classification.

**Frozen identity-edge schema.** One row per `(site_id, origin_pair, osm_id)`, origins canonically ordered:

`site_id, origin_a, origin_b, osm_id,
 a_intersects_window, a_selected_by_predicate, a_closure_only,
 b_intersects_window, b_selected_by_predicate, b_closure_only,
 min_distance_m, hausdorff_m,
 iou_5, iou_10, iou_25, iou_50, cov_a_in_b_{5,10,25,50}, cov_b_in_a_{5,10,25,50}, degenerate_flag`

**The six endpoint flags are per-endpoint, and v6 promised them in prose while omitting them from this
schema** (round-6 #1). Without them a consumer cannot tell an edge between two genuinely in-window ways
from one whose far endpoint exists only as closure — which is precisely the distinction Plan B needs.

6.5 **Exact operator definitions** (round-4 #6 — v4 left these open):

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

6.6 **No components, no aggregates, no classification vocabulary.** Connected components, aggregate
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
     rewriting but not the parsing.

     **The 22.5-minute figure is NOT the worst-case rework, and v5 used it as though it were**
     (round-5 #5). §3 had already established that it is a parser floor and that compressed size orders
     neither runtime nor memory — then this paragraph called it measured worst-case production rework and
     used it to dismiss resumable intermediates. Both claims are withdrawn: the figure was fixed in one
     place and left standing in two others.

     **The restart decision is deferred to the production-path gate.** Worst-case rework is the
     **maximum measured committed-region duration** from §3's production run, and it is unknown until that
     run happens. If it turns out unacceptable, a separately committed resumable intermediate with a
     validated cursor is the alternative, and this section is reopened. Plan A does not get to decide the
     question with a number that measures something else.

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
  the problem; Plan A owning it was. Identity edges plus GeoParquet, from which Plan B builds its own
  index, give Plan B the freedom instead.
- **A 5000 m extraction guard — a CHOSEN processing guard**: §2.3 already
  concedes it was picked rather than derived, and `max_processing_radius_m` measures Plan A's own boundary,
  not source completeness. The *processing-mask* margin is the check, kept strictly separate from the
  current-polygon margin, which proves nothing.

## Risks / open questions

- **The corpus projection rests on one file's way density** (§3.3) and now covers two passes. If some
  region is far denser per MB than Indonesia, 4.5 h is optimistic — the 12 h ceiling absorbs a 2.6x error,
  and the per-file ceiling still gates each file individually.
- **`S` (the `(site_id, osm_id)` closure table) is assumed to fit in memory** for pass 2, and it is now
  keyed by pair rather than by ID, so it is larger than v6 assumed. It is bounded by the road network
  inside 36 windows, not the corpus, but it is **unmeasured**: pass 1 reports its cardinality, and the
  pass-2 gate (§4.6) re-measures peak commit charge with it resident before pass 2 is authorised
  corpus-wide.
- **14 of 36 extracts remain unprofiled**, and the largest-by-bytes is *not* known to be the binding case
  for memory or runtime (round-4 #4). Per-file runtime enforcement is what covers this, not extrapolation.
- **The duplicate-group preflight may find unequal node references or coordinates**, which blocks rather
  than reconciles. Measured at zero across 32,369 cross-region duplicates at origin 2020 — but at
  node-reference level only, on land-border pairs only, at one origin. The coordinate check that §4.3 now
  requires has **never been run**, and it is the check most likely to fire.
- **The 5000 m guard is chosen, not derived.** Plan C could in principle exceed it, and
  `max_processing_radius_m` plus the emitted processing-mask margins are the check.
- **pyosmium 4.3.1 is newly added** to the environment and exercised only by the measurements above.
- **The production-path gate (§3) has not been run**, because the production path does not exist yet.
  Every runtime number here is a parser floor, now doubled by §2.2's second pass. If serialisation, masking
  and publication cost more than parsing, the 12 h two-pass ceiling is what will fire — and the restart
  boundary (§10.1) is undecided until that same run reports its maximum committed-region duration.
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
   predicate on fixtures containing `was:highway`, `area:highway` and `historic:highway` (**all retained**)
   and `not:highway`, `source:highway` (the only exclusions), and **failing closed on an unknown
   `*:highway` namespace**; closed and `area:highway` ways stored as `LineString` with `is_closed` set; a way with one
   invalid node location failing the stage closed; exact-mask dispatch emitting a way to every window it
   touches and none it does not; **node-reference inequality failing preflight**, and **equal node
   references with unequal resolved coordinates ALSO failing preflight**; group rejection on tag or
   timestamp disagreement; unique-dedup-key assertion passing where distinct IDs trace coincident roads;
   header-timestamp precedence with `feature_max <= header <= issue_date` and a missing-field failure;
   **identity edges emitted at arbitrary separation, proven against a way whose counterpart lies OUTSIDE
   the site window** — a synthetic in-window fixture would pass while production omitted the case (§2.2);
   `closure_only` records excluded from coverage statistics, from Plan C's road supply and from Plan B's
   spatial candidate domain; **a tag-changed counterpart still inside the window carrying `intersects_window = true`,
   `selected_by_predicate = false` AND `closure_only = true` simultaneously**, and excluded from Plan C's
   road supply because that is defined on both flags; **pass 2 emitting the other-origin counterpart of a way pass 1 already emitted** — the case v7's
   suppression key silently killed — while re-emitting no exact `(site_id, origin, source_region, osm_id)`
   record; a way inside site A and outside site B carrying different flags for
   each; `max_processing_radius_m` computed from the realised mask, emitted per site, and a query beyond it
   refused; anchors projected then clipped, proven with a way extending well outside the box and with a
   winding way whose intersection is a **`MultiLineString`**, all positive-length components retained, and
   point-only and empty intersections flagged rather than dropped; degenerate zero-length geometry emitting null metrics
   and a flag rather than dividing by zero; **no** classification vocabulary anywhere in the output;
   the memory ceiling enforced on **job-wide commit charge**, terminating via `TerminateJobObject` on a
   **`JobObjectNotificationLimitInformation`** threshold set below the hard limit — proven by a deliberate
   over-limit allocation, and proven NOT to rely on a non-guaranteed completion-port message — with
   allocation failure and abnormal child exit both failing the stage, and working set proven unsuitable by
   showing it *fall* under paging pressure; DAG validation rejecting a parent whose
   child digest was altered; pointer replacement refused when revalidation fails; lock order asserted;
   **`LockFileEx` locks released by killing the owning process**; `publish_container` refusing a reparse
   or non-NTFS ancestor; **the startup classifier driven through every row of the CURRENT §5.2 table** —
   `orphan`, `init`, 1, 1c, 2, 2b, 4, 5, 6, 7, 8 (round-10 #7: the proof previously named a row 0 that no
   longer exists) — with the **recovery ENTRYPOINT** invoked twice from each row and required to reach the
   same terminal state, since replaying a raw `ReplaceFileW` is not the test; **a kill injected before and
   after every adjacent action**, specifically the staging-before-intent boundary, each of the
   `S → B → intent` deletions, and orphan cleanup; `orphan` proven to fire only with `B` absent, and a
   `B` present without a valid intent proven to route to row 8 and **not** be deleted; a foreign
   same-digest staging file rejected by file ID; a backup with digest `d_old` but the wrong pre-mutation
   file ID rejected as unverified; the equal-digest no-op proven to run **after** recovery and to be
   refused while any remnant exists; a target legitimately named like a transaction file proven not to
   collide, via the `.__txn/<hash>` layout; two simultaneous first publishers proven to serialise via
   `CREATE_NEW`; roll-forward proven for rows 5 and 6, the latter by atomic rename with no placeholder;
   fail-closed proven for rows 7 and 8; **every pointer dereference proven to revalidate the full DAG and
   to error rather than return a partial read after a simulated reordered-namespace crash**;
   manifest-as-commit at shard, region and stage level under a simulated kill; cache key rejecting an
   artifact built for different site windows; dirty-tree scoping ignoring an unrelated docs edit.
2. **The §3 gate re-run through the production parser-to-committed-region path**, every row passing, its
   immutable measurement artifact recorded. The parser-only numbers already in §3 do not satisfy this.
3. **The full three-origin duplicate-group preflight** over every real region overlap, including the
   resolved-coordinate check, run from committed region checkpoints per §4.6 and **gating deduplication
   and publication** — not gating the parse, which it cannot precede.
4. The published origin-level datasets with `source_regions[]`, and the shard/region/origin/stage manifests
   with their digest links verified end to end.
5. The identity-edge table with its frozen operator parameters, all six endpoint flags and per-origin
   presence (absence emitted as `UNKNOWN`, never as "no counterpart"), the manifest-bound
   `(site_id, origin, osm_type, osm_id)` membership table, plus the
   GeoParquet geometry and per-site `max_processing_radius_m` that Plan B indexes for itself.
6. Per-site processing-mask margins in metres, reported separately from current-polygon margins.

Josh runs the proof. Reviewer and builder claims are advisory.
