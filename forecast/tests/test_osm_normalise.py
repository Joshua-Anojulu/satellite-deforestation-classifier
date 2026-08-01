"""Tests for the frozen OSM selection predicate (§1.2).

The cases that matter are the ones the review chain actually caught:

* the four lifecycle prefixes a five-extract table was missing, which would have
  silently dropped 309 ways;
* the three keys that occur ONLY alongside an ordinary `highway` tag, which a
  boolean predicate-equality assertion structurally cannot detect;
* an unknown namespace on a way that also carries `highway` -- the exact
  false-negative that motivated checking key membership instead.
"""

from __future__ import annotations

import pytest

from forecast.osm_normalise import (
    DISPOSITION,
    EXCLUDE_KEYS,
    RETAIN_KEYS,
    UnknownHighwayNamespace,
    assert_known_highway_keys,
    observed_highway_keys,
    retains,
)

# Measured corpus counts from the full 36-extract census, kept here so a change
# to the table has to confront the evidence that produced it.  The census counted
# keys ending in `:highway`; the plain `highway` tag is a nineteenth table row and
# is NOT one of them.
CENSUS_SUFFIX_KEYS = 18
CENSUS_SET_DIFFERENCE = 2_740


def test_table_matches_the_census_shape() -> None:
    suffix_keys = [key for key in DISPOSITION if key.endswith(":highway")]
    assert len(suffix_keys) == CENSUS_SUFFIX_KEYS
    assert len(DISPOSITION) == CENSUS_SUFFIX_KEYS + 1  # plus plain `highway`
    assert "highway" in DISPOSITION and not "highway".endswith(":highway")
    assert set(RETAIN_KEYS) | set(EXCLUDE_KEYS) == set(DISPOSITION)
    assert not set(RETAIN_KEYS) & set(EXCLUDE_KEYS)


@pytest.mark.parametrize(
    "key",
    ["destroyed:highway", "former:highway", "removed:highway", "disabled:highway"],
)
def test_lifecycle_prefixes_a_partial_census_missed_are_retained(key: str) -> None:
    """These four appear in the set difference; omitting them dropped 309 ways."""

    assert retains({key: "track"})


@pytest.mark.parametrize("key", EXCLUDE_KEYS)
def test_excluded_namespaces_do_not_retain_on_their_own(key: str) -> None:
    assert not retains({key: "yes"})


def test_excluded_namespace_alongside_highway_is_still_retained() -> None:
    """`source:highway` does not retain, but the way's own `highway` does."""

    assert retains({"highway": "residential", "source:highway": "bing"})


def test_area_highway_is_retained() -> None:
    """Road areas are kept; §1.4 stores them as a ring traversal, not as areas."""

    assert retains({"area:highway": "yes"})


def test_historic_highway_is_retained_because_excluding_it_is_irreversible() -> None:
    assert retains({"historic:highway": "road"})


def test_a_way_with_no_highway_key_is_not_retained() -> None:
    assert not retains({"building": "yes", "source": "bing"})


def test_retains_does_not_scan_tags() -> None:
    """Direct lookup only -- scanning was a 2.6x throughput error, not a style point.

    A mapping that raises on iteration proves membership is tested by `in` alone.
    """

    class LookupOnly(dict):
        def __iter__(self):  # pragma: no cover - invoked only on failure
            raise AssertionError("retains() must not iterate the way's tags")

    assert retains(LookupOnly({"highway": "service"}))
    assert not retains(LookupOnly({"building": "yes"}))


class TestUnknownNamespaceAssertion:
    def test_unknown_namespace_alone_fails_closed(self) -> None:
        with pytest.raises(UnknownHighwayNamespace) as excinfo:
            assert_known_highway_keys({"mystery:highway": "track"}, osm_id=42)
        assert excinfo.value.keys == ("mystery:highway",)
        assert excinfo.value.osm_id == 42

    def test_unknown_namespace_ALONGSIDE_highway_still_fails_closed(self) -> None:
        """The false negative a predicate-equality check cannot see.

        Both predicates are true for this way, so comparing them proves nothing;
        only key membership catches it.
        """

        with pytest.raises(UnknownHighwayNamespace):
            assert_known_highway_keys({"highway": "track", "mystery:highway": "yes"})

    @pytest.mark.parametrize("key", ["indoor:highway", "note:highway", "collapsed:highway"])
    def test_keys_that_only_ever_co_occur_with_highway_are_in_the_table(
        self, key: str
    ) -> None:
        """These three never enter the set difference, so only membership finds them."""

        assert key in DISPOSITION
        assert_known_highway_keys({"highway": "residential", key: "yes"})

    def test_known_keys_pass_and_are_returned(self) -> None:
        observed = assert_known_highway_keys(
            {"highway": "track", "disused:highway": "path", "landuse": "forest"}
        )
        assert observed == ("disused:highway", "highway")

    def test_way_with_no_highway_keys_passes_trivially(self) -> None:
        assert assert_known_highway_keys({"building": "yes"}) == ()


def test_observed_keys_ignore_unrelated_tags() -> None:
    assert observed_highway_keys({"name": "Main St", "surface": "asphalt"}) == ()
    assert observed_highway_keys({"not:highway": "track"}) == ("not:highway",)
