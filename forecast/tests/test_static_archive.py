"""Static acquisition must derive its inputs and never overstate its pinning."""

from __future__ import annotations

import hashlib
import io

import pytest
from shapely.geometry import box, mapping

from forecast.static_archive import (
    RemoteFile,
    _md5_from_etag,
    build_inventory,
    download_remote,
    head_remote,
    osm_snapshot_url,
    required_osm_regions,
    required_srtm_tiles,
    resolve_available_regions,
    srtm_tile_id,
)


def _feature(region_id, geom, parent=None):
    return {
        "properties": {
            "id": region_id,
            "parent": parent,
            "urls": {"pbf": f"https://download.geofabrik.de/{region_id}-latest.osm.pbf"},
        },
        "geometry": mapping(geom),
    }


def _site(west, south, east, north, cid="S1"):
    return {"west": west, "south": south, "east": east, "north": north, "candidate_id": cid}


# --- region derivation ------------------------------------------------------

def test_most_specific_containing_region_is_chosen():
    index = {"features": [
        _feature("continent", box(-80, -40, -30, 10)),
        _feature("country", box(-65, -25, -55, -15), parent="continent"),
    ]}
    assert required_osm_regions([_site(-61, -21, -60.8, -20.8)], index) == ("country",)


def test_a_border_straddling_site_takes_two_countries_not_the_continent():
    """The real case: one site sits 68%/36% across the Argentina/Bolivia border.

    No country contains it, so the smallest *containing* region is the whole
    continent -- which would be a ~5 GB download for one site.  A union of the
    two countries covers it far more cheaply.
    """

    # The border sits at lat -22; the site spans -22.2..-21.9 and so crosses it,
    # leaving neither country able to contain it on its own.
    index = {"features": [
        _feature("continent", box(-80, -40, -30, 10)),
        _feature("argentina", box(-65, -30, -60, -22), parent="continent"),
        _feature("bolivia", box(-65, -22, -57, -10), parent="continent"),
    ]}
    site = _site(-63.7, -22.2, -63.3, -21.9)
    regions = required_osm_regions([site], index)
    assert set(regions) == {"argentina", "bolivia"}
    assert "continent" not in regions


def test_a_single_small_containing_region_beats_a_union():
    """Non-vacuity control: the union branch must not fire when it is worse."""

    index = {"features": [
        _feature("continent", box(-80, -40, -30, 10)),
        _feature("country", box(-65, -25, -55, -15), parent="continent"),
    ]}
    assert required_osm_regions([_site(-61, -21, -60.8, -20.8)], index) == ("country",)


def test_uncovered_site_fails_closed():
    index = {"features": [_feature("elsewhere", box(0, 0, 10, 10))]}
    with pytest.raises(ValueError, match="no Geofabrik region covers"):
        required_osm_regions([_site(-61, -21, -60.8, -20.8)], index)


def test_no_sites_fails_closed():
    with pytest.raises(ValueError, match="refusing to derive an empty region set"):
        required_osm_regions([], {"features": []})


# --- availability resolution ------------------------------------------------

def test_missing_dated_archive_falls_back_to_the_parent():
    """kalimantan/sumatra have no dated archive before 2022."""

    index = {"features": [
        _feature("indonesia", box(95, -11, 141, 6)),
        _feature("kalimantan", box(108, -4, 119, 4), parent="indonesia"),
    ]}
    def exists(url):
        return "kalimantan" not in url

    resolved = resolve_available_regions(["kalimantan"], index, (2020, 2021, 2022), exists=exists)
    assert set(resolved) == {"indonesia"}


def test_substitution_is_uniform_across_origins():
    """A region available in 2022 but not 2020 must NOT be used for 2022 only.

    Otherwise the roads layer would come from a different extract in test than
    in training, and extract-boundary differences could track the year.
    """

    index = {"features": [
        _feature("indonesia", box(95, -11, 141, 6)),
        _feature("kalimantan", box(108, -4, 119, 4), parent="indonesia"),
    ]}
    def exists(url):
        return "kalimantan" not in url or "220101" in url

    resolved = resolve_available_regions(["kalimantan"], index, (2020, 2021, 2022), exists=exists)
    assert set(resolved) == {"indonesia"}, "partial availability must not be used"


