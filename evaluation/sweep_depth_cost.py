"""Times a full exhaustive search as the number of operations per execution grows.

For each depth this enumerates the entire space -- every execution of that many operations
-- and checks all of it, without stopping at the first violation. The result is the cost of
covering a depth, which is what decides how deep an exhaustive search can be run at all.
That is a different measurement from time-to-first-violation, where a search that finds a
counter-example early never pays for the rest of the space.

    python -m sweep_depth_cost
    python -m sweep_depth_cost --algorithm woot --property forward-interleaving
    python -m sweep_depth_cost --clients 2 3 4 --depths 2 3 4 5 6 7 --max-seconds 600

The space grows by roughly a factor of ten per operation, so the ladder stops climbing once
a depth costs more than --max-seconds: the next one would take ten times as long, and a
partial measurement of it says nothing. Depths that were not reached are simply absent from
the output rather than recorded as zero.
"""

import argparse
import contextlib
import csv
import io
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "code"))

from convergence_checker.exhaustive_trace import build_exhaustive_states  # noqa: E402
from interleaving_checker.exhaustive_trace import build_exhaustive_interleaving_trace  # noqa: E402
from interleaving_checker.interleaving_checker import (  # noqa: E402
    forward_non_interleaving_for_client_log,
    maximally_non_interleaving_for_client_log,
)
from list_spec_checker.exhaustive_trace import build_exhaustive_trace  # noqa: E402
from list_spec_checker.list_spec_checker import (  # noqa: E402
    strong_list_specification_checker_for_client_log,
    weak_list_specification_checker_for_client_log,
)
from main.cli import ALGORITHMS  # noqa: E402

# The two helpers that know how to copy devices and settle a network are already written and
# used by the CLI's own exhaustive mode; re-deriving them here would risk measuring
# something subtly different from what the checker does.
from main.exhaustive import _client_dict, _converges_from  # noqa: E402

PROPERTIES = ["convergence", "weak-list-spec", "strong-list-spec", "forward-interleaving", "interleaving"]

LIST_SPEC_CHECKERS = {
    "weak-list-spec": weak_list_specification_checker_for_client_log,
    "strong-list-spec": strong_list_specification_checker_for_client_log,
}
INTERLEAVING_CHECKERS = {
    "forward-interleaving": forward_non_interleaving_for_client_log,
    "interleaving": maximally_non_interleaving_for_client_log,
}


@dataclass
class Measurement:
    """One full enumeration of the space at a given depth."""

    algorithm: str
    property: str
    clients: int
    depth: int
    traces: int
    violations: int
    seconds: float
    # False when an implementation raised part way through, which ends the generator and
    # leaves the depth only partly covered. Its time is not a cost for that depth.
    complete: int
    note: str


def enumerate_all(algorithm: str, property_name: str, clients: int, depth: int, depth_first: bool) -> Measurement:
    # Every node is visited and checked, and a failing check is counted rather than raised,
    # so the timing covers the whole space rather than stopping at the first counter-example.
    server, client_dict = _client_dict(ALGORITHMS[algorithm], clients)

    if property_name == "convergence":
        traces = build_exhaustive_states(client_dict, server, depth, False, depth_first)

        def passed(node) -> bool:
            node_server, node_clients = node
            return _converges_from(node_server, node_clients)
    elif property_name in LIST_SPEC_CHECKERS:
        traces = build_exhaustive_trace(client_dict, server, depth, False, depth_first)
        checker = LIST_SPEC_CHECKERS[property_name]

        def passed(node) -> bool:
            return checker(node)
    else:
        traces = build_exhaustive_interleaving_trace(client_dict, server, depth, False, depth_first)
        checker = INTERLEAVING_CHECKERS[property_name]

        def passed(node) -> bool:
            trace, characters = node
            return checker(trace, characters)

    seen = 0
    violations = 0
    note = ""
    complete = True
    captured = io.StringIO()

    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(captured):
            for node in traces:
                seen += 1
                if not passed(node):
                    violations += 1
    except (IndexError, ValueError) as exception:
        # The same exceptions the CLI treats as "does not satisfy the property". They end the
        # generator, so the depth is only partly covered and its time is not its cost.
        complete = False
        note = type(exception).__name__
    elapsed = time.perf_counter() - started

    return Measurement(
        algorithm=algorithm,
        property=property_name,
        clients=clients,
        depth=depth,
        traces=seen,
        violations=violations,
        seconds=round(elapsed, 6),
        complete=int(complete),
        note=note,
    )


def existing(path: Path) -> set[tuple[str, str, int, int]]:
    if not path.exists():
        return set()
    with path.open(newline="") as handle:
        return {
            (row["algorithm"], row["property"], int(row["clients"]), int(row["depth"]))
            for row in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sweep_depth_cost", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "depth_cost.csv")
    parser.add_argument("--algorithm", default="rga", choices=sorted(ALGORITHMS), metavar="A")
    parser.add_argument("--property", default="convergence", choices=PROPERTIES, metavar="P")
    parser.add_argument("--clients", nargs="+", type=int, default=[2, 3, 4], help="one series per client count")
    parser.add_argument("--depths", nargs="+", type=int, default=[2, 3, 4, 5, 6, 7, 8])
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=300.0,
        help="stop climbing once a depth costs more than this (default 300)",
    )
    parser.add_argument("--depth-first", action="store_true", help="enumerate depth first rather than breadth first")
    parser.add_argument("--resume", action="store_true", help="skip measurements already in --out")
    arguments = parser.parse_args(argv)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    done = existing(arguments.out) if arguments.resume else set()

    print(
        f"{arguments.algorithm} / {arguments.property}, full enumeration, "
        f"clients {arguments.clients}, depths {arguments.depths}",
        file=sys.stderr,
    )

    columns = [field.name for field in fields(Measurement)]
    write_header = not arguments.out.exists() or arguments.out.stat().st_size == 0

    with arguments.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
            handle.flush()

        for clients in arguments.clients:
            for depth in sorted(arguments.depths):
                if (arguments.algorithm, arguments.property, clients, depth) in done:
                    continue

                result = enumerate_all(arguments.algorithm, arguments.property, clients, depth, arguments.depth_first)
                writer.writerow(asdict(result))
                handle.flush()

                flag = "" if result.complete else f"  INCOMPLETE ({result.note})"
                print(
                    f"  {clients} clients, depth {depth}: {result.traces:>10,} traces  "
                    f"{result.seconds:9.3f}s  {result.violations:>8,} violations{flag}",
                    file=sys.stderr,
                )

                if result.seconds > arguments.max_seconds:
                    print(
                        f"  stopping at depth {depth} for {clients} clients: "
                        f"{result.seconds:.0f}s is over the {arguments.max_seconds:.0f}s limit, "
                        f"and the next depth would be roughly ten times more",
                        file=sys.stderr,
                    )
                    break
                if not result.complete:
                    print(f"  stopping at depth {depth}: the space is not being covered", file=sys.stderr)
                    break

    print(f"wrote {arguments.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
