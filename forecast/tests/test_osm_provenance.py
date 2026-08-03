"""§7 header provenance, including the origin that has none.

The corpus survey is the point of this module: `osmosis_replication_timestamp`
is present in all 24 of the 2021 and 2022 extracts and in **none** of the 12
from 2020, so §7's "nominal archive-date window derived from all 36 real
headers" cannot be derived, and a third of the published dataset has no
authoritative vintage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forecast.osm_provenance import (
    ABSENT,
    ProvenanceSurvey,
    ProvenanceUnavailable,
    RegionProvenance,
    read_provenance,
    survey,
)


def provenance(region: str, origin: str, timestamp: str) -> RegionProvenance:
    return RegionProvenance(
        name=f"{region}-{origin[2:]}0101",
        origin=origin,
        region=region,
        header_timestamp=timestamp,
        replication_base_url="http://download.geofabrik.de/x-updates",
        generator="osmium/1.14.0",
    )


REGIONS = ("argentina", "bolivia", "norte")


def corpus_like() -> ProvenanceSurvey:
    """The shape the real corpus has: 2020 absent, 2021 and 2022 present."""

    rows = []
    rows += [provenance(r, "2020", ABSENT) for r in REGIONS]
    rows += [provenance(r, "2021", "2021-01-01T21:42:03Z") for r in REGIONS]
    rows += [provenance(r, "2022", "2022-01-01T21:21:26Z") for r in REGIONS]
    return ProvenanceSurvey(tuple(rows))


def test_an_absent_field_is_not_authoritative_and_is_not_substituted():
    absent = provenance("norte", "2020", ABSENT)
    present = provenance("norte", "2021", "2021-01-01T21:42:03Z")

    assert absent.authoritative is False
    assert absent.header_timestamp == ABSENT, (
        "a missing field must stay ABSENT -- never a filename date or a guess"
    )
    assert present.authoritative is True


def test_the_survey_reports_the_origin_with_no_authority():
    surveyed = corpus_like()

    assert surveyed.origins_without_authority == ("2020",)
    assert "NO AUTHORITATIVE HEADER" in surveyed.describe()
    assert "2020" in surveyed.describe()


def test_an_origin_shares_one_timestamp_across_its_regions():
    """Geofabrik cuts one planet snapshot per origin, so agreement is expected."""

    surveyed = corpus_like()

    assert surveyed.origin_timestamp("2021") == "2021-01-01T21:42:03Z"
    assert surveyed.origin_timestamp("2022") == "2022-01-01T21:21:26Z"
    assert surveyed.origin_timestamp("2020") == ABSENT


def test_regions_from_different_snapshots_raise_rather_than_picking_one():
    """Disagreement means the origin is not one vintage.

    Returning any single timestamp would assert a vintage the data does not
    support, which is precisely the claim §7 exists to constrain.
    """

    mixed = ProvenanceSurvey(
        (
            provenance("argentina", "2021", "2021-01-01T21:42:03Z"),
            provenance("bolivia", "2021", "2021-06-14T03:00:00Z"),
        )
    )

    with pytest.raises(ProvenanceUnavailable, match="different snapshots"):
        mixed.origin_timestamp("2021")


def test_the_survey_counts_authoritative_regions():
    document = corpus_like().document()

    assert document["total_regions"] == 9
    assert document["authoritative_regions"] == 6
    assert document["origins_without_authority"] == ["2020"]


def test_reading_a_real_extract_header(tmp_path):
    """A written PBF carries no replication timestamp, which must read as ABSENT.

    `osmium`'s writer emits no `osmosis_replication_timestamp`, so this is the
    missing-field path exercised against a real file rather than a stub.
    """

    import osmium

    path = tmp_path / "testland-200101.osm.pbf"
    writer = osmium.SimpleWriter(str(path))
    writer.add_node(osmium.osm.mutable.Node(id=1, location=(0.0, 0.0), version=1))
    writer.close()

    result = read_provenance(path)

    assert result.origin == "2020"
    assert result.region == "testland"
    assert result.header_timestamp == ABSENT
    assert result.authoritative is False
    assert result.generator, "the generator field is still recorded"


def test_an_unreadable_file_raises_rather_than_reporting_absent(tmp_path):
    """A corrupt file is a different failure from an empty field."""

    broken = tmp_path / "testland-200101.osm.pbf"
    broken.write_bytes(b"this is not a pbf")

    with pytest.raises(ProvenanceUnavailable):
        read_provenance(broken)
