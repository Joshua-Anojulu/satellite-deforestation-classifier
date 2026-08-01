"""The GeoParquet properties §5 and §6.2 are about to be built on.

Round-1 #2 of the Plan A review found that neither `pyarrow` nor another Arrow
consumer was installed, while §6.2 publishes GeoParquet and §5 hashes what it
publishes.  `pyarrow 25.0.0` is now pinned, and these tests exist so the format's
behaviour is a checked property of this environment rather than a claim in a
document -- the failure mode that cost fourteen review rounds.

Two of these are load-bearing for sections not yet written:

`test_writes_are_byte_deterministic` is the property §5's immutable
content-addressed artifact layer rests on.  If the same frame produced different
bytes on each write, every artifact would get a fresh digest and the whole layer
would degrade to append-only storage without anyone noticing.

`test_the_writer_version_is_embedded_in_every_file` proves §8.1's requirement to
put resolved library versions in the cache key is necessary, not precautionary:
byte-identical input data written by a different pyarrow produces a different
artifact hash.
"""

from __future__ import annotations

import hashlib
import json

import geopandas as gpd
import pyarrow
import pyarrow.parquet as pq
import pytest
from shapely.geometry import LineString

#: A per-site UTM, as §6.5 freezes -- the knife-edge site's zone.
SITE_EPSG = 32735

COORDS = ((-63.30, 0.10), (-63.29, 0.1100001), (-63.28, 0.12))


@pytest.fixture
def frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "osm_id": [1, 2],
            "origin": [2020, 2020],
            "intersects_window": [True, False],
            "source_regions": [["norte", "nordeste"], ["norte"]],
            "geometry": [LineString(COORDS), LineString(COORDS[:2])],
        },
        crs=f"EPSG:{SITE_EPSG}",
    )


def digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_writes_are_byte_deterministic(frame, tmp_path) -> None:
    """§5's content-addressed layer needs the same frame to hash the same."""

    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    frame.to_parquet(a)
    frame.to_parquet(b)
    assert digest(a) == digest(b)


def test_the_frozen_crs_survives_the_round_trip(frame, tmp_path) -> None:
    """A radius and a Hausdorff distance in the wrong projection are still
    numbers, so the CRS must come back exactly, not approximately."""

    path = tmp_path / "site.parquet"
    frame.to_parquet(path)
    assert gpd.read_parquet(path).crs.to_epsg() == SITE_EPSG

    geo = json.loads(pq.read_schema(path).metadata[b"geo"])
    assert geo["columns"]["geometry"]["crs"]["id"] == {
        "authority": "EPSG",
        "code": SITE_EPSG,
    }
    assert geo["columns"]["geometry"]["encoding"] == "WKB"


def test_geometry_returns_bitwise_identical_coordinates(frame, tmp_path) -> None:
    """WKB is float64, so §4.3's exact-equality checks survive publication.

    A round-trip that quantised coordinates would make a published record
    compare unequal to the checkpoint it came from.
    """

    path = tmp_path / "site.parquet"
    frame.to_parquet(path)
    assert tuple(gpd.read_parquet(path).geometry[0].coords) == COORDS


def test_the_writer_version_is_embedded_in_every_file(frame, tmp_path) -> None:
    """Why §8.1 puts resolved library versions in the cache key."""

    path = tmp_path / "site.parquet"
    frame.to_parquet(path)
    created_by = pq.ParquetFile(path).metadata.created_by
    assert pyarrow.__version__ in created_by


def test_a_list_column_comes_back_as_an_array_not_a_list(frame, tmp_path) -> None:
    """`source_regions[]` is a list column (§4.1), and it does not round-trip as
    a `list`.  A consumer comparing it to a tuple or a list gets the wrong
    answer without raising."""

    path = tmp_path / "site.parquet"
    frame.to_parquet(path)
    regions = gpd.read_parquet(path).source_regions[0]

    assert not isinstance(regions, list)
    assert list(regions) == ["norte", "nordeste"]
