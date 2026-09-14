"""Measures how long each search strategy takes to find a violation, per algorithm and property.

Every strategy is given the same benchmark of (algorithm, property) pairs that are known to
violate, and the same wall-clock budget per pair, and is timed until it finds a violation.
The result feeds an ECDF over the benchmark -- what fraction of the pairs a strategy has
cracked by time t -- which is the comparison both "what search order" and "randomised vs
exhaustive" need.

    python -m sweep_time_to_violation
    python -m sweep_time_to_violation --budget 60 --depth 7
    python -m sweep_time_to_violation --from-profiles data/profiles.csv
    python -m sweep_time_to_violation --strategies random bfs dfs

Strategies:

    random              sample random traces at --ops, seed 1 upwards, until one violates
    bfs, dfs            enumerate to --depth in that order
    bfs-random          the same, with the operations at each node shuffled
    dfs-random

Three outcomes are distinguished, and only the first is an observation rather than a
censoring: `found`, `exhausted` (the whole space to --depth held no violation) and `timeout`.
An ECDF must plateau at the fraction found rather than run to 100%.

Runs serially by default. These are wall-clock measurements and workers competing for cores
inflate them; --workers trades that accuracy for speed when the ordering is all you need.
"""

import argparse
import contextlib
import csv
import io
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "code"))

import figure_spec  # noqa: E402

from main.cli import ALGORITHMS, CHECKS, case_timeout, run_case  # noqa: E402
from main.exhaustive import EXHAUSTIVE_CHECKS  # noqa: E402

STRATEGIES = ["random", "bfs", "dfs", "bfs-random", "dfs-random"]

# depth_first, randomised -- for the four exhaustive strategies.
EXHAUSTIVE_MODES = {
    "bfs": (False, False),
    "dfs": (True, False),
    "bfs-random": (False, True),
    "dfs-random": (True, True),
}


@dataclass
class Result:
    """One strategy's attempt at one (algorithm, property) pair."""

    algorithm: str
    property: str
    strategy: str
    clients: int
    ops: int
    depth: int
    seed: int
    # found | exhausted | timeout | <exception name>
    outcome: str
    seconds: float
    # Traces enumerated, or seeds sampled: the work done, for an ECDF that wants to compare
    # strategies without the machine's speed in the way.
    work: int


def run_random(
    algorithm: str, property_name: str, clients: int, ops: int, budget: float, seed: int
) -> tuple[str, float, int]:
    # Sampling has no natural end, so the budget is the only stopping condition. Seeds start
    # from `seed` so a run is reproducible and so two strategies never share a trace.
    check = CHECKS[property_name]
    setup = ALGORITHMS[algorithm]

    started = time.perf_counter()
    sampled = 0
    while time.perf_counter() - started < budget:
        outcome = run_case(check, setup, seed + sampled, clients, ops, verbose=False, timeout=budget)
        sampled += 1
        if outcome == "failed":
            return "found", time.perf_counter() - started, sampled
        if outcome not in ("passed", "TimeoutError"):
            return outcome, time.perf_counter() - started, sampled

    return "timeout", time.perf_counter() - started, sampled


def run_exhaustive(
    algorithm: str, property_name: str, clients: int, depth: int, strategy: str, budget: float, seed: int
) -> tuple[str, float, int]:
    check = EXHAUSTIVE_CHECKS[property_name]
    setup = ALGORITHMS[algorithm]
    depth_first, randomised = EXHAUSTIVE_MODES[strategy]

    if randomised:
        random.seed(seed)

    started = time.perf_counter()
    captured = io.StringIO()
    try:
        with case_timeout(budget), contextlib.redirect_stdout(captured):
            passed, checked = check(setup, clients, depth, randomised, depth_first)
    except TimeoutError:
        return "timeout", time.perf_counter() - started, 0
    except Exception as exception:  # noqa: BLE001 - a broken implementation must not end the sweep
        return type(exception).__name__, time.perf_counter() - started, 0

    # `passed` false means the search stopped early on a violation; true means it covered the
    # whole space to `depth` and found none, which is a censoring, not a slow success.
    return ("exhausted" if passed else "found"), time.perf_counter() - started, checked


def attempt(
    algorithm: str, property_name: str, strategy: str, clients: int, ops: int, depth: int, budget: float, seed: int
) -> Result:
    if strategy == "random":
        outcome, seconds, work = run_random(algorithm, property_name, clients, ops, budget, seed)
    else:
        outcome, seconds, work = run_exhaustive(algorithm, property_name, clients, depth, strategy, budget, seed)

    return Result(
        algorithm=algorithm,
        property=property_name,
        strategy=strategy,
        clients=clients,
        ops=ops,
        depth=depth,
        seed=seed,
        outcome=outcome,
        seconds=round(seconds, 6),
        work=work,
    )


