"""The §3 entry gate: frozen conditions, and what does and does not authorise.

Implements §3 of `OSM-NORMALISATION-PLAN.md`.

**v3 named a file but no criterion, which is not a gate** (round-3 #3).  The
conditions and their ceilings are frozen here, and every one carries an outcome
of `PASS`, `FAIL` or `NOT_ASSESSED`.

**`NOT_ASSESSED` is a first-class outcome, and it does not authorise.**  The
plan's own table has two such rows -- projected corpus wall-clock, and peak
commit with `S` resident.  A gate that only knew `PASS`/`FAIL` would have to call
an unmeasured condition one or the other, and calling it `PASS` is exactly the
overclaim round-4 #3 caught: the harness measured node decoding, index
construction, the retain-predicate and per-node validation, and did **not**
perform `LineString` construction, mask intersection, dispatch, serialisation,
hashing or publication.  22.5 minutes bounds the parser from below and says
nothing about the stage.

**The measurements are a floor, not an authorisation.**  The corpus run is
authorised only by a re-run of the table through the production
parser-to-committed-region path, recorded as an immutable artifact carrying the
parser source hash, the exact command, input digests, resolved dependency
versions, per-file counters, the resource trace and output digests.  Until that
artifact exists this is evidence the parser is fast enough, not evidence the
stage is -- so :class:`GateReport` refuses to say `authorises_corpus_run` without
one.

**One file passing does not order the other 35** (round-4 #4).  `flex_mem`
switches between sparse and dense representations by node cardinality and node-ID
density; sparse cost scales with node count and dense cost with the largest node
ID, and **neither is ordered by compressed PBF bytes**.  v4's "if
`indonesia-220101` fits, every other file fits" is withdrawn, so enforcement is
per file and node cardinality and maximum node ID are recorded per file, those
being the actual drivers of index size.

**Working set is never a gate** (round-6 #6).  It counts resident pages, so a
run that begins swapping reports a *lower* number.  It is recorded for §10.2's
journal and ignored by the verdict -- a test asserts a wild working-set value
cannot change the outcome.

**Extrapolations are labelled, never scored.**  The corpus projection applies
Indonesia's measured 30,174 ways/MB to all 8641 MB; way density varies by region,
so 260.7 M ways is an estimate.  The 22.5 minutes and 8.22 GB are direct
measurements of one file and are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from forecast.memory_supervisor import (
    AUTHORISATION_CEILING_BYTES,
    HARD_LIMIT_BYTES,
)

#: Frozen ceilings (§3).
PARSER_WALL_CLOCK_CEILING_S = 45 * 60
CORPUS_WALL_CLOCK_CEILING_S = 12 * 3600

#: The file the parser measurement was taken on.
REFERENCE_FILE = "indonesia-220101"

#: Measured on that file, fully validating (§3, §3.2).  Recorded so a re-run can
#: be compared against it rather than against memory.
MEASURED_PARSER_WALL_CLOCK_S = 22.5 * 60
MEASURED_PEAK_COMMIT_BYTES = int(8.22 * 1024**3)
MEASURED_RETAINED_WAYS = 4_839_062


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class GateCondition:
    """One row of §3's table."""

    name: str
    ceiling: float | None
    observed: float | None
    outcome: Outcome
    is_gate: bool = True
    extrapolated: bool = False
    note: str = ""


@dataclass(frozen=True)
class FileCounters:
    """Per-file counters (§3).

    `node_cardinality` and `max_node_id` are recorded because they are the
    actual drivers of `flex_mem` index size -- compressed bytes are not.
    """

    name: str
    node_cardinality: int
    max_node_id: int
    retained_ways: int
    ways_with_complete_geometry: int
    invalid_node_locations: int
    wall_clock_s: float
    peak_commit_bytes: int
    peak_working_set_bytes: int

    @property
    def geometry_availability(self) -> float:
        if not self.retained_ways:
            return 1.0
        return self.ways_with_complete_geometry / self.retained_ways


@dataclass(frozen=True)
class ProductionPathEvidence:
    """The immutable measurement artifact §3 requires before authorisation.

    Nothing here is optional.  A partial artifact would let a corpus run be
    authorised by evidence that cannot be reproduced or attributed.
    """

    parser_source_sha256: str
    command: tuple[str, ...]
    input_digests: Mapping[str, str]
    dependency_versions: Mapping[str, str]
    output_digests: Mapping[str, str]
    covers_full_production_path: bool

    def missing(self) -> tuple[str, ...]:
        absent = [
            name
            for name, value in (
                ("parser_source_sha256", self.parser_source_sha256),
                ("command", self.command),
                ("input_digests", self.input_digests),
                ("dependency_versions", self.dependency_versions),
                ("output_digests", self.output_digests),
            )
            if not value
        ]
        if not self.covers_full_production_path:
            absent.append("covers_full_production_path")
        return tuple(absent)


