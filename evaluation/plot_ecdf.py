"""Draws the ECDF of time to first violation, one curve per search strategy.

    python -m plot_ecdf
    python -m plot_ecdf --x work
    python -m plot_ecdf --strategies random bfs dfs

Read a point as: by this much time, that strategy had found a violation in this fraction of
the benchmark. A curve that is further left is faster; a curve that ends higher solves more
of the benchmark at all. Because a strategy can run out of budget, or exhaust the whole space
to its depth without finding anything, the curves plateau below 100% rather than reaching it
-- where each one stops is as much of the result as its shape.

--x work plots traces enumerated (or seeds sampled) instead of seconds, which takes the
machine out of the comparison. It is the fairer axis for comparing search orders against each
other, since they cost the same per trace; seconds is the fairer axis for comparing
randomised sampling against exhaustive enumeration, which do not.

Single-column width, since it is one panel.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from figure_spec import ALGORITHMS, PROPERTIES, named  # noqa: E402

HERE = Path(__file__).resolve().parent

# Same validated slots and dashes as the other figures, so the set reads as one system.
STYLES = {
    "random": ("#2a78d6", (None, None), "Random sampling"),
    "bfs": ("#eb6834", (5, 1.6), "Exhaustive, BFS"),
    "dfs": ("#1baf7a", (1.6, 1.6), "Exhaustive, DFS"),
    "bfs-random": ("#eda100", (5, 1.6, 1.4, 1.6), "Exhaustive, BFS, shuffled"),
    "dfs-random": ("#e87ba4", (1.4, 1.4, 4, 1.4), "Exhaustive, DFS, shuffled"),
}
ORDER = list(STYLES)

INK = "#1a1a19"
MUTED = "#6b6a65"


def load(path: Path, column: str) -> tuple[dict[str, list[float]], dict[str, int], set[tuple[str, str]]]:
    """Per strategy: the costs of the pairs it solved, and how many pairs it attempted."""
    solved: dict[str, list[float]] = defaultdict(list)
    attempted: dict[str, int] = defaultdict(int)
    benchmark: set[tuple[str, str]] = set()

    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            strategy = row["strategy"]
            attempted[strategy] += 1
            benchmark.add((row["algorithm"], row["property"]))
            if row["outcome"] == "found":
                value = float(row[column])
                # A search that finishes inside the clock's resolution still did work; a zero
                # would be dropped by the log axis, so it is floored rather than discarded.
                solved[strategy].append(max(value, 1e-6 if column == "seconds" else 1))

    return solved, attempted, benchmark


def draw(solved, attempted, benchmark: set, column: str, strategies: list[str]):
    figure, axis = plt.subplots(figsize=(3.4, 3.0), constrained_layout=True)

    summary: list[tuple[str, int, int, float | None]] = []

    single = len(benchmark) == 1

    for strategy in strategies:
        costs = sorted(solved.get(strategy, []))
        total = attempted.get(strategy, 0)
        if not total:
            continue
        colour, dash, label = STYLES[strategy]

        # The denominator is the whole benchmark, not the pairs this strategy solved, so the
        # curves are comparable and each one's plateau shows what it could not do.
        xs = [0.0]
        ys = [0.0]
        for position, cost in enumerate(costs, start=1):
            xs.append(cost)
            ys.append(100 * (position - 1) / total)
            xs.append(cost)
            ys.append(100 * position / total)

        line = axis.plot(xs[1:], ys[1:], color=colour, linewidth=1.1, zorder=3, label=label)[0]
        if dash != (None, None):
            line.set_dashes(list(dash))

        median = costs[len(costs) // 2] if len(costs) * 2 >= total else None
        summary.append((label, len(costs), total, median))

    axis.set_xscale("log")
    # Plain numbers rather than powers of ten, to match the other figures; the minor ticks a
    # log axis adds by default crowd a panel this size and the majors are already labelled.
    axis.minorticks_off()
    if column == "seconds":
        low = min((min(v) for v in solved.values() if v), default=1e-3)
        high = max((max(v) for v in solved.values() if v), default=1.0)
        ticks = [tick for tick in (1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100) if low / 3 <= tick <= high * 3]
        axis.set_xticks(ticks)
        axis.set_xticklabels([f"{tick:g}" for tick in ticks])
    axis.set_ylim(-3, 103)
    axis.set_yticks([0, 25, 50, 75, 100])
    axis.set_xlabel(
        "Seconds to first violation" if column == "seconds" else "Traces checked to first violation",
        fontsize=7.5,
        color=INK,
    )
    if single:
        (algorithm, property_name) = next(iter(benchmark))
        axis.set_ylabel("Runs that found a violation (%)", fontsize=7.5, color=INK)
        axis.set_title(
            f"{named(ALGORITHMS, algorithm).label}, {named(PROPERTIES, property_name).label.lower()}",
            fontsize=7.5,
            color=INK,
            pad=3,
        )
    else:
        axis.set_ylabel(f"Benchmark solved (%, n={len(benchmark)})", fontsize=7.5, color=INK)
    axis.grid(axis="y", color="#e6e5e0", linewidth=0.5, zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(labelsize=6.5, colors=MUTED, length=2, width=0.5)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_linewidth(0.5)
        axis.spines[side].set_color("#c9c8c2")

    figure.legend(
        *axis.get_legend_handles_labels(),
        loc="outside lower center",
        ncol=2,
        frameon=False,
        fontsize=5.8,
        labelcolor=INK,
        handlelength=2.6,
        columnspacing=1.2,
        labelspacing=0.35,
        borderpad=0,
    )
    return figure, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plot_ecdf", description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "data" / "time_to_violation.csv")
    parser.add_argument("--out", type=Path, default=HERE / "figures" / "time_to_violation.pdf")
    parser.add_argument("--x", choices=("seconds", "work"), default="seconds", help="what to measure cost in")
    parser.add_argument("--strategies", nargs="+", choices=ORDER, default=ORDER, metavar="S")
    arguments = parser.parse_args(argv)

    if not arguments.data.exists():
        parser.error(f"{arguments.data} does not exist -- run sweep_time_to_violation.py first")

    solved, attempted, benchmark = load(arguments.data, arguments.x)
    if not attempted:
        parser.error(f"no rows in {arguments.data}")

    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7})
    figure, summary = draw(solved, attempted, benchmark, arguments.x, arguments.strategies)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(arguments.out)
    preview = arguments.out.with_suffix(".png")
    figure.savefig(preview, dpi=220)
    print(f"wrote {arguments.out} and {preview}", file=sys.stderr)

    if len(benchmark) == 1:
        print(f"\n{next(iter(benchmark))[0]} / {next(iter(benchmark))[1]}, repeated runs:", file=sys.stderr)
    else:
        print(f"\nbenchmark of {len(benchmark)} (algorithm, property) pairs:", file=sys.stderr)
    for label, found, tried, median in summary:
        middle = f"median {median:.2f}" if median is not None else "never reaches half"
        print(f"  {label:28s} solved {found:>3d}/{tried:<3d}  {middle}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
