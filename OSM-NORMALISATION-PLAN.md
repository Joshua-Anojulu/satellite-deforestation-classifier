---
review_provenance:
  schema_version: 2
  status: in-progress
  rounds: []
  historical_cross_model_review: false
  final_body_cross_model_approved: false
  degraded_rounds: []
---

# Plan A: OSM normalisation infrastructure for Specification W
_Locked via grill — by Claude + Josh_

> **Position in the sequence.** Plan A of three, superseding part of `STATIC-FEATURES-PLAN.md`
> (`reviewed-unapproved`, closed after 3 Codex rounds). It absorbs that review's round-3 findings **#5**
> (sequencing depended on machinery scheduled after the audit) and **#7** (dedup and lineage not safely
> executable). **Plan B** (roads vintage audit) and **Plan C** (feature extraction) both consume this
> plan's output and are not written yet.

## Goal

Turn the 36 acquired `.osm.pbf` extracts into a normalised, deduplicated, provenance-pinned road-network
cache that Plan B and Plan C can both consume without re-parsing a byte. This plan makes **no scientific
decisions**: it selects no road tiers, computes no features, and takes no position on the roads vintage.
It exists because both successor plans need the same parsed, deduplicated input, and because the earlier
attempt discovered that its audit depended on parsing machinery that had not been specified.

## Approach

### 1. The parsing stack is constrained, and the constraint is measured

The superseded plan specified dataset-level interleaved reading via `GetNextFeature()` or `ogr2ogr`.
**Neither is available here**: `osgeo` is not installed and `ogr2ogr`/`ogrinfo` are not on `PATH`.
Available: **pyogrio 0.13.0 bundling GDAL 3.12.4**, which exposes `set_gdal_config_options`.

1.1 **Only the `lines` layer is read**, exactly once per file. The concern that per-layer pyogrio reads
    re-traverse the file is real but moot when a single layer is needed: roads are ways, and ways are
    `lines`. One layer, one traversal.
1.2 **A repo-local `osmconf.ini`** is committed, derived from the pyogrio-bundled copy with
    `osm_version=yes`, `osm_timestamp=yes`, `osm_changeset=yes` for all layers, and the `attributes` list
    extended with the tags Plan B's cross-tab needs. It is selected via `OSM_CONFIG_FILE`, **set before
    the first read**, and its **sha256 is recorded in every cache key and in the manifest** — parsed
    geometry and attributes depend on it.
1.3 **Verified working**: with this configuration pyogrio returns `osm_id`, `osm_version`,
    `osm_timestamp`, `osm_changeset` alongside the tag columns.

### 2. `osm_changeset` is permanently unavailable, and lineage is designed around that

Measured across **77,764 features in two extracts**: `osm_changeset` is **0 for every feature, with no
nulls** — Geofabrik strips changeset and user identifiers from public extracts, as its download page
states. Enabling it in `osmconf.ini` changes nothing, because the field is absent from the source.

The superseded plan's lineage design required changeset. It cannot. **Lineage uses `osm_id`,
`osm_version`, `osm_timestamp` and geometry instead**, with timestamp supplying the edit-ordering signal
changeset would have given. Both substitutes are fully populated: `osm_version` ranges 1–75 with no nulls,
`osm_timestamp` has no nulls.

**A free provenance check falls out of this.** In the `200101` extract the maximum `osm_timestamp` is
2019-12-31 19:55 — strictly before the snapshot date. Plan A therefore **asserts
`max(osm_timestamp) < snapshot_date` per extract** and fails closed otherwise, which independently
corroborates that a dated extract really is the state it claims. Nothing else in the pipeline checks this.

### 3. Normalise every highway-tagged way, not only the tiers

The cache retains **every way with a non-null `highway` tag**, because Plan B's cross-tab is what decides
whether the tier lists are right, and filtering to them first would assume the answer and make
excluded-tag accounting impossible — the exact self-contradiction the superseded plan was caught on.

Per way: `osm_id`, `osm_version`, `osm_timestamp`, raw `highway` value, `surface`, `tracktype`, `access`,
any lifecycle prefix (`disused:`, `proposed:`, `construction`), the source region and origin, and geometry.
Written as **GeoParquet per `(origin, region)`** — 36 files — under
`ml-data/deforestation-risk/external/static/normalised/`, outside the repo.

### 4. Deduplication within an origin

Overlapping extracts are deliberate: the Argentina/Bolivia straddling site pulls both country files, so a
way crossing that border appears in each, and each copy is **clipped at its extract boundary**.

4.1 **Key is `(origin, osm_type, osm_id)`** — not `(type, id, version)`. Including version *retains* both
    copies rather than merging them, which was a defect in the superseded plan.
4.2 **Version conflicts fail closed.** Overlapping extracts at the same origin are snapshots of the same
    OSM database on the same date, so the same id must carry the same version. A differing version means
    the extracts are not the same vintage, which is a provenance failure, not something to resolve by
    picking a winner. It is reported per id and halts the run.
4.3 **Same-version fragments are geometrically unioned**, then deduplicated, so a way clipped in two
    extracts is reassembled rather than either truncated or double-counted.
4.4 **Assert zero duplicated centreline length** after dedup, and report total length before and after so
    the reduction is visible rather than assumed.

### 5. Cross-origin lineage — computed, but not classified

For every way present at more than one origin, emit the raw signals Plan B needs, **without deciding what
they mean**:

