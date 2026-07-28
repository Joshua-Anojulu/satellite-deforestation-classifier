"""Static drivers, their issue-date compliance, and the frozen primary schema.

`FORECAST-PLAN.md` §3 freezes two rules this module implements literally:

1. **Issue date for origin T is 31 December T.** Every layer vintage used by the
   primary model must carry a timestamp **on or before** that date.
2. **Anything lacking a clean ≤-issue snapshot is excluded from the primary
   model** and may appear only in a labelled exploratory sensitivity.

To those the analysis plan adds a third, which exists to stop a subtler leak:

3. **One frozen schema across all origins** -- the *intersection* of layers valid
   at every origin.  A layer present in training and absent in validation would
   encode time through missingness, which a model can read as a signal about
   *which year it is looking at*.

Coverage is therefore an explicit feature, never `NaN`: "not surveyed here" and
"none present here" must not share an encoding.

Nothing here edits `risk/external_layers.py`; the 12-site v11 path is frozen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

#: The three frozen origins.  Imported rather than restated where possible, but
#: the issue-date rule is local to this module.
ORIGINS = (2020, 2021, 2022)

GLOBAL = "global"
REGION_LIMITED = "region_limited"


def issue_date(origin: int) -> date:
    """Issue date for an origin: 31 December of T (frozen, §3)."""

    return date(origin, 12, 31)


@dataclass(frozen=True)
class StaticLayer:
    """A static driver and everything needed to judge its admissibility."""

    name: str
    #: "static" -> one vintage for all origins; "per_origin" -> a snapshot per T.
    kind: str
    coverage: str
    #: For static layers: the single release date.  For per-origin layers this is
    #: unused and ``snapshot_for`` supplies the date.
    vintage: date | None = None
    source: str = ""
    note: str = ""

    def snapshot_for(self, origin: int) -> date | None:
        """The vintage that would be used at this origin, ignoring compliance.

        Per-origin OSM snapshots are Geofabrik's **1 January of T** yearly
        archives.  Geofabrik keeps no year-end snapshot, and 1 January of T+1 --
        though only a day past the issue date -- is still *after* it, so the
        compliant choice is 1 January of T.  That makes the roads layer up to
        twelve months stale, which is disclosed rather than hidden.
        """

        if self.kind == "static":
            return self.vintage
        if self.kind == "per_origin":
            return date(origin, 1, 1)
        raise ValueError(f"unknown layer kind: {self.kind}")

    def is_issue_date_valid(self, origin: int) -> bool:
        snapshot = self.snapshot_for(origin)
        return snapshot is not None and snapshot <= issue_date(origin)


#: The registry.  Vintages are facts about the published products, checked
#: during Phase B reconnaissance rather than assumed.
REGISTRY: tuple[StaticLayer, ...] = (
    StaticLayer(
        name="roads",
        kind="per_origin",
        coverage=GLOBAL,
        source="Geofabrik dated OSM extracts (YYMMDD, 1 January of T)",
        note="up to 12 months stale: no year-end snapshot exists",
    ),
    StaticLayer(
        name="terrain",
        kind="static",
        coverage=GLOBAL,
        vintage=date(2008, 1, 1),
        source="CGIAR-CSI SRTM v4.1 (2008 release, 90 m)",
        note=(
            "NOT Copernicus DEM. Both GLO-30 and GLO-90 on AWS are the *2021 "
            "release* -- switching to GLO-90 does not help, because the release, "
            "not the resolution, is what post-dates the 2020 issue date. SRTM "
            "v4.1 predates every origin by over a decade. 90 m resampled for the "
            "30 m table; terrain is the most static covariate in the set."
        ),
    ),
    StaticLayer(
        name="rivers",
        kind="static",
        coverage=GLOBAL,
        vintage=date(2013, 1, 1),
        source="HydroBASINS v1.0 level 3",
    ),
    StaticLayer(
        name="ecoregion",
        kind="static",
        coverage=GLOBAL,
        vintage=date(2017, 1, 1),
        source="RESOLVE Ecoregions 2017",
    ),
    StaticLayer(
        name="climate",
        kind="static",
        coverage=GLOBAL,
        vintage=date(2010, 12, 31),
        source="CHIRPS 1981-2010 normal (pre-period by construction)",
    ),
    StaticLayer(
        name="protected_areas",
        kind="per_origin",
        coverage=GLOBAL,
        # No retrievable snapshot: Protected Planet publishes the current month
        # only, with no documented public archive of past monthly releases at
        # stable URLs.  Modelled as having NO vintage so it fails rule 1 at every
        # origin rather than being silently substituted with a current release.
        source="WDPA monthly release (NO public archive of past releases)",
        note="excluded: no retrievable <=issue-date snapshot",
    ),
    StaticLayer(
        name="peat",
        kind="static",
        coverage=REGION_LIMITED,
        vintage=date(2018, 1, 1),
        source="PEATMAP (Asia only)",
        note=(
            "Asia-only: Amazon and Congo sites have no peat data, so absence "
            "would conflate 'no peat' with 'not surveyed'."
        ),
    ),
)


#: Layers with no retrievable snapshot at ANY origin.  Kept as an explicit set
#: rather than inferred from a null vintage, so the reason is legible and a
#: future contributor cannot "fix" it by quietly pointing at a current release.
NO_RETRIEVABLE_SNAPSHOT = frozenset({"protected_areas"})


@dataclass(frozen=True)
class SchemaDecision:
    """Why a layer is in or out of the primary model."""

    name: str
    included: bool
    reason: str
    valid_origins: tuple[int, ...] = field(default_factory=tuple)


def evaluate_layer(layer: StaticLayer, origins: Sequence[int] = ORIGINS) -> SchemaDecision:
    """Decide a single layer's admissibility against all three frozen rules."""

    if layer.coverage == REGION_LIMITED:
        return SchemaDecision(
            layer.name, False,
            f"region-limited coverage: {layer.note or 'absence is ambiguous'}",
        )

    if layer.name in NO_RETRIEVABLE_SNAPSHOT:
        return SchemaDecision(
            layer.name, False,
            "no retrievable <=issue-date snapshot exists for any origin",
        )

    valid = tuple(o for o in origins if layer.is_issue_date_valid(o))
    if len(valid) != len(origins):
        missing = tuple(o for o in origins if o not in valid)
        return SchemaDecision(
            layer.name, False,
            f"vintage post-dates the issue date at origin(s) {missing}; the frozen "
            "intersection admits only layers valid at EVERY origin",
            valid,
        )
    return SchemaDecision(layer.name, True, "valid at every origin", valid)


