"""Measures how often a violation appears as the number of clients grows.

The companion to sweep_ops.py: that one holds the client count fixed and varies the trace
length, this one holds the trace length fixed and varies the client count. Together they
cover the two parameters that decide whether a violation is reachable at all.

    python -m sweep_clients
    python -m sweep_clients --seeds 10000 --resume
    python -m sweep_clients --algorithms soct2 abt --properties convergence --clients 2 3 4 5

Client count is the one parameter here that is a matter of correctness rather than of cost.
A violation that needs three concurrent operations cannot occur with two clients however
long the traces are, so an algorithm requiring TP2 will read as clean at two clients no
matter how much search it is given. Anything reported at a single client count carries an
implicit claim that the count was high enough, and this is the measurement behind it.

Rows share a schema with sweep_ops.py, so plot_ops.py draws either with --x clients.
"""

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, fields
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "code"))

import figure_spec  # noqa: E402
from sweep_ops import Cell, run_cell  # noqa: E402

from main.cli import ALGORITHMS, CHECKS  # noqa: E402

# Two is the floor worth measuring -- one client has no concurrency and so no violation of
# any of these properties. The top end is set by cost: every extra client multiplies the
# work the checker does per trace as well as the branching of the generator.
DEFAULT_CLIENTS = [2, 3, 4, 5, 6]

# Long enough that a violation reachable at a given client count has a fair chance of
# appearing, so that a zero reads as "not reachable" rather than "not looked for".
DEFAULT_OPS = 30


def key(algorithm: str, property_name: str, clients: int, ops: int) -> tuple[str, str, int, int]:
    return (algorithm, property_name, clients, ops)


def existing_cells(path: Path) -> set[tuple[str, str, int, int]]:
    if not path.exists():
        return set()
    with path.open(newline="") as handle:
        return {
            key(row["algorithm"], row["property"], int(row["clients"]), int(row["ops"]))
            for row in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_clients", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "violation_rate_clients.csv")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=sorted(ALGORITHMS),
        metavar="A",
        help="measure these against every property in --properties; "
        "without it the figure's own per-property sets are used",
    )
    parser.add_argument("--properties", nargs="+", choices=sorted(CHECKS), metavar="P")
    parser.add_argument("--clients", nargs="+", type=int, default=DEFAULT_CLIENTS, help="client counts to measure")
    parser.add_argument(
        "--ops", type=int, default=DEFAULT_OPS, help=f"trace length, held fixed (default {DEFAULT_OPS})"
    )
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

    if arguments.algorithms or arguments.properties:
        wanted = [
            (algorithm, property_name)
            for algorithm in (arguments.algorithms or sorted(ALGORITHMS))
            for property_name in (arguments.properties or sorted(CHECKS))
        ]
    else:
        wanted = figure_spec.cells()

    cells = [
        (algorithm, property_name, clients)
        for algorithm, property_name in wanted
        for clients in arguments.clients
        if key(algorithm, property_name, clients, arguments.ops) not in done
    ]
    if not cells:
        print("nothing to do", file=sys.stderr)
        return 0

    print(
        f"{len(cells)} cells at {arguments.ops} operations, {arguments.seeds} seeds each, "
        f"client counts {arguments.clients}",
        file=sys.stderr,
    )

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
                    clients,
                    arguments.ops,
                    arguments.from_seed,
                    arguments.seeds,
                    arguments.timeout,
                    arguments.max_timeouts,
                ): (algorithm, property_name, clients)
                for algorithm, property_name, clients in cells
            }

            for completed, future in enumerate(as_completed(futures), start=1):
                algorithm, property_name, clients = futures[future]
                try:
                    cell = future.result()
                except Exception as exception:  # noqa: BLE001 - one bad cell must not end the sweep
                    print(
                        f"[{completed}/{len(cells)}] {algorithm} {property_name} clients={clients} "
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
                    f"[{completed}/{len(cells)}] {algorithm:24s} {property_name:21s} clients={clients:<2d} "
                    f"{cell.violations:>6d}/{cell.seeds} violated  ({cell.seconds:6.1f}s){note}",
                    file=sys.stderr,
                )

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
