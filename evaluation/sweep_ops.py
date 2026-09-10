"""Measures how often a violation appears as a function of trace length.

This produces the data behind the "how commonly violations appear" figure: for each
(algorithm, property, trace length) cell it runs a fixed set of seeds and records how many
of them the checker rejected. The output is one CSV row per cell.

Because every checker calls `random.seed(n)` before generating a trace, seed n at 20
operations extends seed n at 10 operations rather than being an unrelated trace. A cell is
therefore not an independent sample at each length: read a row as "by length L, this
fraction of the seeds had shown a violation", which is what makes the curve answer the
question of what depth a search has to reach.

With no --algorithms or --properties it measures exactly the cells the figure needs, which
figure_spec.py defines per property. Naming either dimension sweeps the cross product
instead, for exploring outside the figure.

    python -m sweep_ops
    python -m sweep_ops --seeds 10000 --resume
    python -m sweep_ops --algorithms rga fugue --properties convergence --ops 5 10 15

Runs the cells in parallel, one process per cell, appending each as it finishes, so a long
sweep can be interrupted and picked up again with --resume.
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

# Sampled densely at the short end, because that is where the curves turn: most violations
# that appear at all have appeared by 10 operations, and the question the figure answers is
# where each one starts.
DEFAULT_OPS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50]


@dataclass
class Cell:
    """One (algorithm, property, length) point: the result of running `seeds` traces."""

    algorithm: str
    property: str
    clients: int
    ops: int
    seeds: int
    violations: int
    errors: int
    timeouts: int
    violation_rate: float
    first_violation_seed: int
    error_kind: str
    aborted: int
    seconds: float


def key(algorithm: str, property_name: str, clients: int, ops: int) -> tuple[str, str, int, int]:
    return (algorithm, property_name, clients, ops)


def run_cell(
    algorithm: str,
    property_name: str,
    clients: int,
    ops: int,
    from_seed: int,
    seeds: int,
    timeout: float,
    max_timeouts: int,
) -> Cell:
    # A checker rejecting a trace and an implementation raising are different findings, so
    # they are counted separately rather than folded together into a failure count. An
    # implementation that hangs (Logoot can, on adjacent identifiers) would otherwise spend
    # `timeout` seconds on every one of thousands of seeds, so a cell gives up once it has
    # seen enough of them and reports how far it got.
    check = CHECKS[property_name]
    setup = ALGORITHMS[algorithm]

    violations = 0
    errors = 0
    timeouts = 0
    first_violation_seed = 0
    error_kind = ""
    aborted = False
    started = time.time()

    checked = 0
    for seed in range(from_seed, from_seed + seeds):
        outcome = run_case(check, setup, seed, clients, ops, verbose=False, timeout=timeout)
        checked += 1

        if outcome == "passed":
            continue
        if outcome == "failed":
            violations += 1
            first_violation_seed = first_violation_seed or seed
        elif outcome == "TimeoutError":
            timeouts += 1
            if max_timeouts and timeouts >= max_timeouts:
                aborted = True
                break
        else:
            errors += 1
            error_kind = error_kind or outcome

    return Cell(
        algorithm=algorithm,
        property=property_name,
        clients=clients,
        ops=ops,
        seeds=checked,
        violations=violations,
        errors=errors,
        timeouts=timeouts,
        violation_rate=violations / checked if checked else 0.0,
        first_violation_seed=first_violation_seed,
        error_kind=error_kind,
        aborted=int(aborted),
        seconds=round(time.time() - started, 2),
    )


def existing_cells(path: Path) -> set[tuple[str, str, int, int]]:
    if not path.exists():
        return set()
    with path.open(newline="") as handle:
        return {
            key(row["algorithm"], row["property"], int(row["clients"]), int(row["ops"]))
            for row in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_ops", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "violation_rate.csv")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=sorted(ALGORITHMS),
        metavar="A",
        help="measure these against every property in --properties; without it the figure's own per-property sets are used",
    )
    parser.add_argument("--properties", nargs="+", choices=sorted(CHECKS), metavar="P")
    parser.add_argument("--ops", nargs="+", type=int, default=DEFAULT_OPS, help="trace lengths to measure")
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--seeds", type=int, default=2000, help="traces per cell (default 2000)")
    parser.add_argument("--from-seed", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=2.0, help="seconds before one trace is given up on")
    parser.add_argument("--max-timeouts", type=int, default=20, help="timeouts before a cell is abandoned, 0 for none")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--resume", action="store_true", help="skip cells already in --out")
    arguments = parser.parse_args(argv)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    done = existing_cells(arguments.out) if arguments.resume else set()
    if arguments.resume and done:
        print(f"resuming: {len(done)} cells already in {arguments.out}", file=sys.stderr)

    # Each panel of the figure has its own algorithms, so the default is that list rather
    # than a cross product: measuring a property against an algorithm that satisfies it
    # costs a full run of seeds to produce a line that would sit flat on zero. Naming
    # either dimension explicitly asks for the cross product instead, which is what an
    # exploratory sweep wants.
    if arguments.algorithms or arguments.properties:
        wanted = [
            (algorithm, property_name)
            for algorithm in (arguments.algorithms or sorted(ALGORITHMS))
            for property_name in (arguments.properties or sorted(CHECKS))
        ]
    else:
        wanted = figure_spec.cells()

    cells = [
        (algorithm, property_name, ops)
        for algorithm, property_name in wanted
        for ops in arguments.ops
        if key(algorithm, property_name, arguments.clients, ops) not in done
    ]
    if not cells:
        print("nothing to do", file=sys.stderr)
        return 0

    write_header = not arguments.out.exists() or arguments.out.stat().st_size == 0
    columns = [field.name for field in fields(Cell)]

    with arguments.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
            handle.flush()

        with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
            futures = {
                pool.submit(
                    run_cell,
                    algorithm,
                    property_name,
                    arguments.clients,
                    ops,
                    arguments.from_seed,
                    arguments.seeds,
                    arguments.timeout,
                    arguments.max_timeouts,
                ): (algorithm, property_name, ops)
                for algorithm, property_name, ops in cells
            }

            # Rows are appended as cells finish rather than at the end, so an interrupted
            # sweep keeps everything it has already paid for and --resume can continue it.
            for completed, future in enumerate(as_completed(futures), start=1):
                algorithm, property_name, ops = futures[future]
                try:
                    cell = future.result()
                except Exception as exception:  # noqa: BLE001 - one bad cell must not end the sweep
                    print(
                        f"[{completed}/{len(cells)}] {algorithm} {property_name} ops={ops} "
                        f"CELL FAILED: {type(exception).__name__}: {exception}",
                        file=sys.stderr,
                    )
                    continue

                writer.writerow(asdict(cell))
                handle.flush()

                note = ""
                if cell.errors:
                    note += f"  [{cell.errors} raised {cell.error_kind}]"
                if cell.timeouts:
                    note += f"  [{cell.timeouts} timed out{', abandoned' if cell.aborted else ''}]"
                print(
                    f"[{completed}/{len(cells)}] {algorithm:24s} {property_name:21s} ops={ops:<3d} "
                    f"{cell.violations:>6d}/{cell.seeds} violated  ({cell.seconds:6.1f}s){note}",
                    file=sys.stderr,
                )

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
