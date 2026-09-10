"""Times one (algorithm, property) pair over and over, varying only the seed.

Everything else -- the algorithm, the property, the client count, the trace length, the
depth -- is held fixed, and each run differs only in where its randomness starts. The
result is the distribution of the time a search takes to find that one violation, which is
what plot_ecdf.py turns into an ECDF.

    python -m sweep_repeats
    python -m sweep_repeats --algorithm got --property convergence --runs 300
    python -m sweep_repeats --strategies random dfs-random --budget 30

This is the within-pair counterpart to sweep_time_to_violation.py, which times one run each
across many pairs. That one answers "which strategy should the checker use"; this one
answers "how much does the answer vary from run to run", which is the question a single
reported number cannot.

The two deterministic strategies, bfs and dfs, do exactly the same work every run: they have
no seed to vary, so their spread is measurement noise and nothing else. They are run fewer
times (--deterministic-runs) because more would buy nothing, and they are worth keeping in
the figure precisely because that noise is the baseline the randomised spreads are read
against.

Runs serially by default; see --workers on sweep_time_to_violation.py for why.
"""

import argparse
import csv
import sys
from dataclasses import asdict, fields
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "code"))

from sweep_time_to_violation import STRATEGIES, Result, run_exhaustive, run_random  # noqa: E402

from main.cli import ALGORITHMS, CHECKS  # noqa: E402
from main.exhaustive import EXHAUSTIVE_CHECKS  # noqa: E402

DETERMINISTIC = {"bfs", "dfs"}

# Seeds for the sampling strategy are spaced far enough apart that two runs can never reach
# into each other's stretch of the seed space, however long one of them searches for.
SEED_STRIDE = 1_000_000


def one_run(
    algorithm: str,
    property_name: str,
    strategy: str,
    run: int,
    clients: int,
    ops: int,
    depth: int,
    budget: float,
    base_seed: int,
) -> Result:
    if strategy == "random":
        seed = base_seed + run * SEED_STRIDE
        outcome, seconds, work = run_random(algorithm, property_name, clients, ops, budget, seed)
    else:
        seed = base_seed + run
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_repeats", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "repeats.csv")
    parser.add_argument("--algorithm", default="adopted-ressel", choices=sorted(ALGORITHMS), metavar="A")
    parser.add_argument("--property", default="convergence", choices=sorted(CHECKS), metavar="P")
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=STRATEGIES, metavar="S")
    parser.add_argument("--runs", type=int, default=100, help="runs per randomised strategy (default 100)")
    parser.add_argument(
        "--deterministic-runs",
        type=int,
        default=10,
        help="runs for bfs and dfs, which repeat the same search every time (default 10)",
    )
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--ops", type=int, default=30, help="trace length for the random strategy")
    parser.add_argument("--depth", type=int, default=5, help="depth for the exhaustive strategies")
    parser.add_argument("--budget", type=float, default=30.0, help="seconds one run may take (default 30)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--resume", action="store_true", help="skip runs already in --out")
    arguments = parser.parse_args(argv)

    strategies = [s for s in arguments.strategies if s == "random" or arguments.property in EXHAUSTIVE_CHECKS]
    if not strategies:
        parser.error(f"no exhaustive checker for {arguments.property}, and 'random' was not among --strategies")

    done: set[tuple[str, int]] = set()
    if arguments.resume and arguments.out.exists():
        with arguments.out.open(newline="") as handle:
            done = {
                (row["strategy"], int(row.get("run", -1)))
                for row in csv.DictReader(handle)
                if row["algorithm"] == arguments.algorithm and row["property"] == arguments.property
            }

    jobs = [
        (strategy, run)
        for strategy in strategies
        for run in range(arguments.deterministic_runs if strategy in DETERMINISTIC else arguments.runs)
        if (strategy, run) not in done
    ]
    if not jobs:
        print("nothing to do", file=sys.stderr)
        return 0

    print(
        f"{arguments.algorithm} / {arguments.property}: {len(jobs)} runs "
        f"({arguments.clients} clients, ops {arguments.ops}, depth {arguments.depth}, budget {arguments.budget:.0f}s)",
        file=sys.stderr,
    )

    # `run` is not part of Result, which describes one attempt rather than a series, so it is
    # written alongside the fields rather than forced into the dataclass.
    columns = ["run", *[field.name for field in fields(Result)]]
    write_header = not arguments.out.exists() or arguments.out.stat().st_size == 0

    with arguments.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
            handle.flush()

        counts: dict[str, int] = {}
        for index, (strategy, run) in enumerate(jobs, start=1):
            result = one_run(
                arguments.algorithm,
                arguments.property,
                strategy,
                run,
                arguments.clients,
                arguments.ops,
                arguments.depth,
                arguments.budget,
                arguments.seed,
            )
            writer.writerow({"run": run, **asdict(result)})
            handle.flush()

            counts[strategy] = counts.get(strategy, 0) + 1
            total = arguments.deterministic_runs if strategy in DETERMINISTIC else arguments.runs
            if counts[strategy] % 25 == 0 or counts[strategy] == total:
                print(
                    f"[{index}/{len(jobs)}] {strategy:11s} {counts[strategy]:>4d}/{total}"
                    f"  last {result.outcome} in {result.seconds:.3f}s",
                    file=sys.stderr,
                )

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
