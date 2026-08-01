"""Site window masks, the frozen per-site UTM, and the processing radius.

Implements §2.1, §2.3 and §2's window dispatch of `OSM-NORMALISATION-PLAN.md`,
and freezes the CRS rule §6.5 will reuse for identity-edge metrics.

**No envelope.**  The nine Indonesian site boxes total 0.495 deg² inside a 99.83
deg² envelope -- 202x oversized -- and clustering only reaches 110x, so no
rectangle works (round-2 #2).  Every way is tested against the *exact set* of
site window polygons as it streams and dispatched to each window it touches.

**The buffer is geodesic, and that is what makes §2.1 -> §6.5 acyclic.**  §6.5
takes the UTM zone from the window centroid, so a mask built *in* UTM would need
the projection before the window that defines it exists.  A geodesic buffer runs
on the ellipsoid and needs no projection, which breaks the circle.

**`max_processing_radius_m` is measured, never assumed to be 5000.**  Three
independent effects push the realised value off the nominal guard, and all three
were measured rather than reasoned about:

* Azimuth discretisation.  A polygonal circle inscribed in the true circle would
  cut *inward*, so the build radius is the circumscribed one, `r / cos(pi/N)`,
  which keeps that error one-sided and outward.
* Ring spacing.  Adjacent circles leave a shallow notch between their centres;
  at `RING_STEP_DEG` the notch depth is under 0.1 m, bounded by
  `r - sqrt(r^2 - (step/2)^2)`.
* The UTM point scale factor.  Near a central meridian `k = 0.9996`, so 5000
  ground metres measure ~4998 projected metres; near a zone edge `k > 1` and it
  reads long.

Across the 36 Specification W sites the realised radius spans **4998.01 m to
5004.23 m**.  §2.3 defines this as the largest radius for which a query centred
anywhere in the site box cannot reach outside the data Plan A retained, computed
from the *realised* mask -- so the per-site measurement is the contract number,
and no site is promised a flat 5000 m.  Round-8 #2 already cut a completeness
claim out of this metric's name; inventing a guarantee here would put one back.

**The zone rule is applied to the exact arithmetic box centre, not to a computed
centroid, and this is not a stylistic preference.**  Site
`F2_M002.900_P0024.000` is centred at longitude **exactly 24.0**, which is a UTM
zone boundary.  Its exact centre selects zone 35; the *polygon* centroid of the
same box computes to `23.999999999999655` and selects zone 34.  The frozen
projection for that site therefore flips on floating-point summation order, and
a Shapely upgrade could flip it back.  `max_processing_radius_m` happens to be
identical either way (5004.2251 m, by symmetry), but §6.5's identity-edge
metrics -- `min_distance_m`, `hausdorff_m`, every `iou_tau` -- are *not*
symmetric under the choice: the same input would emit different metre values
across runs.  The centre is computed exactly and the boundary tie-break is
stated below, so the zone is a function of the manifest alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, Sequence

from pyproj import CRS, Geod, Transformer
from shapely import STRtree
from shapely.geometry import LineString, Polygon
from shapely.ops import transform as shapely_transform, unary_union

#: §2.1, frozen: a site window is its site box buffered by 5000 m, geodesically.
EXTRACTION_GUARD_M = 5000.0

#: Frozen buffer discretisation.  Both numbers are part of the contract, not
#: library defaults -- §6.5 froze buffer parameters for the same reason.
RING_STEP_DEG = 0.0005
BUFFER_AZIMUTHS = 90

#: Sanity band on the realised radius.  Wide enough to admit the measured
#: 4998.01-5004.23 m spread with room, tight enough that a wrong CRS, a missing
#: buffer or a degenerate box fails the stage closed instead of emitting a
#: plausible number.
RADIUS_SANITY_BAND_M = (4950.0, 5050.0)

GEOD = Geod(ellps="WGS84")

_WGS84 = "EPSG:4326"


class ZoneExceptionRegion(Exception):
    """The centre falls in a region where the plain UTM zone rule is wrong.

    Norway's zone 32V and the Svalbard widenings break `floor((lon+180)/6)+1`.
    No Specification W site is anywhere near them -- the 36 sites span latitudes
    -23.25 to 18.33 -- so the rule is *refused* rather than silently applied, and
    a future site in those bands surfaces as an error instead of a quietly wrong
    projection.
    """


class DegenerateSiteBox(Exception):
    """A site box with non-positive extent in either axis."""


def utm_epsg(lon: float, lat: float) -> int:
    """The frozen per-site CRS rule (§6.5): one UTM zone, from the window centre.

    **Boundary tie-break, frozen:** a centre lying exactly on a zone boundary
    takes the eastern (higher-numbered) zone, which is what the floor rule
    yields for the exact value.  Callers must pass the exact arithmetic centre;
    passing a polygon centroid reintroduces the flip described in the module
    docstring.
    """

    if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
        raise ValueError(f"centre out of range: ({lon}, {lat})")
    if 56.0 <= lat < 64.0 and 3.0 <= lon < 12.0:
        raise ZoneExceptionRegion(f"Norway zone 32V exception at ({lon}, {lat})")
    if 72.0 <= lat < 84.0 and 0.0 <= lon < 42.0:
        raise ZoneExceptionRegion(f"Svalbard zone exception at ({lon}, {lat})")

    zone = int(math.floor((lon + 180.0) / 6.0) % 60) + 1
    return (32600 if lat >= 0.0 else 32700) + zone


def densified_box_ring(
    west: float,
    south: float,
    east: float,
    north: float,
    step_deg: float = RING_STEP_DEG,
) -> tuple[tuple[float, float], ...]:
    """The site box boundary, densified, closed, counter-clockwise from (W, S).

    Densification is not cosmetic.  A box has four corners in lon/lat but its
    edges are *curves* in UTM, so projecting four corners and joining them with
    straight lines would clip the box's own area; and the geodesic buffer places
    a circle at every ring vertex, so ring spacing sets the notch depth.
    """

    if east <= west or north <= south:
        raise DegenerateSiteBox(f"box ({west}, {south}, {east}, {north}) is empty")
    if step_deg <= 0.0:
        raise ValueError(f"step_deg must be positive, got {step_deg}")

    points: list[tuple[float, float]] = []

    def edge(x0: float, y0: float, x1: float, y1: float) -> None:
        span = max(abs(x1 - x0), abs(y1 - y0))
        steps = max(1, int(math.ceil(span / step_deg)))
        for i in range(steps):
            points.append((x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps))

    edge(west, south, east, south)
    edge(east, south, east, north)
    edge(east, north, west, north)
    edge(west, north, west, south)
    points.append((west, south))
    return tuple(points)


def geodesic_window(
    west: float,
    south: float,
    east: float,
    north: float,
    *,
    radius_m: float = EXTRACTION_GUARD_M,
    step_deg: float = RING_STEP_DEG,
    azimuths: int = BUFFER_AZIMUTHS,
) -> Polygon:
    """The §2.1 extraction guard: the site box buffered `radius_m` geodesically.

    Built as the union of the box with a geodesic circle at every densified ring
    vertex.  The circles use the **circumscribed** radius so azimuth
    discretisation can only push the boundary outward, never inward.
    """

    if azimuths < 8:
        raise ValueError(f"azimuths must be at least 8, got {azimuths}")
    if radius_m <= 0.0:
        raise ValueError(f"radius_m must be positive, got {radius_m}")

    ring = densified_box_ring(west, south, east, north, step_deg)
    build_radius = radius_m / math.cos(math.pi / azimuths)
    bearings = [360.0 * i / azimuths for i in range(azimuths)]

    parts: list[Polygon] = [Polygon(ring)]
    for lon, lat in ring:
        fan_lon, fan_lat, _ = GEOD.fwd(
            [lon] * azimuths, [lat] * azimuths, bearings, [build_radius] * azimuths
        )
        parts.append(Polygon(zip(fan_lon, fan_lat)))

    window = unary_union(parts)
    if not isinstance(window, Polygon):
        raise ValueError(f"window is not a single polygon: {window.geom_type}")
    return window


@dataclass(frozen=True, eq=False)
class AnchorClip:
    """§2.3's anchor domain for one way at one site: geometry clipped to the box.

    The clip is **projected first, intersected second** (round-7 #5).  The order
    is frozen because clipping is not closed over `LineString`: intersecting a
    winding way with a box yields a `LineString`, a `MultiLineString`, a
    point-only touch, a `GeometryCollection` of mixed types, or empty.  All five
    were confirmed against the installed Shapely rather than assumed.

    Point-only and empty intersections are **excluded and flagged, never
    silently dropped** -- without this, two conforming Plan B implementations
    would generate different candidate sets from the same input.
    """

    components: tuple[LineString, ...]
    point_only: bool
    empty: bool

    @property
    def is_anchor(self) -> bool:
        return bool(self.components)

    @property
    def total_length_m(self) -> float:
        return sum(component.length for component in self.components)


@dataclass(frozen=True, eq=False)
class SiteWindow:
    """One site's frozen mask, projection and processing radius."""

    site_id: str
    epsg: int
    centre: tuple[float, float]
    box: Polygon
    mask: Polygon
    box_utm: Polygon
    mask_utm: Polygon
    max_processing_radius_m: float

    def to_utm(self, geometry):
        """Project a lon/lat geometry into this site's frozen UTM."""

        return shapely_transform(_transformer(self.epsg).transform, geometry)

    def intersects_window(self, geometry) -> bool:
        """§2.2's `intersects_window` flag: does the geometry meet this mask?"""

        return self.mask.intersects(geometry)

    def clip_anchor(self, geometry) -> AnchorClip:
        """Clip a lon/lat way to this site's anchor domain (§2.3)."""

        clipped = self.to_utm(geometry).intersection(self.box_utm)
        components = tuple(
            part
            for part in lineal_parts(clipped)
            if part.length > 0.0
        )
        return AnchorClip(
            components=components,
            point_only=not components and not clipped.is_empty,
            empty=clipped.is_empty,
        )

    def as_record(self) -> dict[str, object]:
        """The per-site row emitted alongside the mask (§2.3)."""

        return {
            "site_id": self.site_id,
            "epsg": self.epsg,
            "centre_lon": self.centre[0],
            "centre_lat": self.centre[1],
            "extraction_guard_m": EXTRACTION_GUARD_M,
            "max_processing_radius_m": self.max_processing_radius_m,
            "buffer_step_deg": RING_STEP_DEG,
            "buffer_azimuths": BUFFER_AZIMUTHS,
            # §2.3 / round-8 #2: this measures Plan A's own processing boundary
            # and nothing more.  §9 leaves historical extract coverage UNKNOWN.
            "roads_source_available": "UNKNOWN",
            "radius_metric": "site UTM, the projection Plan B measures in",
        }


def lineal_parts(geometry) -> Iterator[LineString]:
    """Walk any intersection result and yield only its lineal pieces.

    Clipping is not closed over `LineString`: intersecting one with a polygon
    yields a `LineString`, a `MultiLineString`, a point-only touch, a mixed
    `GeometryCollection` or empty -- all five confirmed against the installed
    Shapely.  §6's coverage metrics intersect against a buffer and hit the same
    set of outcomes, so both callers walk results through this one definition.
    """

    if geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        yield geometry
        return
    for part in getattr(geometry, "geoms", ()):
        yield from lineal_parts(part)


_TRANSFORMERS: dict[int, Transformer] = {}


def _transformer(epsg: int) -> Transformer:
    transformer = _TRANSFORMERS.get(epsg)
    if transformer is None:
        transformer = Transformer.from_crs(_WGS84, CRS.from_epsg(epsg), always_xy=True)
        _TRANSFORMERS[epsg] = transformer
    return transformer


def build_site_window(site: Mapping[str, object]) -> SiteWindow:
    """Build one site's window from its Specification W manifest record."""

    site_id = str(site["candidate_id"])
    west, south = float(site["west"]), float(site["south"])
    east, north = float(site["east"]), float(site["north"])

    # The exact arithmetic centre -- see the module docstring on why this must
    # not be a polygon centroid.
    centre = ((west + east) / 2.0, (south + north) / 2.0)
    epsg = utm_epsg(*centre)

    box = Polygon(densified_box_ring(west, south, east, north))
    mask = geodesic_window(west, south, east, north)

    project = _transformer(epsg).transform
    box_utm = shapely_transform(project, box)
    mask_utm = shapely_transform(project, mask)

    # inf distance(site_box, complement(mask)).  The complement's frontier is the
    # mask boundary, and the box lies strictly inside, so this is the distance
    # from the box to the mask's exterior ring -- exact for these polygons.
    radius = box_utm.distance(mask_utm.exterior)

    low, high = RADIUS_SANITY_BAND_M
    if not low <= radius <= high:
        raise ValueError(
            f"{site_id}: max_processing_radius_m {radius:.2f} m outside the "
            f"sanity band [{low}, {high}] -- the mask or the CRS is wrong"
        )

    return SiteWindow(
        site_id=site_id,
        epsg=epsg,
        centre=centre,
        box=box,
        mask=mask,
        box_utm=box_utm,
        mask_utm=mask_utm,
        max_processing_radius_m=radius,
    )


def build_site_windows(sites: Iterable[Mapping[str, object]]) -> tuple[SiteWindow, ...]:
    """Build every site window, refusing duplicate site ids."""

    windows = tuple(build_site_window(site) for site in sites)
    ids = [window.site_id for window in windows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate site ids in the manifest")
    return windows


class WindowDispatch:
    """§2's dispatch: every way tested against the exact set of site windows.

    A way is emitted to **every** window it touches, never to a covering
    rectangle.  The `STRtree` is an acceleration structure only -- the
    `intersects` predicate makes the answer exact, so a bounding-box hit that
    misses the mask is not dispatched.
    """

    def __init__(self, windows: Sequence[SiteWindow]) -> None:
        self._windows = tuple(windows)
        self._tree = STRtree([window.mask for window in self._windows])

    def __len__(self) -> int:
        return len(self._windows)

    def sites_touching(self, geometry) -> tuple[str, ...]:
        """Site ids whose window this lon/lat geometry meets, sorted."""

        hits = self._tree.query(geometry, predicate="intersects")
        return tuple(sorted(self._windows[int(i)].site_id for i in hits))

    def window(self, site_id: str) -> SiteWindow:
        for window in self._windows:
            if window.site_id == site_id:
                return window
        raise KeyError(site_id)
