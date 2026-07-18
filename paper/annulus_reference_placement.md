# Placing pseudo-invariant reference targets for a study area that is itself an active change frontier

**Status:** design note, 2026-07-17. A short, honest methods result. Supersedes the retracted
`pif_infeasibility_finding.md` (whose central claim — that PIF is *infeasible* in frontiers — is
false; see that file's banner).

## The problem

Pseudo-invariant feature (PIF) normalization co-registers multi-date optical imagery by regressing
each date onto a reference date over pixels assumed radiometrically unchanged. It needs a population
of such pixels *in the scene*. A study that deliberately samples **inside active deforestation
frontiers** appears to lack one: by construction, the analysis box is where clearing is happening.

The naive conclusion — which we drew and then retracted — is that PIF cannot be used there. That is
wrong, and the reason it is wrong is the useful part.

## The finding: the reference is not missing, it is outside the box

The PIF population is absent from the **buffered analysis box**, not from the **landscape** or the
**sensor scene**. All figures below use the study's locked criterion (Hansen GFC datamask==1,
treecover2000 ≥ 70, no 2001–2020 loss, ≥ 1,920 m from any 2001–2020 loss pixel, floor 5,000 pixels),
distances haloed so clearing just outside a window is visible, and only ≤2020 inputs.

**Inside a 4 km-buffered ~36 × 32 km box (Rondônia, Amazon fishbone):** 0 PIF pixels. Intact forest
sits a median of 168 m from the nearest clearing; the farthest forest pixel reaches 1,469 m and the
farthest point in the whole box reaches 1,573 m — both below the 1,920 m rule. Across 19 sites, only
6/19 boxes contain a PIF population.

**Immediately outside the box:** applying the identical criterion to annuli measured outward from the
box edge —

| Annulus (from box edge) | Sites reaching the 5,000 floor |
|---|---|
| ≤ 5 km | 7 / 19 |
| ≤ 10 km | 8 / 19 |
| ≤ 20 km | 10 / 19 |
| ≤ 30 km | 12 / 19 |
| ≤ 50 km | 14 / 19 |

Rondônia — 0 inside the box — has 32,915 PIF pixels within 50 km. The nearest qualifying pixel to
each box edge is 0.0–9.1 km away.

**And the annulus is genuinely same-scene, not merely nearby.** Proximity is not granule membership,
so we tested acquisition sharing directly: for each site, take the nearest outside-box PIF pixel,
ask the Copernicus Data Space catalogue which Sentinel-2 L2A products cover it in the site's frozen
seasonal window, and intersect those product IDs with the products that actually contributed to the
box composite (recorded in provenance).

- 9 / 12 sites: the annulus point shares **100%** of the box-centre point's acquisitions.
- 1 / 12: 96%.
- 3 / 12: 50%, entirely because the box *centre* lies in a Sentinel-2 tile-overlap zone (covered by
  two tiles' products) while the annulus lies in one of them — it still shares every product of that
  tile, so it is same-granule, not foreign.

A same-granule annulus 0–9 km outside the box therefore shares overpass, platform, and essentially
the same atmospheric path as the target. This is exactly the property PIF assumes and exactly what a
distant (tens-of-km, possibly cross-granule) reference cannot promise.

## Recommendation

When the analysis area is an active change frontier, **place the PIF reference in a same-granule
annulus outside the buffered analysis box**, and confirm same-scene status by **intersecting actual
contributing product IDs**, not by MGRS tile name and not by proximity alone. The box is not the
scene; the reference belongs in the scene, outside the box.

## Honest limitations (this is a placement note, not a validated pipeline)

1. **Not universal.** Only 12/19 sites had a same-granule annulus within 30 km. Seven did not —
   including whole frontiers where the surrounding landscape is also cleared or non-forest (two
   peat-swamp sites, and Rondônia/Mato Grosso/Riau/Gran Chaco reach a population only at ≥50 km,
   where the same-granule guarantee weakens). Where the disturbed region is larger than the granule,
   this does not rescue you.
2. **Endogeneity, unresolved.** "Far from mapped loss" is not "radiometrically invariant." Annulus
   forest may itself be degrading below the Hansen detection floor, so subtracting its trend could
   erase real signal. This note does not establish invariance; it establishes *availability* and
   *acquisition-sharing*.
3. **Same granule ≠ identical atmosphere.** Shared acquisitions bound aerosol/BRDF differences
   tightly but do not eliminate spatially varying path radiance across a 100+ km granule.
4. **End-to-end unvalidated.** We did not run normalization with an annulus reference and measure
   downstream improvement. The recommendation rests on availability + acquisition-sharing, not on a
   demonstrated accuracy gain. That measurement is the natural next step for anyone adopting this.

## A methods lesson worth stating plainly

This result exists only because an earlier, stronger claim was wrong, and the way it was wrong
recurs. Four times in this work a check confirmed something true but irrelevant while the load-bearing
question went unasked:

- a boolean "clear observation" mask summed to **negative** counts on the backend; the magnitudes
  were plausible and correctly ordered, so only *a count cannot be negative* caught it;
- a distance transform over a clipped raster left **median and 90th-percentile distances unmoved**
  while inflating the tail a threshold depends on — caught only by haloing and re-checking the tail;
- a download archive was **228/228 present** but two files were silently truncated — caught only by
  decoding every band, not counting files;
- and the framing itself: we reasoned from one box's geometry to a claim about *frontiers*, and never
  looked 5 km past the box edge — while explicitly arguing about 60 km reference patches.

Each survived because the natural check verified an adjacent, true fact. The generalizable takeaway:
when a result depends on a property, assert *that property* at the boundary where it enters —
`.absolute()` on a count, a halo on a distance, a decode on a download, an out-of-box census on an
in-box claim.

## Reproducibility

Every figure is label-blind (≤2020 inputs), Hansen-only or catalogue-metadata-only, and requires no
imagery download. Scripts: `risk/census/ingranule_annulus_census.py` (availability by annulus),
`risk/census/annulus_granule_check.py` (acquisition-sharing via the CDSE OData catalogue),
`risk/census/verify_composites.py` (decode-based integrity). The full design/argument history,
including the retracted line of reasoning and its adversarial review, is in `PLAN-REVIEW-LOG.md`.
