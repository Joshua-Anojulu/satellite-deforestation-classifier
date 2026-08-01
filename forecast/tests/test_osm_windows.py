"""Tests for the site window masks, the frozen UTM, and the processing radius.

Three of these tests exist because building found something fourteen review
rounds of prose did not, and each asserts the **positive** case rather than the
absence of a symptom:

`test_zone_comes_from_the_exact_centre_not_a_polygon_centroid` pins the one site
centred exactly on a UTM zone boundary.  Its exact centre selects zone 35; the
polygon centroid of the same box computes to `23.999999999999655` and selects
zone 34.  Nothing would have raised -- the run would simply have emitted §6.5's
identity-edge metrics in a different projection than the previous run.

`test_clip_yields_every_intersection_shape` asserts the components that come out
of each of the five clip outcomes, including the mixed `GeometryCollection`.  A
test asserting only "no crash" would pass while the collection branch silently
dropped every lineal part inside it.

`test_dispatch_is_exact_not_bounding_box` places a way inside the mask's
*envelope* but outside the mask, and asserts it is dispatched to no site.  With
the `intersects` predicate dropped, the tree still returns it and every
downstream count inflates with ways the guard never retained.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon

from forecast.osm_windows import (
    BUFFER_AZIMUTHS,
    EXTRACTION_GUARD_M,
    RADIUS_SANITY_BAND_M,
    RING_STEP_DEG,
    DegenerateSiteBox,
    WindowDispatch,
    ZoneExceptionRegion,
    build_site_window,
    build_site_windows,
    densified_box_ring,
    geodesic_window,
    utm_epsg,
)

GEOD = Geod(ellps="WGS84")

MANIFEST = (
    Path(__file__).resolve().parents[1] / "artifacts" / "specification_w_manifest.json"
)

#: The site centred at longitude exactly 24.0 -- a UTM zone boundary.
KNIFE_EDGE_SITE = "F2_M002.900_P0024.000"

#: Measured across all 36 sites: three effects push the realised radius off the
#: nominal 5000 m guard, and none of them is a bug.  See the module docstring of
#: `forecast.osm_windows`.
OBSERVED_RADIUS_RANGE_M = (4998.0, 5004.3)


def site(west: float, south: float, east: float, north: float, site_id: str = "t-1"):
    return {
        "candidate_id": site_id,
        "west": west,
        "south": south,
        "east": east,
        "north": north,
    }


@pytest.fixture(scope="module")
def manifest_sites() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["sites"]


@pytest.fixture(scope="module")
def real_windows(manifest_sites) -> tuple:
    """Every Specification W window, built once -- ~0.8 s per site."""

    return build_site_windows(manifest_sites)


@pytest.fixture(scope="module")
def small_window():
    """A small synthetic site, cheap enough to build per module."""

    return build_site_window(site(-63.0, 0.0, -62.98, 0.02))


class TestFrozenCRSRule:
    def test_zone_comes_from_the_exact_centre_not_a_polygon_centroid(self) -> None:
        """The knife-edge case, asserted from both sides.

        The exact arithmetic centre and the polygon centroid of the *same* box
        disagree about the zone.  The build must take the exact one.
        """

        assert utm_epsg(24.0, -2.9) == 32735
        assert utm_epsg(23.999999999999655, -2.9) == 32734

        record = next(
            s
            for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["sites"]
            if s["candidate_id"] == KNIFE_EDGE_SITE
        )
        window = build_site_window(record)
        assert window.centre == (24.0, -2.9)
        assert window.epsg == 32735

        drifted = Polygon(
            densified_box_ring(
                float(record["west"]),
                float(record["south"]),
                float(record["east"]),
                float(record["north"]),
            )
        ).centroid
        assert drifted.x != 24.0
        assert utm_epsg(drifted.x, drifted.y) != window.epsg

    def test_boundary_tie_break_takes_the_eastern_zone(self) -> None:
        assert utm_epsg(-180.0, 0.0) == 32601
        assert utm_epsg(-174.0, 0.0) == 32602
        assert utm_epsg(0.0, 0.0) == 32631

    def test_hemisphere_splits_at_the_equator(self) -> None:
        assert utm_epsg(-63.25, 0.0) == 32620
        assert utm_epsg(-63.25, -0.0001) == 32720

    @pytest.mark.parametrize(
        "lon,lat", [(6.0, 60.0), (9.0, 58.0), (15.0, 78.0), (35.0, 80.0)]
    )
    def test_zone_exception_regions_are_refused_not_guessed(self, lon, lat) -> None:
        """Norway 32V and Svalbard break the plain rule, so the rule refuses."""

        with pytest.raises(ZoneExceptionRegion):
            utm_epsg(lon, lat)

    @pytest.mark.parametrize("lon,lat", [(181.0, 0.0), (0.0, 91.0)])
    def test_out_of_range_centres_are_refused(self, lon, lat) -> None:
        with pytest.raises(ValueError):
            utm_epsg(lon, lat)


class TestBoxRing:
    def test_ring_is_closed_and_densified(self) -> None:
        ring = densified_box_ring(-63.375, 0.07, -63.125, 0.29)
        assert ring[0] == ring[-1] == (-63.375, 0.07)
        assert len(ring) > 4
        assert Polygon(ring).is_valid

    def test_spacing_never_exceeds_the_frozen_step(self) -> None:
        ring = densified_box_ring(-63.375, 0.07, -63.125, 0.29)
        gaps = [
            max(abs(b[0] - a[0]), abs(b[1] - a[1]))
            for a, b in zip(ring, ring[1:])
        ]
        assert max(gaps) <= RING_STEP_DEG + 1e-12

    @pytest.mark.parametrize(
        "box", [(-63.0, 0.0, -63.0, 0.2), (-63.0, 0.2, -62.9, 0.2), (-62.9, 0.0, -63.0, 0.2)]
    )
    def test_degenerate_boxes_are_refused(self, box) -> None:
        with pytest.raises(DegenerateSiteBox):
            densified_box_ring(*box)


class TestGeodesicWindow:
    def test_window_contains_the_box(self) -> None:
        box = Polygon(densified_box_ring(-63.0, 0.0, -62.98, 0.02))
        assert geodesic_window(-63.0, 0.0, -62.98, 0.02).contains(box)

    def test_realised_clearance_is_at_least_the_guard_less_the_notch(self) -> None:
        """The positive statement of what the buffer delivers.

        Azimuth discretisation is one-sided outward by construction, so the only
        inward error is the ring-spacing notch, bounded by
        `r - sqrt(r^2 - (step/2)^2)`.  Measured against real geodesic distances,
        not against the construction that produced them.
        """

        west, south, east, north = -63.0, 0.0, -62.98, 0.02
        window = geodesic_window(west, south, east, north)
        box_ring = densified_box_ring(west, south, east, north, RING_STEP_DEG / 4)

        step_m = GEOD.inv(west, south, west + RING_STEP_DEG, south)[2]
        notch_m = EXTRACTION_GUARD_M - math.sqrt(
            EXTRACTION_GUARD_M**2 - (step_m / 2.0) ** 2
        )
        assert notch_m < 1.0

        clearances = [
            min(GEOD.inv(bx, by, mx, my)[2] for bx, by in box_ring)
            for mx, my in window.exterior.coords
        ]
        assert min(clearances) >= EXTRACTION_GUARD_M - notch_m - 1.0

    def test_a_coarser_fan_is_refused(self) -> None:
        with pytest.raises(ValueError):
            geodesic_window(-63.0, 0.0, -62.98, 0.02, azimuths=4)


class TestProcessingRadius:
    def test_radius_is_the_distance_to_the_mask_boundary(self, small_window) -> None:
        """What the number means, asserted as a reachability statement.

        A query centred anywhere in the box and shorter than the radius cannot
        leave the mask; that is the whole contract Plans B and C consume.
        """

        window = small_window
        radius = window.max_processing_radius_m
        assert radius == pytest.approx(
            window.box_utm.distance(window.mask_utm.exterior), abs=1e-9
        )

        centre = window.box_utm.centroid
        assert window.mask_utm.contains(centre.buffer(radius - 1.0))

        for corner in window.box_utm.exterior.coords:
            assert window.mask_utm.contains(Point(corner).buffer(radius - 1.0))

    def test_radius_is_measured_not_the_nominal_guard(self, small_window) -> None:
        """§2.3 computes this from the realised mask.  It is not 5000.0."""

        assert small_window.max_processing_radius_m != EXTRACTION_GUARD_M
        low, high = RADIUS_SANITY_BAND_M
        assert low < small_window.max_processing_radius_m < high

    def test_a_mask_from_the_wrong_crs_fails_the_stage_closed(self, monkeypatch) -> None:
        """The sanity band exists to catch construction errors, and does."""

        import forecast.osm_windows as mod

        monkeypatch.setattr(mod, "utm_epsg", lambda lon, lat: 32601)
        with pytest.raises(ValueError, match="sanity band"):
            mod.build_site_window(site(-63.0, 0.0, -62.98, 0.02))

    def test_emitted_record_carries_the_metric_and_the_unknown(self, small_window) -> None:
        record = small_window.as_record()
        assert record["max_processing_radius_m"] == small_window.max_processing_radius_m
        assert record["extraction_guard_m"] == EXTRACTION_GUARD_M
        assert record["buffer_azimuths"] == BUFFER_AZIMUTHS
        # Round-8 #2: this metric proves Plan A added no truncation beyond the
        # mask.  It never certifies historical source coverage (§9).
        assert record["roads_source_available"] == "UNKNOWN"


class TestAnchorClipping:
    """§2.3: project first, intersect second, keep positive-length lineal parts."""

    def test_clip_yields_every_intersection_shape(self, small_window) -> None:
        window = small_window
        west, south, east, north = -63.0, 0.0, -62.98, 0.02
        mid_lat = (south + north) / 2.0

        crossing = window.clip_anchor(
            LineString([(west - 0.005, mid_lat), (east + 0.005, mid_lat)])
        )
        assert len(crossing.components) == 1
        assert crossing.total_length_m > 0.0
        assert crossing.is_anchor

        in_out_in = window.clip_anchor(
            LineString(
                [
                    (west + 0.005, mid_lat),
                    (west - 0.005, mid_lat),
                    (west + 0.005, south + 0.005),
                ]
            )
        )
        assert len(in_out_in.components) == 2
        assert all(part.length > 0.0 for part in in_out_in.components)

        mixed = window.clip_anchor(
            LineString(
                [
                    (west + 0.005, north),
                    (west + 0.010, north),
                    (west + 0.005, north + 0.002),
                    (east - 0.002, north + 0.002),
                ]
            )
        )
        assert mixed.components, "the lineal part of a GeometryCollection is the anchor"
        assert all(part.length > 0.0 for part in mixed.components)
        assert not mixed.point_only and not mixed.empty

        touch = window.clip_anchor(
            LineString([(west - 0.005, north + 0.005), (west, north), (west - 0.005, north - 0.005)])
        )
        assert touch.components == ()
        assert touch.point_only is True
        assert touch.empty is False
        assert touch.is_anchor is False

        away = window.clip_anchor(LineString([(west - 1.0, mid_lat), (west - 0.9, mid_lat)]))
        assert away.components == ()
        assert away.empty is True
        assert away.point_only is False

    def test_anchor_is_clipped_to_the_box_not_the_mask(self, small_window) -> None:
        """Every point of every anchor is inside the box by construction."""

        window = small_window
        clip = window.clip_anchor(LineString([(-63.02, 0.01), (-62.96, 0.01)]))
        assert clip.components
        for part in clip.components:
            assert window.box_utm.buffer(1e-6).contains(part)

    def test_anchor_lengths_are_metres_in_the_frozen_utm(self, small_window) -> None:
        """The clip is projected first, so lengths are metres, not degrees."""

        window = small_window
        clip = window.clip_anchor(LineString([(-63.0, 0.01), (-62.98, 0.01)]))
        expected = GEOD.inv(-63.0, 0.01, -62.98, 0.01)[2]
        assert clip.total_length_m == pytest.approx(expected, rel=1e-3)


class TestDispatch:
    def test_a_way_is_dispatched_to_every_window_it_touches(self) -> None:
        """No envelope: emission is to the exact set of windows (round-2 #2)."""

        a = build_site_window(site(-63.00, 0.00, -62.98, 0.02, "a"))
        b = build_site_window(site(-62.85, 0.00, -62.83, 0.02, "b"))
        far = build_site_window(site(-50.00, 0.00, -49.98, 0.02, "far"))
        dispatch = WindowDispatch([a, b, far])

        # The two boxes are ~16 km apart, so their 5 km windows stay disjoint and
        # a hit on both is a real double-dispatch rather than an artefact of the
        # fixture.  Boxes closer than 10 km would share window area by design.
        assert not a.mask.intersects(b.mask)

        both = LineString([(-62.94, 0.01), (-62.89, 0.01)])
        assert dispatch.sites_touching(both) == ("a", "b")
        assert dispatch.sites_touching(LineString([(-62.99, 0.01), (-62.985, 0.01)])) == ("a",)
        assert dispatch.sites_touching(LineString([(0.0, 0.0), (0.1, 0.1)])) == ()

    def test_dispatch_is_exact_not_bounding_box(self) -> None:
        """A way inside the mask envelope but outside the mask goes nowhere.

        The mask is a rounded rectangle, so its envelope corner lies outside it.
        Dropping the `intersects` predicate makes this way dispatch, and every
        downstream count inflates with ways the guard never retained.
        """

        window = build_site_window(site(-63.0, 0.0, -62.98, 0.02))
        dispatch = WindowDispatch([window])
        minx, miny, _, _ = window.mask.bounds

        corner = LineString([(minx, miny), (minx + 1e-5, miny + 1e-5)])
        assert window.mask.envelope.intersects(corner)
        assert not window.mask.intersects(corner)
        assert dispatch.sites_touching(corner) == ()

    def test_intersects_window_flag_agrees_with_dispatch(self) -> None:
        """§2.2's flag and §2's dispatch are the same predicate, not two."""

        window = build_site_window(site(-63.0, 0.0, -62.98, 0.02))
        dispatch = WindowDispatch([window])
        for line in (
            LineString([(-62.99, 0.01), (-62.985, 0.01)]),
            LineString([(-63.5, 0.01), (-63.4, 0.01)]),
            LineString([(-63.02, 0.01), (-62.96, 0.01)]),
        ):
            assert bool(dispatch.sites_touching(line)) == window.intersects_window(line)


class TestSpecificationWSites:
    def test_all_thirty_six_sites_build(self, real_windows) -> None:
        assert len(real_windows) == 36
        assert len({w.site_id for w in real_windows}) == 36
        assert all(w.mask.contains(w.box) for w in real_windows)

    def test_realised_radii_match_the_measured_range(self, real_windows) -> None:
        low, high = OBSERVED_RADIUS_RANGE_M
        radii = [w.max_processing_radius_m for w in real_windows]
        assert low <= min(radii) and max(radii) <= high
        assert len({round(r, 2) for r in radii}) > 1, "the radius is per-site, not a constant"

    def test_every_site_gets_one_frozen_zone(self, real_windows) -> None:
        for window in real_windows:
            assert 32601 <= window.epsg <= 32760
            assert window.epsg == utm_epsg(*window.centre)

    def test_no_two_site_windows_overlap(self, real_windows) -> None:
        """Sites were drawn with a 50 km minimum separation; the 5 km guard
        cannot bring two windows into contact, and a way is never double-counted
        for two sites through a shared mask."""

        for i, a in enumerate(real_windows):
            for b in real_windows[i + 1 :]:
                assert not a.mask.intersects(b.mask)

    def test_dispatch_over_the_real_windows(self, real_windows) -> None:
        dispatch = WindowDispatch(real_windows)
        assert len(dispatch) == 36
        target = dispatch.window(KNIFE_EDGE_SITE)
        inside = LineString(
            [
                (target.centre[0] - 0.001, target.centre[1]),
                (target.centre[0] + 0.001, target.centre[1]),
            ]
        )
        assert dispatch.sites_touching(inside) == (KNIFE_EDGE_SITE,)
        assert dispatch.sites_touching(LineString([(0.0, 45.0), (0.1, 45.1)])) == ()