def primary_schema(
    origins: Sequence[int] = ORIGINS,
    registry: Iterable[StaticLayer] = REGISTRY,
) -> tuple[tuple[str, ...], tuple[SchemaDecision, ...]]:
    """Return the frozen primary feature schema and every decision behind it.

    The schema is the intersection across origins, so it cannot vary by origin
    and therefore cannot encode time through missingness.
    """

    decisions = tuple(evaluate_layer(layer, origins) for layer in registry)
    included = tuple(d.name for d in decisions if d.included)
    if not included:
        raise ValueError("primary static schema is empty; refusing to proceed")
    return included, decisions


def coverage_features(included: Sequence[str]) -> tuple[str, ...]:
    """Explicit coverage flags, so absence is never encoded as NaN."""

    return tuple(f"{name}_covered" for name in sorted(included))


def build_manifest(
    origins: Sequence[int] = ORIGINS,
    registry: Iterable[StaticLayer] = REGISTRY,
) -> dict[str, object]:
    """The committed record of what the primary model may use, and why."""

    registry = tuple(registry)
    included, decisions = primary_schema(origins, registry)
    by_name = {layer.name: layer for layer in registry}
    return {
        "schema_version": 1,
        "origins": list(origins),
        "issue_dates": {str(o): issue_date(o).isoformat() for o in origins},
        "primary_schema": list(included),
        "coverage_features": list(coverage_features(included)),
        "layers": {
            decision.name: {
                "included_in_primary": decision.included,
                "reason": decision.reason,
                "valid_origins": list(decision.valid_origins),
                "kind": by_name[decision.name].kind,
                "coverage": by_name[decision.name].coverage,
                "source": by_name[decision.name].source,
                "note": by_name[decision.name].note,
                "snapshots": {
                    str(o): (
                        by_name[decision.name].snapshot_for(o).isoformat()
                        if by_name[decision.name].snapshot_for(o) else None
                    )
                    for o in origins
                },
            }
            for decision in decisions
        },
    }


def write_manifest_once(path: str | Path, manifest: Mapping[str, object]) -> Path:
    """Write the schema manifest exclusively; never rewrite an existing one."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as sink:
        sink.write(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path
