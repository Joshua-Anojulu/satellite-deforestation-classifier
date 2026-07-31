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
  historical_cross_model_review: true
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan A: OSM normalisation infrastructure for Specification W
_Locked via grill — by Claude + Josh · revised after Codex round 1 and a read-only preflight_

> **Position.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md` (`reviewed-unapproved`).
> **Plan B** (vintage audit) and **Plan C** (feature extraction) consume this plan's output and are not
> written yet.

## Goal

Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned road-network
cache that Plan B and Plan C consume without re-parsing. This plan makes **no scientific decisions**: it
selects no road tiers, computes no features, sets no classification thresholds, and takes no position on
the roads vintage.

**Three claims in v1 were false and are corrected here.** A read-only preflight over **22 of 36 extracts**
(finding #16) established the facts below; v1 asserted them from bbox subsets.

## Measured facts this plan is built on

| Fact | Measurement |
|---|---|
| A `lines`-only read **loses data** | **22/22 files** carry highway features in `multipolygons`; 11,340 of 10,616,974 (**0.107 %**) |
| `max(osm_timestamp)` **does not** precede the snapshot date | **21/22 files** contain edits made during their nominal snapshot day |
| Scan cost is linear and cheap | **0.22 s/MB** across a 13× size range (79 MB → 1016 MB) |
| Materialisation is the expense | full parse ≈ **8.5× scan**; 1.87–1.96 s/MB |
| Whole-file parsing of the largest extracts is **infeasible** | indonesia-200101 ≈ **32 min**, -220101 ≈ **45 min**, against an observed window of **~6–11 min** |
| A bbox read of the 1 GB extract **is** feasible | **219 s** |
| `osm_changeset` is stripped at source | 0 nonzero across 504,944 lines (reviewer's larger sample) |
| `osgeo` / `ogr2ogr` unavailable | confirmed by reviewer |

## Approach

### 1. Read every way-bearing layer, not just `lines`

v1 claimed roads are ways and ways are `lines`. GDAL routes area-tagged ways to `multipolygons`, and
**every profiled file** proved it. The parser consumes **`lines`, `multipolygons` and `other_relations`**,
filters each to non-null `highway`, and records per-layer counts so the split is visible in the manifest
rather than assumed. Ways recovered from `multipolygons` retain their original element type.

### 2. Bbox-limited reads to site windows — the scan/materialise asymmetry decides this

v1 chose one-pass-per-file over per-site reads because per-site *looked* ~9× costlier. That was drawn from
a 20 s bbox read mistaken for the dominant cost. Measured: **the scan is 0.22 s/MB and linear;
materialisation is ~8.5× more.**

2.1 Each file is read **once per layer**, with a bbox covering the **union of that file's site windows**,
    so the scan happens once and materialisation is confined to the region actually needed.
2.2 **If a file's union window still overruns the execution window, it shards by site** — each site's
    window is an independently valid, independently committed unit. This is the sub-file resumability
    finding #12 demanded: a killed Indonesia parse must not commit nothing.
2.3 **Streaming API is pinned.** Bulk `read_dataframe` materialises everything; if a window is large
    enough to need streaming, `pyogrio.open_arrow` is used and **`pyarrow` is pinned as a dependency** —
    it is not currently installed, which v1 overlooked.

### 3. Snapshot provenance from the PBF header, not feature maxima

v1 asserted `max(osm_timestamp) < snapshot_date` as a "free integrity check". It would have **rejected 21
of 22 valid archives**, because extracts routinely contain edits from during their nominal snapshot day.
Worse, a feature maximum is only a *lower* bound on dataset recency and cannot authenticate a snapshot at
all.

Replaced by: **parse the PBF header's `osmosis_replication_timestamp` / content timestamp**, record it,
and require **it** and every feature timestamp to be **no later than the origin's issue date (31 Dec T)**.
That is a real bound on the archive; the feature maximum is reported as an observation, never as proof.

### 4. Deduplication within an origin

4.1 Key is **`(origin, osm_type, osm_id)`**.
4.2 **Same-ID/version groups must agree on everything before merging**: exact equality of `osm_timestamp`
    **and the canonical full tag map**, not version alone. v1 checked only version, so a timestamp or tag
    disagreement could have been silently combined under one geometry.
4.3 **Geometry relationships are classified, not unconditionally unioned.** The reviewer found the first 20
    Argentina/Bolivia duplicates were **identical full ways, not clipped fragments** — v1's central
    assumption. Rules: identical copies deduplicate directly; **proven endpoint-contiguous** fragments
    merge preserving node-reference order; **every other relationship (subset, partial overlap,
    three-region, disconnected) is reported and fails closed**, never unioned blindly.
4.4 Raw node-reference order is retained throughout, so merges cannot silently renode or reorder geometry.
4.5 **Version conflicts halt** — but a **preflight over every real overlap runs first** (the reviewer found
    0 conflicts in 871 Argentina/Bolivia IDs). If any conflict exists, it is resolved by acquiring a common
    parent extract or revising the source contract **before** the cache is built, so the halt is an entry
    condition rather than a stall discovered mid-run.
4.6 **Assert unique dedup keys**, not "zero global coincident length" — distinct OSM IDs may legitimately
    trace coincident roads, and v1's assertion would have rejected that. Distinct-ID overlap is reported
    separately.

### 5. Published layout — parse checkpoints vs published datasets

v1 promised 36 per-`(origin, region)` files **and** cross-region deduplication, which are incompatible: a
merged way either sits in two files or one region becomes an arbitrary owner.

- **36 per-`(origin, region)` parquet files are parse CHECKPOINTS only**, never consumed downstream.
- **Three origin-level datasets are published**, partitioned by stable-ID bucket, each way carrying a
  sorted **`source_regions[]`** array so provenance survives the merge.

### 6. Lineage — a high-recall candidate graph, frozen here; the cutoff frozen in Plan B

v1 deferred the threshold to Plan B but still said "no acceptable candidate", which silently requires an
acceptance rule. Plan A therefore freezes the **candidate-generation contract** — deliberately high-recall
— and leaves only the **classification cutoff** to Plan B:

- candidate search in a **deterministic metric CRS** (UTM zone of the way's centroid), with a frozen
  **search radius of 250 m** and a **buffer tolerance of 10 m**, because exact intersections of slightly
  shifted linework are usually empty;
- the **complete many-to-many candidate graph**, with pairwise and aggregate coverage metrics
  (buffered intersection over union, and over each side's length) in **geodesic metres**;
- an **unresolved set** with count and length.

Plan A classifies nothing. Plan B picks the cutoff against these distributions.

### 7. Tag schema — lossless

v1 selected a handful of attributes while promising no successor would re-parse. Since Plan B defines its
cross-tab later, and lifecycle-only ways may lack a plain `highway` tag, the cache retains the
**complete canonical tag map** plus element type and node references for every retained way. Convenience
columns (`highway`, `surface`, `tracktype`, `access`) are **redundant projections** of that map, not the
source of truth.

### 8. Extraction polygons — availability, honestly bounded

Geofabrik documents `.poly` as the boundary for the **current** extract. The inventory pins 2020–2022
PBFs and **no contemporaneous polygon exists**, so fetching today's `.poly` cannot establish which
boundary produced a 2020 archive.

Plan A therefore: fetches and pins current `.poly` files as **auxiliary, clearly labelled current-vintage**
artifacts; searches for dated polygon artifacts and records the outcome; and **marks historical source
availability UNKNOWN** where none exists, rather than certifying it from a current polygon. Plan C must
treat `roads_source_available` accordingly.

### 9. Halo — emitted, not assumed

Plan A disclaims feature decisions, so it cannot define "full halo" without importing one. It therefore
**emits each site's polygon-coverage margin in metres** and leaves the comparison to Plan C, which owns the
support radius. The existing resolver's 51-pixel contagion default is **not** inherited — it is a
different quantity for a different feature family.

### 10. Durability

10.1 **Cache identity** hashes the **parser source, `osmconf.ini`, dependency lock, resolved
     GDAL/PROJ/pyogrio versions, and dirty working-tree content** — not a git commit SHA, which both
     misses uncommitted parser edits and needlessly invalidates every checkpoint after a docs commit.
10.2 **A hashed completion manifest, published last, is the sole commit marker.** File existence is not:
     a kill can land after a parquet rename but before its checkpoint.
10.3 Outputs are **fsynced and hashed**, and **cached outputs are rehashed before reuse**.
10.4 A **cache-key-scoped OS advisory lock**, so a stale lockfile cannot wedge the pipeline.
10.5 Per-**shard** checkpoints (per site where a file shards), not merely per file.

### 11. Provenance

Inputs **rehashed before parsing** against `static_archive_inventory.json`; mismatch fails closed. The
manifest records recomputed hashes, the inventory hash and weak-anchor disclaimer verbatim, the auxiliary
polygon inventory with its current-vintage caveat, `osmconf.ini` hash, resolved stack versions, per-layer
and per-file counts, the overlap-conflict preflight result, lineage distributions, the unresolved set, the
polygon-coverage margins, and output hashes.

## Key decisions & tradeoffs

- **All way-bearing layers, because 22/22 files proved `lines` alone loses data.** Costs extra reads;
  0.107 % of features is small but systematic and silent.
- **Bbox-to-site-union reads with per-site sharding**, reversing v1 — justified by the measured
  scan/materialise asymmetry, and the only shape that survives a 6–11 minute window against a 45-minute
  whole-file parse.
- **Header timestamp, not feature maxima**, because the latter rejects 21/22 valid archives and proves
  nothing anyway.
- **Geometry relationships classified and fail-closed**, since the assumed clipped-fragment case was not
  what the data actually contains.
- **Candidate generation frozen here, classification frozen in Plan B** — high recall now, judgement later.
- **Historical polygon availability declared unknown** rather than certified from a current file.

## Risks / open questions

- **14 of 36 extracts remain unprofiled**, including all three Indonesia files. The three findings held at
  100 % across 22, but the largest files are exactly where a surprise would hurt most.
- **Whether a site-union bbox on Indonesia fits the window is projected, not measured** — the 219 s figure
  is scan-only with negligible materialisation.
- **`pyarrow` is not installed**; if streaming proves necessary, that is a new dependency.
- **The overlap preflight may find real version conflicts**, which would block until the source contract is
  revised.
- **Lifecycle-only ways** (`disused:highway=track` with no `highway` key) may be missed by a non-null
  `highway` filter; the lossless tag map mitigates this only if the filter itself is widened.
- **250 m / 10 m candidate parameters are chosen, not derived** — deliberately high-recall, and Plan B can
  only narrow, never widen, what Plan A emits.

## Out of scope

- Tier selection, the vintage decision, the cross-tab — **Plan B**.
- Features, projections, rasterisation, terrain — **Plan C**.
- Anything touching `lossyear`, the sealed worker, or the 12-site v11 path.
- Re-acquiring or modifying the certified archives; `static_archive_inventory.json` is never rewritten.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: highway features recovered from `multipolygons`
   on a real extract; the PBF header timestamp parsed and the issue-date bound enforced, with the
   feature-maximum recorded but non-authoritative; same-ID/version groups rejected on tag or timestamp
   disagreement; identical / contiguous / overlapping / disconnected geometry cases each hitting their
   declared branch, with only the first two merging; unique-dedup-key assertion passing where distinct IDs
   trace coincident roads; candidate graph emitted with metrics and **no** classification; completion
   manifest as sole commit marker under a simulated kill after rename; cache key changing on a dirty
   parser edit but **not** on an unrelated docs commit.
2. The overlap-conflict preflight over every real overlapping region pair, with counts.
3. The published origin-level datasets with `source_regions[]`, plus the 36 parse checkpoints.
4. The lineage candidate graph and unresolved set.
5. The auxiliary polygon inventory, labelled current-vintage, with historical availability marked unknown.
6. Per-site polygon-coverage margins in metres.
7. Largest-file runtime measured against the execution window.

Josh runs the proof. Reviewer and builder claims are advisory.
