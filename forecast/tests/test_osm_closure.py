"""Tests for the two-pass identity closure (§2.2).

The central test is `test_pass_two_emits_the_other_origin_counterpart`: it is the
positive case that the earlier suppression rule silently destroyed.  Keying
suppression on `(site_id, osm_id)` made pass 2 emit **nothing at all** -- every
pair in `S` is there because pass 1 emitted it in some origin -- so the closure
was inert, the identity edges were simply absent, and nothing raised.  A test
asserting only "no duplicates" would have passed over that hole, which is why
the emission case is asserted directly.
"""

from __future__ import annotations

import pytest

from forecast.osm_closure import (
    ClosureKey,
    ClosureTable,
    RecordKey,
    SiteRecord,
    pass_one_records,
    pass_two_records,
)

SITE_A = "para-01"
SITE_B = "rondonia-02"


def record(site, origin, region, osm_id, intersects=True, selected=True) -> SiteRecord:
    return SiteRecord(
        key=RecordKey(site, origin, region, osm_id),
        intersects_window=intersects,
        selected_by_predicate=selected,
    )


class TestFlags:
    def test_in_window_and_selected_is_a_road(self) -> None:
        r = record(SITE_A, 2020, "norte", 1)
        assert r.in_road_supply is True
        assert r.closure_only is False

    def test_tag_changed_counterpart_carries_all_three_facts(self) -> None:
        """Inside the window, no longer a road: both flags AND closure_only.

        v7's proof said such a record carries `intersects_window` "rather than
        being stamped closure-only".  It is both -- the flags answer different
        questions.
        """

        r = record(SITE_A, 2021, "norte", 1, intersects=True, selected=False)
        assert r.intersects_window is True
        assert r.selected_by_predicate is False
        assert r.closure_only is True
        assert r.in_road_supply is False

    def test_outside_window_but_still_a_road_is_closure_only(self) -> None:
        r = record(SITE_A, 2021, "norte", 1, intersects=False, selected=True)
        assert r.closure_only is True
        assert r.in_road_supply is False

    def test_road_supply_needs_BOTH_flags(self) -> None:
        """`intersects_window` alone would admit a record that is not a road."""

        in_window_not_road = record(SITE_A, 2021, "norte", 1, True, False)
        assert in_window_not_road.intersects_window is True
        assert in_window_not_road.in_road_supply is False


class TestClosureTableKeying:
    def test_keyed_by_pair_not_by_id(self) -> None:
        """A way can be inside site A and outside site B."""

        table = ClosureTable()
        table.add(SITE_A, 42)
        assert ClosureKey(SITE_A, 42) in table
        assert ClosureKey(SITE_B, 42) not in table

    def test_a_counterpart_is_claimed_only_by_sites_that_claim_it(self) -> None:
        table = ClosureTable()
        table.add(SITE_A, 42)
        table.add(SITE_B, 99)
        assert table.sites_claiming(42) == (SITE_A,)
        assert table.sites_claiming(99) == (SITE_B,)
        assert table.sites_claiming(1234) == ()

    def test_table_is_a_set_of_pairs(self) -> None:
        table = ClosureTable()
        table.add(SITE_A, 42)
        table.add(SITE_A, 42)
        table.add(SITE_B, 42)
        assert len(table) == 2


class TestPassOne:
    def test_emits_only_ways_intersecting_the_window(self) -> None:
        out = list(
            pass_one_records(
                origin=2020,
                source_region="norte",
                site_id=SITE_A,
                ways=[(1, True), (2, False), (3, True)],
            )
        )
        assert [r.key.osm_id for r in out] == [1, 3]
        assert all(r.in_road_supply for r in out)


class TestPassTwoClosure:
    def test_pass_two_emits_the_other_origin_counterpart(self) -> None:
        """THE case the old suppression key destroyed.

        Way 42 is in site A's window at origin 2020, so pass 1 emits it and `S`
        gains (A, 42).  At origin 2021 the way has moved far outside the window.
        Pass 2 must still emit it, or the identity edge between the two origins
        cannot exist.
        """

        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        emitted = {RecordKey(SITE_A, 2020, "norte", 42)}  # what pass 1 wrote

        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted=emitted,
                ways=[(42, False, True)],  # far outside the window now
            )
        )

        assert len(out) == 1, "pass 2 must recover the other-origin counterpart"
        assert out[0].key == RecordKey(SITE_A, 2021, "norte", 42)
        assert out[0].intersects_window is False
        assert out[0].closure_only is True

    def test_suppression_on_the_pair_would_have_emitted_nothing(self) -> None:
        """Guards the bug directly: pair-keyed suppression is inert.

        Simulating the old rule -- skip whenever `(site_id, osm_id)` was seen --
        removes the very record the closure exists to produce.
        """

        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        pair_keyed_emitted = {ClosureKey(SITE_A, 42)}

        would_emit = [
            osm_id
            for osm_id in (42,)
            for site in closure.sites_claiming(osm_id)
            if ClosureKey(site, osm_id) not in pair_keyed_emitted
        ]
        assert would_emit == [], "the old rule suppressed everything, silently"

        # The record-keyed rule emits it.
        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted={RecordKey(SITE_A, 2020, "norte", 42)},
                ways=[(42, False, True)],
            )
        )
        assert [r.key.osm_id for r in out] == [42]

    def test_exact_record_already_written_is_suppressed(self) -> None:
        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        emitted = {RecordKey(SITE_A, 2020, "norte", 42)}
        out = list(
            pass_two_records(
                origin=2020,
                source_region="norte",
                closure=closure,
                emitted=emitted,
                ways=[(42, True, True)],
            )
        )
        assert out == [], "pass 2 must not duplicate the exact pass-1 record"

    def test_same_origin_different_region_is_NOT_suppressed(self) -> None:
        """Region is part of the key for the same reason origin is."""

        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        emitted = {RecordKey(SITE_A, 2020, "norte", 42)}
        out = list(
            pass_two_records(
                origin=2020,
                source_region="nordeste",
                closure=closure,
                emitted=emitted,
                ways=[(42, True, True)],
            )
        )
        assert [r.key.source_region for r in out] == ["nordeste"]

    def test_ways_not_in_the_closure_are_ignored(self) -> None:
        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted=set(),
                ways=[(999, True, True)],
            )
        )
        assert out == []

    def test_pass_two_considers_ways_the_predicate_did_not_select(self) -> None:
        """A tag-changed counterpart is exactly what the edge exists to catch."""

        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted=set(),
                ways=[(42, True, False)],  # still there, no longer tagged a road
            )
        )
        assert len(out) == 1
        assert out[0].selected_by_predicate is False
        assert out[0].closure_only is True
        assert out[0].in_road_supply is False

    def test_counterpart_goes_only_to_sites_that_claim_it(self) -> None:
        closure = ClosureTable([ClosureKey(SITE_A, 42)])
        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted=set(),
                ways=[(42, False, True)],
            )
        )
        assert [r.key.site_id for r in out] == [SITE_A]

    def test_one_way_claimed_by_two_sites_yields_two_records(self) -> None:
        closure = ClosureTable([ClosureKey(SITE_A, 42), ClosureKey(SITE_B, 42)])
        out = list(
            pass_two_records(
                origin=2021,
                source_region="norte",
                closure=closure,
                emitted=set(),
                ways=[(42, False, True)],
            )
        )
        assert sorted(r.key.site_id for r in out) == sorted([SITE_A, SITE_B])
