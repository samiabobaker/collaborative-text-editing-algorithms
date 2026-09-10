"""Measures how many seeds a randomised search needs before it finds a violation.

For each (algorithm, property) pair this runs many independent replicate searches and
records, for each one, the seed at which it first hit a violation. The empirical
distribution of that index is the detection curve: P(a violation has been found by seed n).

A replicate is a disjoint block of the seed space, and it stops at its first violation,
because the index is all the curve needs. That is what makes this affordable: the expected
cost of a replicate is 1/p seeds rather than the whole block, so a pair that violates on
0.4% of traces costs a few hundred seeds per replicate instead of thousands.

    python -m sweep_seeds
    python -m sweep_seeds --ops 15 --replicates 500
    python -m sweep_seeds --pairs cot/strong-list-spec dopt/convergence

The trace length matters more than it looks. At 50 operations almost every violation that
exists at all is found within a hundred seeds, so the curve is uninformative; the default is
a short length, where the pairs separate by orders of magnitude.
"""

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "code"))

import figure_spec  # noqa: E402

from main.cli import ALGORITHMS, CHECKS, run_case  # noqa: E402

DEFAULT_OPS = 10


@dataclass
class Replicate:
    """One independent search: where in its block of seeds it first found a violation."""

    algorithm: str
    property: str
    clients: int
    ops: int
    replicate: int
    block_size: int
    from_seed: int
    # 1-based index within the block, or 0 for a block that ran out without a violation.
    # Zero is right-censoring, not a rate of zero, so the curve it feeds is only valid out
    # to block_size and must not be extrapolated past it.
    first_violation: int
    seeds_used: int
    errors: int
    timeouts: int
    seconds: float


def run_replicate(
    algorithm: str,
    property_name: str,
    clients: int,
    ops: int,
    replicate: int,
    from_seed: int,
    block_size: int,
    timeout: float,
) -> Replicate:
    check = CHECKS[property_name]
    setup = ALGORITHMS[algorithm]

    errors = 0
    timeouts = 0
    first = 0
    used = 0
    started = time.time()

    for offset in range(block_size):
        outcome = run_case(check, setup, from_seed + offset, clients, ops, verbose=False, timeout=timeout)
        used += 1

        if outcome == "failed":
            first = offset + 1
            break
        if outcome == "TimeoutError":
            timeouts += 1
        elif outcome != "passed":
            errors += 1

    return Replicate(
        algorithm=algorithm,
        property=property_name,
        clients=clients,
        ops=ops,
        replicate=replicate,
        block_size=block_size,
        from_seed=from_seed,
        first_violation=first,
        seeds_used=used,
        errors=errors,
        timeouts=timeouts,
        seconds=round(time.time() - started, 2),
    )


def parse_pair(text: str) -> tuple[str, str]:
    if "/" not in text:
        raise argparse.ArgumentTypeError(f"{text!r} should be <algorithm>/<property>")
    algorithm, property_name = text.split("/", 1)
    if algorithm not in ALGORITHMS:
        raise argparse.ArgumentTypeError(f"unknown algorithm {algorithm!r}")
    if property_name not in CHECKS:
        raise argparse.ArgumentTypeError(f"unknown property {property_name!r}")
    return algorithm, property_name


def existing(path: Path) -> set[tuple[str, str, int, int, int]]:
    if not path.exists():
        return set()
    with path.open(newline="") as handle:
        return {
            (row["algorithm"], row["property"], int(row["clients"]), int(row["ops"]), int(row["replicate"]))
            for row in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_seeds", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "detection.csv")
    parser.add_argument(
        "--pairs",
        nargs="+",
        type=parse_pair,
        metavar="ALGORITHM/PROPERTY",
        help="pairs to measure; defaults to figure_spec.DETECTION_PAIRS",
    )
    parser.add_argument("--ops", type=int, default=DEFAULT_OPS, help=f"operations per trace (default {DEFAULT_OPS})")
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--replicates", type=int, default=300, help="independent searches per pair (default 300)")
    parser.add_argument("--block", type=int, default=5000, help="seeds one search may use before giving up")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--resume", action="store_true", help="skip replicates already in --out")
    arguments = parser.parse_args(argv)

    pairs = arguments.pairs or figure_spec.DETECTION_PAIRS
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    done = existing(arguments.out) if arguments.resume else set()
    if arguments.resume and done:
        print(f"resuming: {len(done)} replicates already in {arguments.out}", file=sys.stderr)

    # Every replicate gets its own stretch of the seed space, so no two searches in the
    # whole sweep ever look at the same trace and the replicates really are independent.
    jobs = []
    for algorithm, property_name in pairs:
        for replicate in range(arguments.replicates):
            if (algorithm, property_name, arguments.clients, arguments.ops, replicate) in done:
                continue
            jobs.append((algorithm, property_name, replicate, 1 + replicate * arguments.block))

    if not jobs:
        print("nothing to do", file=sys.stderr)
        return 0

    write_header = not arguments.out.exists() or arguments.out.stat().st_size == 0
    columns = [field.name for field in fields(Replicate)]
    finished: dict[tuple[str, str], int] = {}

    with arguments.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
            handle.flush()

        with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
            futures = {
                pool.submit(
                    run_replicate,
                    algorithm,
                    property_name,
                    arguments.clients,
                    arguments.ops,
                    replicate,
                    from_seed,
                    arguments.block,
                    arguments.timeout,
                ): (algorithm, property_name)
                for algorithm, property_name, replicate, from_seed in jobs
            }

            for completed, future in enumerate(as_completed(futures), start=1):
                pair = futures[future]
                try:
                    result = future.result()
                except Exception as exception:  # noqa: BLE001 - one bad replicate must not end the sweep
                    print(f"[{completed}/{len(jobs)}] {pair} FAILED: {type(exception).__name__}", file=sys.stderr)
                    continue

                writer.writerow(asdict(result))
                handle.flush()

                # One line per replicate would be hundreds of lines of noise, so progress is
                # reported per pair as its replicates land.
                seen = finished[pair] = finished.get(pair, 0) + 1
                if seen % 50 == 0 or seen == arguments.replicates:
                    print(
                        f"[{completed}/{len(jobs)}] {pair[0]:16s} {pair[1]:22s} {seen}/{arguments.replicates} searches",
                        file=sys.stderr,
                    )

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
