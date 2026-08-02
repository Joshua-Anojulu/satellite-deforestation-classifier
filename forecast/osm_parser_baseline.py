"""The parser-only baseline, checked in so it can be re-run and contradicted.

**This module exists because the original one did not.** §3's 22.5-minute and
8.22 GB figures came from a harness that was never committed, so when the
production path measured 14.3 minutes and 5.45 GB on the same extract there was
no way to test why -- a strictly larger workload cannot be cheaper, and the
explanation could not be checked. Round-4 #3 named this exposure exactly: *"no
checked-in harness or immutable measurement artifact binds the result to future
parser code."*

**What this runs is the parser and nothing else**, matching what §3's harness was
described as doing: node decoding, `flex_mem` index construction, the retain
predicate, and §1.5's full per-node validation of every retained way. It does
**not** build `LineString`s, intersect masks, dispatch, serialise, hash or
publish. Subtracting this from `osm_pipeline`'s wall clock on the same file is
therefore the measured cost of those six stages.

**Total ways are counted, not just retained ones.** If the two runs disagree on
how much of the file was parsed, no comparison of their timings means anything --
and that is the first thing to rule out.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from forecast.osm_normalise import retains
from forecast.osm_stream import build_retained_way, way_processor
from forecast.process_memory import process_memory


@dataclass(frozen=True)
class BaselineResult:
    """One parser-only measurement."""

    name: str
    total_ways: int
    retained_ways: int
    node_cardinality: int
    max_node_id: int
    wall_clock_s: float
    peak_commit_bytes: int
    peak_working_set_bytes: int

    def document(self) -> dict[str, object]:
        return {
            "name": self.name,
            "total_ways": self.total_ways,
            "retained_ways": self.retained_ways,
            "node_cardinality": self.node_cardinality,
            "max_node_id": self.max_node_id,
            "wall_clock_s": self.wall_clock_s,
            "peak_commit_bytes": self.peak_commit_bytes,
            "peak_working_set_bytes": self.peak_working_set_bytes,
        }


def measure(path: str | Path, *, sample_every: int = 200_000, progress: bool = True) -> BaselineResult:
    """Parse one extract with full validation, discarding every result.

    The retained way is built and then dropped on purpose: building it is the
    validation (§1.5 checks every node location), and keeping it would make this
    measure accumulation rather than parsing -- which is the very difference
    under investigation.
    """

    path = Path(path)
    peak_commit = 0
    peak_working_set = 0
    total = 0
    retained = 0
    node_cardinality = 0
    max_node_id = 0

    def sample() -> None:
        nonlocal peak_commit, peak_working_set
        reading = process_memory()
        peak_commit = max(peak_commit, reading.commit_bytes)
        peak_working_set = max(peak_working_set, reading.peak_working_set_bytes)

    sample()
    started = time.perf_counter()
    for way in way_processor(str(path)):
        total += 1
        if retains(way.tags):
            built = build_retained_way(way)
            retained += 1
            node_cardinality += len(built.node_refs)
            if built.node_refs:
                max_node_id = max(max_node_id, max(built.node_refs))
            del built
        if total % sample_every == 0:
            sample()
            if progress:
                print(
                    f"  {path.name}: {total:,} ways ({retained:,} retained), "
                    f"{time.perf_counter() - started:,.0f}s, "
                    f"commit {peak_commit / 1024**3:.2f} GB",
                    flush=True,
                )
    wall_clock = time.perf_counter() - started
    sample()

    return BaselineResult(
        name=path.stem,
        total_ways=total,
        retained_ways=retained,
        node_cardinality=node_cardinality,
        max_node_id=max_node_id,
        wall_clock_s=wall_clock,
        peak_commit_bytes=peak_commit,
        peak_working_set_bytes=peak_working_set,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extract", help="path to a .osm.pbf")
    parser.add_argument("--out", default=None, help="write the measurement here")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    result = measure(args.extract, progress=not args.quiet)
    print()
    print(f"total ways        {result.total_ways:,}")
    print(f"retained ways     {result.retained_ways:,}")
    print(f"wall clock        {result.wall_clock_s:.1f} s = {result.wall_clock_s / 60:.1f} min")
    print(f"peak commit       {result.peak_commit_bytes / 1024**3:.2f} GB")
    print(f"peak working set  {result.peak_working_set_bytes / 1024**3:.2f} GB")

    if args.out:
        Path(args.out).write_text(
            json.dumps(result.document(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
