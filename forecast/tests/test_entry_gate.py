"""Tests for the §3 entry gate, the commit probe, and the supervised child.

`test_a_not_assessed_condition_does_not_authorise` is the central one.  Round-4
#3 caught v4 presenting parser measurements as though they authorised the corpus
run; the plan's own table has two `NOT_ASSESSED` rows, and a gate that collapsed
them into `PASS` would reproduce exactly that overclaim with a green check beside
it.

`test_a_fully_measured_table_with_evidence_authorises` is its necessary
counterpart.  A suite that only asserted "does not authorise" would pass over a
gate that can never authorise anything, which is the same silent-emptiness
failure the §2.2 suppression rule had.

`test_the_supervisor_terminates_on_the_guaranteed_notification` is the kill-test
for the mechanism round-7 #4 and round-8 #9 both got wrong in prose.
"""

from __future__ import annotations

import sys

import pytest

from forecast.entry_gate import (
    CORPUS_WALL_CLOCK_CEILING_S,
    PARSER_WALL_CLOCK_CEILING_S,
    FileCounters,
    GateReport,
    Outcome,
    ProductionPathEvidence,
    evaluate_gate,
)
from forecast.memory_supervisor import (
    AUTHORISATION_CEILING_BYTES,
    HARD_LIMIT_BYTES,
    MemorySupervisedJob,
    run_supervised,
)
from forecast.process_memory import (
    ProcessMemoryUnavailable,
    process_memory,
    validate_probe,
)

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="the §3 mechanism is Windows-specific"
)

GB = 1024**3

#: Shared by the breach and no-breach supervised tests.  Well above the ~10 MB
#: this interpreter commits at startup, so crossing it means the child allocated.
THRESHOLD_BYTES = 256 * 1024 * 1024

ALLOCATE = (
    "b = bytearray({mb} * 1024 * 1024)\n"
    "for i in range(0, len(b), 4096): b[i] = 1\n"
)


def counters(
    name: str = "indonesia-220101",
    *,
    wall_clock_s: float = 22.5 * 60,
    peak_commit_bytes: int = int(8.22 * GB),
    retained: int = 4_839_062,
    complete: int | None = None,
    invalid: int = 0,
    node_cardinality: int = 43_250_208,
    max_node_id: int = 11_000_000_000,
    peak_working_set_bytes: int = int(6.58 * GB),
) -> FileCounters:
    return FileCounters(
        name=name,
        node_cardinality=node_cardinality,
        max_node_id=max_node_id,
        retained_ways=retained,
        ways_with_complete_geometry=retained if complete is None else complete,
        invalid_node_locations=invalid,
        wall_clock_s=wall_clock_s,
        peak_commit_bytes=peak_commit_bytes,
        peak_working_set_bytes=peak_working_set_bytes,
    )


def evidence(**overrides) -> ProductionPathEvidence:
    base = {
        "parser_source_sha256": "a" * 64,
        "command": ("python", "-m", "forecast.osm_stream"),
        "input_digests": {"indonesia-220101.osm.pbf": "b" * 64},
        "dependency_versions": {"osmium": "4.3.1", "pyarrow": "25.0.0"},
        "output_digests": {"norte-2020.parquet": "c" * 64},
        "covers_full_production_path": True,
    }
    base.update(overrides)
    return ProductionPathEvidence(**base)


def fully_measured(**kwargs) -> GateReport:
    return evaluate_gate(
        [counters()],
        evidence=evidence(),
        projected_corpus_wall_clock_s=4.5 * 3600,
        pass_two_peak_commit_bytes=int(9.5 * GB),
        **kwargs,
    )


