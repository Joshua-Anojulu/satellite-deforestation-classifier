"""OSM way selection for the Specification W road-network cache.

Implements §1.2 of `OSM-NORMALISATION-PLAN.md`: which ways are retained from the
36 dated `.osm.pbf` extracts, and the assertion that stops the population
drifting when OpenStreetMap grows a namespace we have never seen.

Three things here are measured rather than assumed, and the measurements are what
make the module short:

**The disposition table is a census result, not a guess.**  Every tag key ending
in `:highway` across all 36 extracts was enumerated -- 34,764,774 retained ways,
18 distinct keys, and a *set difference* of 2,740 ways whose retention actually
depends on the choice.  An earlier table frozen from only five extracts was
missing four standard lifecycle prefixes (`destroyed:`, `former:`, `removed:`,
`disabled:`), which would have **silently dropped 309 ways**.

**The assertion is on KEY MEMBERSHIP, not on predicate equality.**  Comparing a
frozen predicate against a `:highway`-suffix reference predicate compares two
*booleans*, so a way carrying `mystery:highway` **and** an ordinary `highway` tag
satisfies both and the unknown namespace passes unseen.  That is not
hypothetical: `indoor:highway` (86), `note:highway` (9) and `collapsed:highway`
(3) occur in this corpus *only* alongside `highway`, so a boolean check could
never have found them.  :func:`assert_known_highway_keys` therefore checks that
every observed key is in the table, whatever else the way carries.

**Membership is tested by direct lookup, never by scanning the way's tags.**  A
generator over every tag of every non-highway way was the bug that made an early
benchmark report 17,849 ways/s where direct lookups reach 46,467 -- a 2.6x error
that sent the design down a blind alley for two revisions.

Exclusion is limited to unambiguously non-road namespaces.  `historic:highway` is
documented as inconsistently used and can mark a previously valid carriageway, so
dropping it would be a scientific judgement made in the infrastructure layer --
and an irreversible one, since the record would never reach Plan B.
"""

from __future__ import annotations

from typing import Iterable, Mapping

#: The road tag itself.
HIGHWAY = "highway"

#: Keys whose presence retains a way, from the full 36-extract census (§1.2).
#: Ordered as in the plan's table: the road tag, then lifecycle prefixes by
#: corpus frequency.  `area:highway` is the established tagging for road *areas*
#: and is retained; §1.4 stores such ways as their ring traversal with
#: `is_closed` set, and Plan A emits no area semantics.
RETAIN_KEYS: tuple[str, ...] = (
    HIGHWAY,
    "abandoned:highway",
    "area:highway",
    "disused:highway",
    "construction:highway",
    "proposed:highway",
    "demolished:highway",
    "destroyed:highway",
    "was:highway",
    "former:highway",
    "razed:highway",
    "removed:highway",
    "disabled:highway",
    "collapsed:highway",
    "historic:highway",
)

#: Keys observed in the corpus that do NOT retain a way.  Each is unambiguously
#: not a carriageway: provenance metadata, a negative assertion, indoor
#: navigation, or free text.
EXCLUDE_KEYS: tuple[str, ...] = (
    "source:highway",
    "not:highway",
    "indoor:highway",
    "note:highway",
)

#: Every `*:highway` key the census observed, mapped to its frozen disposition.
#: A key absent from this mapping is a namespace this corpus has never contained;
#: encountering one is a stage failure, not a default.
DISPOSITION: Mapping[str, bool] = {
    **{key: True for key in RETAIN_KEYS},
    **{key: False for key in EXCLUDE_KEYS},
}

#: Suffix used only to *detect* unknown namespaces in the assertion below.  It is
#: never used as the selection rule -- a suffix rule silently absorbs any future
#: `<anything>:highway`, including the metadata ones.
_HIGHWAY_SUFFIX = ":highway"


class UnknownHighwayNamespace(Exception):
    """An observed `*:highway` key is absent from the frozen disposition table.

    Raised rather than defaulted.  A new namespace changes which ways the cache
    contains, so it must be classified deliberately and the table re-frozen.
    """

    def __init__(self, keys: Iterable[str], osm_id: int | None = None) -> None:
        self.keys = tuple(sorted(keys))
        self.osm_id = osm_id
        where = f" on way {osm_id}" if osm_id is not None else ""
        super().__init__(
            f"unknown *:highway namespace{where}: {', '.join(self.keys)}. "
            "Classify it in forecast.osm_normalise.DISPOSITION and re-freeze the "
            "census before running the corpus."
        )


def retains(tags: Mapping[str, str]) -> bool:
    """True if this way belongs in the cache, by direct lookup over the table.

    `tags` may be a plain mapping or a pyosmium `TagList`; both support `in`.
    """

    for key in RETAIN_KEYS:
        if key in tags:
            return True
    return False


def _tag_keys(tags: Mapping[str, str]) -> Iterable[str]:
    """Key strings from either a plain mapping or an osmium ``TagList``.

    Iterating a ``TagList`` yields ``Tag`` objects, not keys -- a difference that
    only shows up against the real parser, which is why the stream tests build
    actual ``.osm.pbf`` fixtures instead of passing dicts.
    """

    for item in tags:
        yield getattr(item, "k", item)


def observed_highway_keys(tags: Mapping[str, str]) -> tuple[str, ...]:
    """Every key on this way that ends in `:highway`, plus `highway` itself.

    This *does* scan the way's tags, which is why it belongs in the assertion
    path and not in :func:`retains`.
    """

    found = [key for key in _tag_keys(tags) if key.endswith(_HIGHWAY_SUFFIX)]
    if HIGHWAY in tags:
        found.append(HIGHWAY)
    return tuple(sorted(found))


def assert_known_highway_keys(
    tags: Mapping[str, str], osm_id: int | None = None
) -> tuple[str, ...]:
    """Fail closed if the way carries a `*:highway` key outside the table.

    Returns the observed keys so a caller can record the census as it parses.
    Deliberately independent of :func:`retains`: an unknown namespace on a way
    that *also* carries `highway` is exactly the case a predicate-equality check
    cannot see, and it is the case this corpus actually contains.
    """

    observed = observed_highway_keys(tags)
    unknown = [key for key in observed if key not in DISPOSITION]
    if unknown:
        raise UnknownHighwayNamespace(unknown, osm_id)
    return observed