def test_region_available_everywhere_is_kept():
    index = {"features": [_feature("peru", box(-82, -19, -68, 0))]}
    resolved = resolve_available_regions(["peru"], index, (2020, 2021), exists=lambda url: True)
    assert set(resolved) == {"peru"}


def test_no_usable_ancestor_fails_closed():
    index = {"features": [_feature("orphan", box(0, 0, 1, 1))]}
    with pytest.raises(ValueError, match="no ancestor"):
        resolve_available_regions(["orphan"], index, (2020,), exists=lambda url: False)


# --- URLs -------------------------------------------------------------------

def test_snapshot_url_is_january_first_of_T():
    url = "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
    assert osm_snapshot_url(url, 2020).endswith("peru-200101.osm.pbf")
    assert osm_snapshot_url(url, 2022).endswith("peru-220101.osm.pbf")


def test_snapshot_url_rejects_an_unexpected_form():
    with pytest.raises(ValueError, match="unexpected Geofabrik"):
        osm_snapshot_url("https://example/peru.osm.pbf", 2020)


def test_srtm_tile_naming():
    # srtm_26_14 spans lon [-55,-50], lat [-10,-5] -- verified against the real
    # CGIAR tile grid.
    assert srtm_tile_id(-7.5, -52.5) == "srtm_26_14"
    # Row 13 spans lat [-5, 0], so the equator is its top edge.
    assert srtm_tile_id(0.0, 0.0) == "srtm_37_13"


def test_srtm_tiles_are_derived_and_fail_closed():
    tiles = required_srtm_tiles([_site(-61, -11, -60.8, -10.8)])
    assert tiles and all(t.startswith("srtm_") for t in tiles)
    with pytest.raises(ValueError, match="refusing to derive an empty tile set"):
        required_srtm_tiles([])


# --- pinning honesty --------------------------------------------------------

def test_only_a_plain_hex_etag_counts_as_an_md5():
    assert _md5_from_etag('"54237d9cbf19ee48959d87b9b95c3f3e"') == "54237d9cbf19ee48959d87b9b95c3f3e"
    assert _md5_from_etag('"abc-2"') == "", "multipart etags are not md5s"
    assert _md5_from_etag('W/"weak"') == ""
    assert _md5_from_etag(None) == ""


class _Response:
    def __init__(self, body=b"", headers=None):
        self._body = io.BytesIO(body)
        self.headers = headers or {}

    def read(self, size=-1):
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_head_fails_closed_without_a_length():
    with pytest.raises(ValueError, match="no content length"):
        head_remote("roads", "k", "https://example/x", opener=lambda r: _Response(headers={}))


def _remote(body, md5=""):
    return RemoteFile("roads", "k", "https://example/x", 2020, len(body), md5)


def test_truncated_download_never_lands(tmp_path):
    body = b"a complete extract"
    target = tmp_path / "x.pbf"
    with pytest.raises(ValueError, match="length mismatch"):
        download_remote(_remote(body), target, opener=lambda u: _Response(body[:4]))
    assert not target.exists()


def test_publisher_md5_is_checked_when_offered(tmp_path):
    body = b"a complete extract"
    target = tmp_path / "x.pbf"
    wrong = hashlib.md5(b"different").hexdigest()
    with pytest.raises(ValueError, match="md5 mismatch"):
        download_remote(_remote(body, wrong), target, opener=lambda u: _Response(body))
    assert not target.exists()


def test_download_returns_sha256(tmp_path):
    body = b"a complete extract"
    target = tmp_path / "x.pbf"
    digest = download_remote(_remote(body), target, opener=lambda u: _Response(body))
    assert digest == hashlib.sha256(body).hexdigest()
    assert target.read_bytes() == body


def test_inventory_states_the_weaker_anchor_and_counts_publisher_digests():
    records = [
        {"kind": "roads", "key": "peru@2020", "md5": "", "sha256": "a"},
        {"kind": "terrain", "key": "srtm_26_14", "md5": "", "sha256": "b"},
    ]
    inventory = build_inventory(records)
    assert inventory["files_with_publisher_md5"] == 0
    assert "NOT an independent" in inventory["pinning_anchor"]
    assert "sha256 on receipt only" in inventory["pinning_anchor"]


def test_empty_inventory_is_refused():
    with pytest.raises(ValueError, match="empty static inventory"):
        build_inventory([])
