"""§7 snapshot provenance, read from the real PBF headers.

Implements the header side of §7 of `OSM-NORMALISATION-PLAN.md`.

**The authoritative field is absent for an entire origin, and this module exists
to say so rather than to paper over it.**  §7 requires
`osmosis_replication_timestamp`, "else the documented content timestamp, with
precedence and a missing-field failure stated", and requires validating headers
"against a nominal archive-date window **derived from all 36 real headers**".
Surveyed across the corpus:

- **2021: 12 of 12 present.**  Every region carries `2021-01-01T21:42:03Z`.
- **2022: 12 of 12 present.**  Every region carries `2022-01-01T21:21:26Z`.
- **2020: 0 of 12 present.**  The field is empty in every single extract.

So the window cannot be derived from 36 headers, because only 24 exist, and a
third of the corpus -- the whole 2020 vintage -- has no authoritative timestamp
at all.  That is not an edge case to be defaulted away; it decides what vintage
can be claimed for a third of the published dataset.

**Nothing is substituted here.**  A missing field is reported as
:data:`ABSENT`, never as a filename date or a guess.  The filename *does* encode
an intended date and the header *does* carry a replication base URL, but
promoting either to "the snapshot timestamp" is a provenance claim, and §7 is
explicit that the feature maximum -- the obvious substitute -- "is recorded as an
observation and is never authoritative: it would have rejected 21 of 22 valid
archives".  The same reasoning forbids the other substitutes.

**Identical timestamps within an origin are expected, not suspicious.**
Geofabrik cuts every regional extract from one planet snapshot, so all twelve
2021 regions sharing a timestamp to the second is corroboration that the origin
is one vintage.
"""

from __future__ import annotations

import osmium
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

#: The authoritative field §7 names.
REPLICATION_TIMESTAMP = "osmosis_replication_timestamp"
REPLICATION_BASE_URL = "osmosis_replication_base_url"

#: What a region's timestamp is when the authoritative field is empty.  A
#: sentinel rather than `None` so it survives serialisation into a conflict
#: report and reads as a decision rather than a missing value.
ABSENT = "ABSENT"


class ProvenanceUnavailable(Exception):
    """A header could not be read at all.  Distinct from a field being empty."""


@dataclass(frozen=True)
class RegionProvenance:
    """One extract's header provenance."""

    name: str
    origin: str
    region: str
    header_timestamp: str
    replication_base_url: str
    generator: str

    @property
    def authoritative(self) -> bool:
        """Whether §7's required field was actually present."""

        return self.header_timestamp != ABSENT

    def document(self) -> dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "region": self.region,
            "header_timestamp": self.header_timestamp,
            "authoritative": self.authoritative,
            "replication_base_url": self.replication_base_url,
            "generator": self.generator,
        }


def read_provenance(path: str | Path) -> RegionProvenance:
    """Read one extract's header.  Cheap -- roughly 0.3 s, no way pass."""

    from forecast.osm_pipeline import origin_and_region

    path = Path(path)
    try:
        header = osmium.io.Reader(str(path)).header()
    except Exception as exc:  # pragma: no cover - a corrupt file, not a policy
        raise ProvenanceUnavailable(f"could not read header of {path.name}: {exc}") from exc

    origin, region = origin_and_region(path)
    return RegionProvenance(
        name=path.stem,
        origin=origin,
        region=region,
        header_timestamp=header.get(REPLICATION_TIMESTAMP) or ABSENT,
        replication_base_url=header.get(REPLICATION_BASE_URL) or "",
        generator=header.get("generator") or "",
    )


@dataclass(frozen=True)
class ProvenanceSurvey:
    """The corpus-wide header survey §7 asks for."""

    regions: tuple[RegionProvenance, ...]

    @property
    def by_origin(self) -> dict[str, tuple[RegionProvenance, ...]]:
        grouped: dict[str, list[RegionProvenance]] = {}
        for region in self.regions:
            grouped.setdefault(region.origin, []).append(region)
        return {k: tuple(v) for k, v in sorted(grouped.items())}

    @property
    def origins_without_authority(self) -> tuple[str, ...]:
        """Origins where NO region carries the authoritative field.

        Reported per origin rather than per file because that is the shape the
        corpus actually has, and because a whole missing vintage is a different
        problem from a few missing files.
        """

        return tuple(
            origin
            for origin, regions in self.by_origin.items()
            if not any(r.authoritative for r in regions)
        )

    def origin_timestamp(self, origin: str) -> str:
        """The single timestamp shared by an origin's regions, or `ABSENT`.

        Raises when regions disagree: Geofabrik cuts one planet snapshot per
        origin, so disagreement means the origin is not one vintage and no
        single timestamp describes it.
        """

        stamps = {r.header_timestamp for r in self.by_origin.get(origin, ())}
        if not stamps:
            raise KeyError(f"no regions surveyed for origin {origin!r}")
        if len(stamps) > 1:
            raise ProvenanceUnavailable(
                f"origin {origin} has regions from different snapshots: "
                f"{sorted(stamps)}; no single timestamp describes it"
            )
        return stamps.pop()

    def describe(self) -> str:
        lines = []
        for origin, regions in self.by_origin.items():
            present = sum(1 for r in regions if r.authoritative)
            stamps = sorted({r.header_timestamp for r in regions})
            lines.append(
                f"{origin}: {present}/{len(regions)} authoritative"
                + (f"  {stamps[0]}" if len(stamps) == 1 else f"  {stamps}")
            )
        if self.origins_without_authority:
            lines.append(
                "NO AUTHORITATIVE HEADER for origin(s): "
                + ", ".join(self.origins_without_authority)
                + " -- §7's window cannot be derived from 36 headers"
            )
        return "\n".join(lines)

    def document(self) -> dict[str, object]:
        return {
            "regions": [r.document() for r in self.regions],
            "origins_without_authority": list(self.origins_without_authority),
            "authoritative_regions": sum(1 for r in self.regions if r.authoritative),
            "total_regions": len(self.regions),
        }


def survey(paths: Iterable[str | Path]) -> ProvenanceSurvey:
    return ProvenanceSurvey(tuple(read_provenance(p) for p in sorted(paths)))