class TestAuthorisation:
    def test_a_fully_measured_table_with_evidence_authorises(self) -> None:
        """The positive case, without which the gate could be vacuously safe."""

        report = fully_measured()
        assert report.authorises_corpus_run is True
        assert report.failed == () and report.not_assessed == ()
        assert all(
            c.outcome is Outcome.PASS for c in report.conditions
        ), report.describe()

    def test_a_not_assessed_condition_does_not_authorise(self) -> None:
        """Round-4 #3.  NOT_ASSESSED is not PASS, and this is where it matters.

        These are the plan's own two unmeasured rows: the corpus projection and
        pass 2's commit charge with `S` resident.
        """

        report = evaluate_gate([counters()], evidence=evidence())

        assert report.authorises_corpus_run is False
        assert {c.name for c in report.not_assessed} == {
            "projected corpus wall-clock, both passes",
            "peak commit charge with S resident, pass 2",
        }
        assert report.failed == ()
        assert "NOT AUTHORISED" in report.describe()

    def test_measurements_alone_do_not_authorise_without_evidence(self) -> None:
        """The corpus run is authorised only by a production-path re-run."""

        report = evaluate_gate(
            [counters()],
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        assert report.not_assessed == ()
        assert report.failed == ()
        assert report.authorises_corpus_run is False
        assert "no production-path evidence" in report.describe()

    def test_parser_only_evidence_does_not_authorise(self) -> None:
        """22.5 minutes bounds the parser from below and says nothing about the
        stage: no LineString construction, mask intersection, dispatch,
        serialisation, hashing or publication."""

        report = evaluate_gate(
            [counters()],
            evidence=evidence(covers_full_production_path=False),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        assert report.authorises_corpus_run is False
        assert report.evidence.missing() == ("covers_full_production_path",)

    @pytest.mark.parametrize(
        "field", ["parser_source_sha256", "command", "input_digests", "output_digests"]
    )
    def test_a_partial_artifact_does_not_authorise(self, field) -> None:
        report = evaluate_gate(
            [counters()],
            evidence=evidence(**{field: type(getattr(evidence(), field))()}),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        assert field in report.evidence.missing()
        assert report.authorises_corpus_run is False


class TestPerFileEnforcement:
    def test_the_worst_file_decides_not_the_first(self) -> None:
        """Round-4 #4: compressed size does not order index cost, so "if the
        largest fits, all fit" is withdrawn and every file is enforced."""

        report = evaluate_gate(
            [counters(), counters("brazil-norte-220101", peak_commit_bytes=int(15.5 * GB))],
            evidence=evidence(),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        failed = {c.name for c in report.failed}
        assert "peak commit charge, pass 1 (worst file)" in failed
        assert report.authorises_corpus_run is False

    def test_index_size_drivers_are_recorded_per_file(self) -> None:
        report = fully_measured()
        assert report.files[0].node_cardinality == 43_250_208
        assert report.files[0].max_node_id > 0

    def test_a_slow_file_fails_the_wall_clock(self) -> None:
        report = evaluate_gate(
            [counters(wall_clock_s=PARSER_WALL_CLOCK_CEILING_S + 1)],
            evidence=evidence(),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        assert any("wall-clock, pass 1" in c.name for c in report.failed)

    def test_incomplete_geometry_and_invalid_locations_fail(self) -> None:
        report = evaluate_gate(
            [counters(retained=100, complete=99, invalid=1)],
            evidence=evidence(),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        failed = {c.name for c in report.failed}
        assert "geometry availability" in failed
        assert "ways with a missing or invalid node location" in failed

    def test_the_gate_needs_at_least_one_measured_file(self) -> None:
        with pytest.raises(ValueError, match="at least one measured file"):
            evaluate_gate([])


class TestWorkingSetIsNeverAGate:
    def test_an_absurd_working_set_cannot_change_the_verdict(self) -> None:
        """Round-6 #6.  Working set counts resident pages, so it *falls* when
        the process starts paging -- a swapping run would look healthier.
        Enforcement is on commit charge, and this proves it."""

        report = evaluate_gate(
            [counters(peak_working_set_bytes=999 * GB)],
            evidence=evidence(),
            projected_corpus_wall_clock_s=4.5 * 3600,
            pass_two_peak_commit_bytes=int(9.5 * GB),
        )
        assert report.authorises_corpus_run is True

        working_set = next(c for c in report.conditions if c.name == "peak working set")
        assert working_set.is_gate is False
        assert working_set not in report.gating


class TestExtrapolationIsLabelled:
    def test_the_corpus_projection_is_marked_extrapolated(self) -> None:
        report = fully_measured()
        projection = next(
            c for c in report.conditions if c.name.startswith("projected corpus")
        )
        assert projection.extrapolated is True
        assert projection.ceiling == CORPUS_WALL_CLOCK_CEILING_S
        assert "EXTRAPOLATED" in report.describe()


@WINDOWS_ONLY
class TestCommitProbe:
    def test_the_probe_tracks_a_deliberate_allocation(self) -> None:
        """§3.1's own validation: a probe returning a constant would make every
        memory row pass without measuring anything."""

        allocation = 64 * 1024 * 1024
        assert validate_probe(allocation) >= allocation // 2

    def test_a_reading_carries_commit_and_working_set_separately(self) -> None:
        sample = process_memory()
        assert sample.commit_bytes > 0
        assert sample.working_set_bytes > 0
        assert sample.commit_gb == sample.commit_bytes / GB

    def test_an_untracking_probe_is_refused(self, monkeypatch) -> None:
        import forecast.process_memory as mod

        monkeypatch.setattr(mod, "process_memory", lambda: mod.MemorySample(1, 1, 1))
        with pytest.raises(ProcessMemoryUnavailable, match="not measuring allocation"):
            mod.validate_probe(64 * 1024 * 1024)


@WINDOWS_ONLY
class TestSupervisedChild:
    def test_the_supervisor_terminates_on_the_guaranteed_notification(self) -> None:
        """The kill-test for §3's frozen design.

        A Job Object memory limit does not terminate anything by itself
        (round-7 #4), and `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT` is not guaranteed to
        be delivered (round-8 #9).  A `JobObjectNotificationLimitInformation`
        threshold registered before the child starts is, and the supervisor
        terminates on it.
        """

        result = run_supervised(
            [sys.executable, "-c", ALLOCATE.format(mb=400)],
            notification_bytes=THRESHOLD_BYTES,
            hard_limit_bytes=2048 * 1024 * 1024,
            timeout_s=60,
        )

        assert result.breached is True
        assert "NOTIFICATION_LIMIT" in result.messages
        assert result.exit_code == 124
        assert result.stage_failed is True

    def test_a_child_under_the_same_threshold_runs_to_completion(self) -> None:
        """The other half, and it shares the threshold on purpose.

        With a threshold the interpreter's own startup could cross, the breach
        test above would pass without the child ever allocating anything.  The
        pair pins the notification to the allocation: 400 MB over the same bar
        terminates, 32 MB under it exits cleanly.
        """

        result = run_supervised(
            [sys.executable, "-c", ALLOCATE.format(mb=32)],
            notification_bytes=THRESHOLD_BYTES,
            hard_limit_bytes=2048 * 1024 * 1024,
            timeout_s=60,
        )
        assert result.breached is False
        assert "NOTIFICATION_LIMIT" not in result.messages
        assert result.exit_code == 0
        assert result.stage_failed is False

    def test_an_abnormal_exit_is_stage_failure(self) -> None:
        """Allocation failure and abnormal child exit are treated identically."""

        result = run_supervised(
            [sys.executable, "-c", "raise SystemExit(3)"],
            notification_bytes=512 * 1024 * 1024,
            hard_limit_bytes=1024 * 1024 * 1024,
            timeout_s=60,
        )
        assert result.breached is False
        assert result.exit_code == 3
        assert result.stage_failed is True

    def test_the_threshold_must_sit_below_the_backstop(self) -> None:
        """Otherwise the hard limit fires first and the guaranteed notification
        never arrives -- which is the whole mechanism."""

        with pytest.raises(ValueError, match="below the hard limit"):
            MemorySupervisedJob(
                notification_bytes=HARD_LIMIT_BYTES, hard_limit_bytes=HARD_LIMIT_BYTES
            )

    def test_the_frozen_ceilings_are_named_not_implied(self) -> None:
        """v9 said merely "below 17 GB", which froze nothing (round-9 #6)."""

        assert AUTHORISATION_CEILING_BYTES == int(14.0 * GB)
        assert HARD_LIMIT_BYTES == int(17.0 * GB)
        assert AUTHORISATION_CEILING_BYTES < HARD_LIMIT_BYTES