def pairs_from_profiles(path: Path) -> list[tuple[str, str]]:
    """Every (algorithm, property) a previous sweep found violations for."""
    found: set[tuple[str, str]] = set()
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["violations"]) > 0:
                found.add((row["algorithm"], row["property"]))
    return sorted(found)


def existing(path: Path) -> set[tuple[str, str, str, int, int]]:
    if not path.exists():
        return set()
    with path.open(newline="") as handle:
        return {
            (row["algorithm"], row["property"], row["strategy"], int(row["clients"]), int(row["depth"]))
            for row in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_time_to_violation", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "time_to_violation.csv")
    parser.add_argument(
        "--from-profiles",
        type=Path,
        nargs="+",
        metavar="CSV",
        help="take the benchmark from sweep CSVs: every pair they recorded violations for. "
        "Gives a larger, less hand-picked benchmark than the figure's own panels, and several "
        "files can be combined because no one sweep covers every property",
    )
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=STRATEGIES, metavar="S")
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--ops", type=int, default=30, help="trace length for the random strategy (default 30)")
    parser.add_argument("--depth", type=int, default=6, help="depth for the exhaustive strategies (default 6)")
    parser.add_argument("--budget", type=float, default=20.0, help="seconds per pair per strategy (default 20)")
    parser.add_argument("--seed", type=int, default=1, help="seeds the sampling and the randomised orders")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel jobs (default 1). These are wall-clock measurements, so raising this "
        "inflates every timing; use it only when the ordering matters more than the values",
    )
    parser.add_argument("--resume", action="store_true", help="skip attempts already in --out")
    arguments = parser.parse_args(argv)

    if arguments.from_profiles:
        missing = [path for path in arguments.from_profiles if not path.exists()]
        if missing:
            parser.error(f"does not exist: {', '.join(str(path) for path in missing)}")
        benchmark = sorted({pair for path in arguments.from_profiles for pair in pairs_from_profiles(path)})
    else:
        benchmark = sorted(set(figure_spec.cells()))

    unsupported = sorted({p for _, p in benchmark if p not in EXHAUSTIVE_CHECKS})
    if unsupported and set(arguments.strategies) - {"random"}:
        print(
            f"note: no exhaustive checker for {', '.join(unsupported)}; those pairs run 'random' only", file=sys.stderr
        )

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    done = existing(arguments.out) if arguments.resume else set()
    if arguments.resume and done:
        print(f"resuming: {len(done)} attempts already in {arguments.out}", file=sys.stderr)

    jobs = [
        (algorithm, property_name, strategy)
        for algorithm, property_name in benchmark
        for strategy in arguments.strategies
        if (strategy == "random" or property_name in EXHAUSTIVE_CHECKS)
        and (algorithm, property_name, strategy, arguments.clients, arguments.depth) not in done
    ]
    if not jobs:
        print("nothing to do", file=sys.stderr)
        return 0

    print(
        f"{len(benchmark)} pairs x {len(arguments.strategies)} strategies = {len(jobs)} attempts, "
        f"{arguments.budget:.0f}s budget each (worst case {len(jobs) * arguments.budget / 60:.0f} min"
        f"{'' if arguments.workers == 1 else f' / {arguments.workers} workers'})",
        file=sys.stderr,
    )

    write_header = not arguments.out.exists() or arguments.out.stat().st_size == 0
    columns = [field.name for field in fields(Result)]

    with arguments.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
            handle.flush()

        def record(result: Result, index: int) -> None:
            writer.writerow(asdict(result))
            handle.flush()
            print(
                f"[{index}/{len(jobs)}] {result.algorithm:16s} {result.property:22s} {result.strategy:11s} "
                f"{result.outcome:9s} {result.seconds:7.2f}s  work={result.work}",
                file=sys.stderr,
            )

        if arguments.workers == 1:
            for index, (algorithm, property_name, strategy) in enumerate(jobs, start=1):
                record(
                    attempt(
                        algorithm,
                        property_name,
                        strategy,
                        arguments.clients,
                        arguments.ops,
                        arguments.depth,
                        arguments.budget,
                        arguments.seed,
                    ),
                    index,
                )
        else:
            with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
                futures = {
                    pool.submit(
                        attempt,
                        algorithm,
                        property_name,
                        strategy,
                        arguments.clients,
                        arguments.ops,
                        arguments.depth,
                        arguments.budget,
                        arguments.seed,
                    ): (algorithm, property_name, strategy)
                    for algorithm, property_name, strategy in jobs
                }
                for index, future in enumerate(as_completed(futures), start=1):
                    try:
                        record(future.result(), index)
                    except Exception as exception:  # noqa: BLE001
                        print(f"[{index}/{len(jobs)}] {futures[future]} FAILED: {exception}", file=sys.stderr)

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