- exact `osm_id` matches with their version and timestamp deltas;
- for ids appearing or disappearing, **candidate geometry matches with their overlap fractions**
  (intersection over union, and intersection over each side's length), so splits, merges and renumberings
  are visible as distributions;
- an **unresolved set**: ids with no acceptable candidate, with their count and centreline length.

**No overlap threshold is frozen here.** Plan A reports the distribution; **Plan B freezes the cutoff**
with its decision table, against observed data rather than a number invented in the infrastructure layer.
That is deliberate: this repo has already had to retract one invented threshold, and the plan that
consumes a classification should be the plan that defines it.

### 6. Extraction polygons acquired and pinned

The `.poly` extraction polygons for the 12 resolved regions were **never acquired** — the existing
inventory holds only `roads` and `terrain` kinds, and a PBF header bbox is not the extraction polygon.
Plan A fetches and pins them into a **separate auxiliary write-once inventory**, leaving
`static_archive_inventory.json` untouched. They serve two purposes here: Plan C needs them for
`roads_source_available`, and Plan A uses them to **assert that every site's full halo lies inside the
union of its regions' polygons**, failing closed rather than discovering truncation during feature
extraction.

### 7. Durability, because this environment interrupts long runs

Phase B's acquisition needed six passes under this environment's background time limits, and one pass
made zero progress because fixed overhead consumed its whole window.

7.1 **Content-addressed cache** keyed by input sha256 + `osmconf.ini` sha256 + resolved
    GDAL/PROJ/pyogrio versions + code tree SHA. Anything that changes parsed output changes the key.
7.2 **Per-`(origin, region)` checkpoints**, so an interrupted run resumes at the next unparsed file rather
    than rescanning.
7.3 **Atomic stage publication** — each output written to a temporary sibling and renamed only after its
    assertions pass, so a killed run never leaves a half-written parquet that a later pass mistakes for
    complete.
7.4 **An exclusive run lock**, so two passes cannot interleave writes.
7.5 **Bounded memory**: features processed in chunks; no whole-extract materialisation.
7.6 **Pin the geospatial stack** in `requirements.txt` — `pyogrio`, `shapely`, `geopandas`, `pyproj`,
    `rasterio` — which is currently absent entirely, along with the resolved GDAL/PROJ versions in the
    manifest.

### 8. Provenance

Every input **rehashed before parsing** and checked against `static_archive_inventory.json`; mismatch
fails closed. The manifest records: recomputed input hashes, the inventory hash and its weak-anchor
disclaimer verbatim, the auxiliary `.poly` inventory hash, `osmconf.ini` hash, resolved
GDAL/PROJ/pyogrio versions, code tree SHA, per-file feature counts and total centreline length before and
after dedup, the version-conflict report, the lineage distributions, the unresolved set, and output hashes.

## Key decisions & tradeoffs

- **pyogrio single-layer reads instead of `GetNextFeature()`**, because `osgeo` and `ogr2ogr` are simply
  not present. Reading only `lines` makes the one-traversal property hold anyway.
- **Lineage on id/version/timestamp/geometry, not changeset**, because changeset is stripped at source and
  no configuration can restore it. Verified, not assumed.
- **Version conflicts halt rather than resolve.** A "highest version wins" rule would silently paper over a
  vintage mismatch between extracts, which is a provenance failure worth stopping for.
- **All highway tags normalised, not just the tiers**, so Plan B can actually decide the tiers.
- **No overlap threshold frozen here** — Plan A reports distributions, Plan B decides.
- **No scientific decisions at all** in this plan; that separation is why the three-way split happened.

## Risks / open questions

- **The unresolved-lineage fraction is unknown until this runs.** If it is large, Plan B's audit is
  weakened, and that would be a reason to revisit the audit design rather than to force a threshold here.
- **Version conflicts may actually occur** across overlapping Geofabrik extracts if the company rebuilds
  regions on different schedules. The plan halts if so, which is correct but would block until resolved.
- **Runtime for the 1.4 GB Indonesia extracts is unmeasured**; a small extract read in 4 s, but that does
  not extrapolate.
- **GeoParquet geometry fidelity** for very long ways clipped and re-unioned needs a check that the union
  is exact rather than simplified.
- **`osmconf.ini` is derived from the pyogrio-bundled copy**, so a pyogrio upgrade could change the base
  file underneath it; the hash detects the drift but the resolution is manual.

## Out of scope

- **Road tier selection, the vintage decision, and the cross-tab interpretation** — Plan B.
- **Features, projections, rasterisation, terrain** — Plan C.
- **Anything touching `lossyear`**, the sealed worker, or the 12-site v11 path.
- **Re-acquiring or modifying the certified archives**; `static_archive_inventory.json` is never rewritten.

## Proof

From the repo root with `PYTHONPATH` set, using `C:\Users\josha\.venvs\satclf\Scripts\python.exe`:

1. `-m pytest forecast/tests -q` fully green, including: `osmconf.ini` producing `osm_version`/
   `osm_timestamp` on a fixture extract; the `max(osm_timestamp) < snapshot_date` assertion failing on a
   doctored fixture; dedup on `(origin, type, id)` reassembling a way clipped across two synthetic
   extracts with **zero duplicate length**; a version conflict halting the run; lineage emitting overlap
   distributions **without** classifying; the halo-inside-polygon assertion failing closed on a synthetic
   truncation; cache keys changing when `osmconf.ini` changes; atomic publication leaving no partial
   parquet after a simulated kill.
2. The auxiliary `.poly` write-once inventory, with `static_archive_inventory.json` unchanged (hash
   compared before and after).
3. The normalised GeoParquet cache, 36 files, with per-file counts and centreline length before and after
   dedup.
4. The lineage report: exact-match counts, overlap distributions, and the unresolved set with its length.
5. The manifest with recomputed hashes and the pinned stack.

Josh runs the proof. Reviewer and builder claims are advisory.