@dataclass(frozen=True)
class GateReport:
    conditions: tuple[GateCondition, ...]
    files: tuple[FileCounters, ...]
    evidence: ProductionPathEvidence | None = None
    unmeasured: tuple[str, ...] = field(default_factory=tuple)

    @property
    def gating(self) -> tuple[GateCondition, ...]:
        return tuple(c for c in self.conditions if c.is_gate)

    @property
    def failed(self) -> tuple[GateCondition, ...]:
        return tuple(c for c in self.gating if c.outcome is Outcome.FAIL)

    @property
    def not_assessed(self) -> tuple[GateCondition, ...]:
        return tuple(c for c in self.gating if c.outcome is Outcome.NOT_ASSESSED)

    @property
    def authorises_corpus_run(self) -> bool:
        """Every gating condition PASS, and production-path evidence present.

        `NOT_ASSESSED` is not `PASS`.  This is the single place the distinction
        is enforced, and it is the property the whole module exists for.
        """

        if self.failed or self.not_assessed:
            return False
        if self.evidence is None or self.evidence.missing():
            return False
        return True

    def describe(self) -> str:
        lines = []
        for condition in self.conditions:
            tag = "" if condition.is_gate else " (observability only)"
            extra = " [EXTRAPOLATED]" if condition.extrapolated else ""
            lines.append(
                f"{condition.outcome.value:13s} {condition.name}{tag}{extra}"
                + (f" -- {condition.note}" if condition.note else "")
            )
        if not self.authorises_corpus_run:
            reasons = []
            if self.failed:
                reasons.append(f"{len(self.failed)} failed")
            if self.not_assessed:
                reasons.append(f"{len(self.not_assessed)} not assessed")
            if self.evidence is None:
                reasons.append("no production-path evidence")
            elif self.evidence.missing():
                reasons.append(f"evidence missing {list(self.evidence.missing())}")
            lines.append("NOT AUTHORISED: " + "; ".join(reasons))
        return "\n".join(lines)


def _scored(name: str, observed: float | None, ceiling: float, **kwargs) -> GateCondition:
    if observed is None:
        return GateCondition(name, ceiling, None, Outcome.NOT_ASSESSED, **kwargs)
    outcome = Outcome.PASS if observed <= ceiling else Outcome.FAIL
    return GateCondition(name, ceiling, observed, outcome, **kwargs)


def evaluate_gate(
    files: Sequence[FileCounters],
    *,
    evidence: ProductionPathEvidence | None = None,
    projected_corpus_wall_clock_s: float | None = None,
    pass_two_peak_commit_bytes: int | None = None,
    corpus_projection_is_extrapolated: bool = True,
) -> GateReport:
    """Score §3's table over per-file counters.

    Every memory and timing condition is enforced **per file**: the worst
    observation decides, because compressed size does not order index cost.
    """

    if not files:
        raise ValueError("the entry gate needs at least one measured file")

    conditions: list[GateCondition] = []

    slowest = max(files, key=lambda f: f.wall_clock_s)
    conditions.append(
        _scored(
            "parser wall-clock, pass 1 (worst file)",
            slowest.wall_clock_s,
            PARSER_WALL_CLOCK_CEILING_S,
            note=f"{slowest.name}",
        )
    )

    conditions.append(
        _scored(
            "projected corpus wall-clock, both passes",
            projected_corpus_wall_clock_s,
            CORPUS_WALL_CLOCK_CEILING_S,
            extrapolated=corpus_projection_is_extrapolated,
            note="an estimate; way density varies by region",
        )
    )

    hungriest = max(files, key=lambda f: f.peak_commit_bytes)
    conditions.append(
        _scored(
            "peak commit charge, pass 1 (worst file)",
            hungriest.peak_commit_bytes,
            AUTHORISATION_CEILING_BYTES,
            note=f"{hungriest.name}; hard backstop {HARD_LIMIT_BYTES}",
        )
    )

    conditions.append(
        _scored(
            "peak commit charge with S resident, pass 2",
            pass_two_peak_commit_bytes,
            AUTHORISATION_CEILING_BYTES,
            note="re-measure on the file with pass 1's maximum observed commit",
        )
    )

    worst_geometry = min(files, key=lambda f: f.geometry_availability)
    conditions.append(
        GateCondition(
            name="geometry availability",
            ceiling=1.0,
            observed=worst_geometry.geometry_availability,
            outcome=(
                Outcome.PASS
                if worst_geometry.geometry_availability >= 1.0
                else Outcome.FAIL
            ),
            note=f"{worst_geometry.name}",
        )
    )

    invalid = sum(f.invalid_node_locations for f in files)
    conditions.append(
        GateCondition(
            name="ways with a missing or invalid node location",
            ceiling=0,
            observed=invalid,
            outcome=Outcome.PASS if invalid == 0 else Outcome.FAIL,
        )
    )

    peak_working_set = max(f.peak_working_set_bytes for f in files)
    conditions.append(
        GateCondition(
            name="peak working set",
            ceiling=None,
            observed=peak_working_set,
            outcome=Outcome.PASS,
            is_gate=False,
            note="observability only; it falls when the process starts paging",
        )
    )

    conditions.append(
        GateCondition(
            name="temporary index disk",
            ceiling=0,
            observed=0,
            outcome=Outcome.PASS,
            note="flex_mem is the sole backend; there is no index file",
        )
    )

    return GateReport(
        conditions=tuple(conditions),
        files=tuple(files),
        evidence=evidence,
        unmeasured=tuple(
            c.name for c in conditions if c.is_gate and c.outcome is Outcome.NOT_ASSESSED
        ),
    )
