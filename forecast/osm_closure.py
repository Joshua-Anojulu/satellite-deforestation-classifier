"""Two-pass identity closure: `S = {(site_id, osm_id)}` and the three flags.

Implements §2.2 of `OSM-NORMALISATION-PLAN.md`.

**Why two passes.**  §6.1 promises identity edges between the same `osm_id` in
different origins *at any distance within the acquired corpus*.  Window dispatch
alone cannot deliver that: a way that moved 8 km between origins is discarded by
the first pass and can never appear in the join.  Pass 2 exists to recover
exactly those counterparts.

**Three things here were wrong in earlier drafts, and each would have failed
silently.  They are the reason this module is shaped the way it is.**

*The closure table is keyed by the pair, not the id.*  A way can be inside site
A's window and outside site B's, so "outside window" is a property of the
`(site, way)` pair.  A single boolean on the record cannot express it.

*The suppression key must carry origin and region.*  Suppressing pass 2 whenever
`(site_id, osm_id)` was already emitted suppresses **everything** -- every pair in
`S` is in `S` *because* pass 1 emitted it in some origin, so that rule makes pass
2 inert and the identity edges simply absent, with no error raised anywhere.
Only the exact `(site_id, origin, source_region, osm_id)` record already written
is skipped.

*`closure_only` is derived, and the road supply needs two flags.*  A tag-changed
counterpart still inside the window is `intersects_window=True`,
`selected_by_predicate=False` and `closure_only=True` simultaneously.  Defining
Plan C's road supply on `intersects_window` alone would admit it -- a record that
is in the window but is no longer a road.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, NamedTuple


class ClosureKey(NamedTuple):
    """A `(site_id, osm_id)` pair: the unit of site relevance."""

    site_id: str
    osm_id: int


class RecordKey(NamedTuple):
    """The unit of *emission*.

    Distinct from :class:`ClosureKey` on purpose, and the distinction is the whole
    fix for the inert-closure bug: suppression operates on this key, relevance on
    the other.
    """

    site_id: str
    origin: int
    source_region: str
    osm_id: int


@dataclass(frozen=True)
class SiteRecord:
    """One way, as claimed by one site in one origin/region, with its flags."""

    key: RecordKey
    intersects_window: bool
    selected_by_predicate: bool

    @property
    def closure_only(self) -> bool:
        """Derived, never stored independently (§2.2)."""

        return not (self.intersects_window and self.selected_by_predicate)

    @property
    def in_road_supply(self) -> bool:
        """Plan C's road supply and every coverage statistic.

        Both flags, not `intersects_window` alone -- otherwise a tag-changed
        record inside the window counts as a road it no longer is.
        """

        return self.intersects_window and self.selected_by_predicate


class ClosureTable:
    """`S`: every way touching a given site window, in any origin.

    Accumulated during pass 1 and published as a first-class artifact, so pass 2's
    input is versioned rather than incidental process state.

    **Indexed by `osm_id`, because pass 2 asks once per way.**  The first version
    scanned every pair on every call, which is correct and unusable: measured at
    480 us per call for `|S|` = 10,000 and 91 ms at 500,000, against 43.25 M ways
    in one extract alone -- 5.8 hours and 1,090 hours respectively, for a single
    file of thirty-six.  The lookup is the inner loop of the whole second pass, so
    it is a dict.  Semantics are unchanged; only the cost is.
    """

    def __init__(self, pairs: Iterable[ClosureKey] = ()) -> None:
        self._pairs: set[ClosureKey] = set()
        self._by_osm_id: dict[int, set[str]] = {}
        for pair in pairs:
            self.add(pair.site_id, pair.osm_id)

    def add(self, site_id: str, osm_id: int) -> None:
        self._pairs.add(ClosureKey(site_id, osm_id))
        self._by_osm_id.setdefault(osm_id, set()).add(site_id)

    def claims(self, osm_id: int) -> bool:
        """Whether any site claims this way, without building a tuple.

        Pass 2 rejects the overwhelming majority of ways on this question, so it
        is answered without sorting or allocating.
        """

        return osm_id in self._by_osm_id

    def sites_claiming(self, osm_id: int) -> tuple[str, ...]:
        """Sites that claim this way -- never "all sites"."""

        return tuple(sorted(self._by_osm_id.get(osm_id, ())))

    def __contains__(self, key: object) -> bool:
        return key in self._pairs

    def __len__(self) -> int:
        return len(self._pairs)

    def __iter__(self) -> Iterator[ClosureKey]:
        return iter(sorted(self._pairs))


def pass_one_records(
    *,
    origin: int,
    source_region: str,
    ways: Iterable[tuple[int, bool]],
    site_id: str,
) -> Iterator[SiteRecord]:
    """Emit pass-1 records for one site from one extract.

    `ways` is `(osm_id, intersects_window)` for ways the §1.2 predicate retained;
    pass 1 only ever sees predicate-selected ways, so `selected_by_predicate` is
    True for all of them.
    """

    for osm_id, intersects in ways:
        if not intersects:
            continue
        yield SiteRecord(
            key=RecordKey(site_id, origin, source_region, osm_id),
            intersects_window=True,
            selected_by_predicate=True,
        )


def pass_two_records(
    *,
    origin: int,
    source_region: str,
    closure: ClosureTable,
    emitted: Mapping[RecordKey, object] | set[RecordKey],
    ways: Iterable[tuple[int, bool, bool]],
) -> Iterator[SiteRecord]:
    """Emit the counterparts pass 1 could not see.

    `ways` is `(osm_id, intersects_by_site, selected_by_predicate)` for every way
    in the extract -- pass 2 must consider ways the predicate did *not* select,
    because a tag-changed counterpart is exactly the case identity edges exist to
    catch.

    **`intersects_by_site` is a mapping, not a boolean, and that is this
    module's own rule finally applied here.**  The header says a way can be
    inside site A's window and outside site B's, so "outside window" is a
    property of the `(site, way)` pair and *"a single boolean on the record
    cannot express it"* -- yet this function took one boolean and stamped it onto
    every claiming site.  A way selected by the predicate, inside A and outside
    B, was emitted as `in_road_supply` for **B**: a road in B's supply that is not
    in B's window, which is precisely what the three flags exist to prevent.  The
    existing tests never caught it because none of them gave two claiming sites
    different window relationships.

    A missing site in the mapping raises rather than defaulting: a default would
    reintroduce the same silent mislabelling one level down.

    A record is emitted iff its `(site_id, osm_id)` is in `S` **and** its exact
    `(site_id, origin, source_region, osm_id)` was not already written by pass 1.
    """

    for osm_id, intersects_by_site, selected in ways:
        for site_id in closure.sites_claiming(osm_id):
            key = RecordKey(site_id, origin, source_region, osm_id)
            if key in emitted:
                continue
            try:
                intersects = intersects_by_site[site_id]
            except (TypeError, KeyError):
                raise ValueError(
                    f"way {osm_id}: no window relationship given for claiming site "
                    f"{site_id!r}; pass 2 needs one per (site, way) pair"
                ) from None
            yield SiteRecord(
                key=key,
                intersects_window=bool(intersects),
                selected_by_predicate=selected,
            )
