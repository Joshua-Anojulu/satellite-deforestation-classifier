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
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan A: OSM normalisation infrastructure for Specification W
_Locked via grill — by Claude + Josh · revised after Codex rounds 1–2, a preflight, and a benchmark_

> **Position.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md` (`reviewed-unapproved`).
> **Plan B** (vintage audit) and **Plan C** (feature extraction) consume this output and are unwritten.

## Goal

Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned road-network
cache that Plan B and Plan C consume without re-parsing. **No scientific decisions**: no tier selection,
no vintage position, no classification thresholds.

## The design changed because three parsers were invalidated by measurement

| design | why it failed | found by |
|---|---|---|
| `GetNextFeature()` / `ogr2ogr` | `osgeo` and CLIs not installed | probe |
| pyogrio bbox-to-site-union | envelope **202×** the true window area; **no node references** | reviewer + API check |
| pyosmium *inside the assistant's background window* | >21 min for one 1.4 GB file | benchmark |

**The third was a misdiagnosis.** One pyosmium pass over the **entire corpus** costs **2.7 hours**
(12,658 ways/s measured; ~121 M ways over 9.42 GB), against **7.2 hours** for per-site pyogrio on the
Indonesia files alone. pyosmium was rejected only because 21 min/file exceeds the **6–11 minute background
window** — which constrains *Claude's* execution, not the machine. Josh ran the 10.92 GB GFC acquisition to
completion in his own terminal. **This plan is a long-running job Josh launches**, with checkpoints for
crash resilience, not to fit a seven-minute ceiling.

## Approach

### 1. One raw way stream per file — no GDAL layers

pyosmium reads the OSM data model directly, so GDAL's `lines` / `multipolygons` / `other_relations`
routing does not exist. That dissolves round-1 #1 (0.107 % of highway features were being lost to
`multipolygons`) rather than working around it, and makes node references available (round-2 #3).

1.1 `osmium.FileProcessor(path, osmium.osm.WAY)` streams every way once.
1.2 **Selection predicate (frozen):** a way is retained if it carries `highway` **or any of the enumerated
    lifecycle keys** `disused:highway`, `abandoned:highway`, `proposed:highway`, `construction:highway`,
    `razed:highway`, `demolished:highway`. Round-2 #5: a non-null `highway` test silently dropped
    lifecycle-only ways before their tags could be preserved.
1.3 **Retained per way:** `osm_id`, `version`, `timestamp`, the **complete canonical tag map**, the
    **ordered node-reference list**, and `is_closed`. Convenience columns are redundant projections.
1.4 **Closed ways are kept as a distinct geometry class** (`way_closed`), not coerced to lines
    (round-2 #8). Whether a plaza's perimeter, area or ring is the audited object is **Plan B/C's**
    decision; Plan A preserves the raw form and says so.

### 2. Site dispatch by exact mask, during the single pass

Round-2 #2: the nine Indonesian site boxes total 0.495 deg² inside a **99.83 deg² envelope — 202×
oversized**, and clustering only reaches 110×, so no rectangle works. Instead each way is tested against
the **exact set of site window polygons** as it streams, and emitted to every window it touches. One pass,
no envelope, no `if it overruns` trigger that a killed process could never record.

**Extraction guard (frozen):** a site window is its site box buffered by **5000 m**, geodesically. That
conservatively exceeds the largest plausible downstream support (Plan C's road radii reach 1500 m) plus
the lineage candidate radius (250 m) and tolerance, so Plan C cannot need a road Plan A discarded
(round-2 #4). Plan A additionally **emits each site's realised coverage margin**, so Plan C can verify
rather than trust.

### 3. Geometry, and its cost

Node references alone are not geometry; pyosmium needs a **node-location index**. Frozen: `flex_mem` where
the file fits available RAM, otherwise a **on-disk `sparse_file_array`**, chosen per file by a measured
rule and recorded. **This cost is unmeasured** and is the plan's largest remaining unknown — the 2.7 hour
projection covers the way stream only. A measured `indonesia-220101` completion is an **entry gate**
before the full run, not a claim made here.

### 4. Deduplication within an origin

4.1 Key `(origin, osm_type, osm_id)`.
4.2 **Group members must agree on `version`, `timestamp` and the full canonical tag map** before any
    geometry reconciliation (round-2 #6/r1 #8). Disagreement fails closed and is reported.
4.3 **Reconciliation is over ordered node-ID sequences**, now that they are available. A group resolves if
    and only if a **unique consistent global node sequence** exists — which correctly accepts identical
    copies, subsets (take the maximal), compatible partial overlaps, and N-fragment cases. It **fails only
    on genuine ambiguity**: branching, coordinate conflict for a shared node, or an unbridgeable gap.
    v2's rule rejected safe cases and accepted an underspecified one (endpoint contact alone).
4.4 **Assert unique dedup keys**, not zero coincident length — distinct IDs may legitimately trace
    coincident roads. Distinct-ID coincidence is reported separately.
4.5 **Every duplicate group is preflighted** — version, tags, timestamp, node-sequence relationship — over
    all real overlaps **before** cache construction (round-2 #7), so an expected-but-unhandled case cannot
    halt the run after hours of parsing.

### 5. Published layout and commit protocol

- **Per-`(origin, region)` outputs are parse checkpoints**, defined as **logical manifests** that may
  reference multiple part files, not "36 single parquets" (round-2 #14).
- **Three origin-level datasets are published**, partitioned by stable-ID bucket, each way carrying sorted
  **`source_regions[]`**.
- **Manifest hierarchy is the commit protocol**: a hashed manifest per **shard**, a **region** manifest
  referencing its shards, a **stage** manifest referencing all regions. A manifest — never file existence —
  is the commit marker at every level, so shards completed before a kill are not orphans.
- **Two locks, not one** (round-2 #15): artifacts live under their content-addressed key with a
  **cache-key lock**; the shared consumer pointer to the published datasets updates under a separate
  **logical-dataset publication lock**, so two valid keys cannot race on the same destination.

### 6. Lineage — emitted, never classified

6.1 **Symmetric CRS**: one UTM zone per **site window**, chosen from the window centroid, so A→B and B→A
    are identical (round-2 #10). Never per-way.
6.2 **Metrics, with exact formulas and units**: buffered-area IoU (dimensionless); `len(A ∩ buffer(B))/len(A)`
    and its reciprocal (dimensionless, lengths geodesic metres); aggregate coverage as union-based over a
    candidate component. **Raw centre-to-centre and Hausdorff distances in metres are emitted too**, so
    Plan B is not confined to one tolerance.
6.3 **Multiple frozen tolerances** — buffers at **5, 10, 25, 50 m** — and a **candidate radius of 1000 m**
    with an emitted saturation curve, so Plan B can see whether widening would have added edges rather than
    inheriting a censored graph (round-2 #9). v2's single 250 m / 10 m pair silently bounded Plan B's
    science.
6.4 **No classification vocabulary.** Degree-zero nodes are `no_candidate`; everything else carries
    candidate degree and metric distributions. `resolved` / `unresolved` belong to Plan B (round-2 #11).

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
    the auxiliary polygon inventory hash, `osmconf.ini`-equivalent parser configuration, and resolved
    library versions. A cached artifact built for different site windows must not validate.
8.2 **Dirty-tree hashing is scoped** to the parser, configuration, schema and dependency files that can
    affect the stage — not all uncommitted content, which would invalidate caches on an unrelated docs
    edit (round-2 #13).
8.3 Outputs **fsynced and hashed**; cached outputs **rehashed before reuse**.

### 9. Extraction polygons

Geofabrik documents `.poly` as the **current** extract boundary; no contemporaneous polygon exists for a
2020–2022 archive. Current files are pinned as **clearly-labelled current-vintage** auxiliary artifacts,
a search for dated artifacts is recorded, and **historical source availability is marked UNKNOWN** rather
than certified from a current polygon. Plan C must treat `roads_source_available` accordingly.

### 10. Provenance

Inputs rehashed before parsing against `static_archive_inventory.json`; mismatch fails closed. The manifest
records recomputed hashes, the inventory hash and weak-anchor disclaimer verbatim, the polygon inventory
with its vintage caveat, resolved library versions, per-file way and retention counts, the duplicate-group
preflight result, lineage distributions and saturation curves, coverage margins, the node-location index
strategy actually used, and output hashes.

## Key decisions & tradeoffs

- **A long-running job Josh launches, not a windowed one.** Three designs were distorted by treating the
  assistant's 6–11 minute background limit as a property of the problem. Checkpoints stay, for crashes.
- **Raw way stream over GDAL layers**, which dissolves the layer-loss, node-reference, lifecycle-tag and
  area-way findings rather than answering each separately.
- **Exact mask dispatch**, since no rectangle approximates these site sets (202×, 110× clustered).
- **Node-sequence reconciliation** accepting any unique consistent sequence, failing only on ambiguity.
- **Lineage emitted at four tolerances with a saturation curve**, so Plan B's science is not bounded by
  Plan A's parameters.
- **A 5000 m extraction guard**, conservative by construction, plus emitted margins so Plan C can verify.

## Risks / open questions

- **The node-location index cost is unmeasured** and is the single largest unknown; the 2.7 hour figure
  covers the way stream only. A measured largest-file completion gates the full run.
- **14 of 36 extracts remain unprofiled**, all three Indonesia files among them.
- **`sparse_file_array` on this disk** may be slow enough to change the design again.
- **The duplicate-group preflight may find unreconcilable groups**, which would block until the source
  contract is revised.
- **The 5000 m guard is chosen, not derived** — conservative, but Plan C could in principle exceed it, and
  the emitted margins are the check.
- **pyosmium 4.3.1 is newly added** to the environment and unexercised beyond the benchmark.

## Out of scope

- Tier selection, the vintage decision, the cross-tab — **Plan B**.
- Features, projections, rasterisation, terrain, and any road-centreline semantics for closed ways —
  **Plan C**.
- Anything touching `lossyear`, the sealed worker, or the 12-site v11 path.
- Re-acquiring or modifying the certified archives.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: lifecycle-only ways retained by the frozen
   predicate; closed ways preserved as a distinct class; exact-mask dispatch emitting a way to every window
   it touches and none it does not; node-sequence reconciliation accepting identical/subset/overlap/
   N-fragment groups and failing on branching, coordinate conflict and gaps; group rejection on tag or
   timestamp disagreement; unique-dedup-key assertion passing where distinct IDs trace coincident roads;
   header-timestamp precedence with `feature_max ≤ header ≤ issue_date` and a missing-field failure;
   lineage emitting metrics at all four tolerances with **no** classification vocabulary; manifest-as-commit
   at shard, region and stage level under a simulated kill; cache key rejecting an artifact built for
   different site windows; dirty-tree scoping ignoring an unrelated docs edit.
2. **The entry gate**: a measured `indonesia-220101` completion — way stream **plus node-location index and
   geometry** — with its wall-clock and index strategy recorded, before the full run is authorised.
3. The duplicate-group preflight over every real overlap.
4. The published origin-level datasets with `source_regions[]`, and the shard/region/stage manifests.
5. The lineage candidate graph, tolerance sweep and saturation curve.
6. Per-site coverage margins in metres.

Josh runs the proof. Reviewer and builder claims are advisory.
