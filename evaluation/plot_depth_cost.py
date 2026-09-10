"""Draws the cost of a full exhaustive search against the number of operations per execution.

    python -m plot_depth_cost
    python -m plot_depth_cost --y traces
    python -m plot_depth_cost --budgets 60 3600

One line per client count, log y, because the space grows geometrically: a straight line
here is a constant branching factor, and its slope is that factor. Horizontal rules mark
time budgets, so the figure can be read the way the question is actually asked -- not "how
long does depth 7 take" but "what depth fits in the time I have".

--y traces plots the size of the space instead of the time to cover it, which is the
machine-independent version of the same curve.
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

# Slots 1-6 of the validated palette, assigned by client count in ascending order.
STYLES = [
    ("#2a78d6", (None, None), "o"),
    ("#eb6834", (5, 1.6), "s"),
    ("#1baf7a", (1.6, 1.6), "^"),
    ("#eda100", (5, 1.6, 1.4, 1.6), "D"),
    ("#e87ba4", (1.4, 1.4, 4, 1.4), "v"),
    ("#4a3aa7", (7, 1.8), "P"),
]

INK = "#1a1a19"
MUTED = "#6b6a65"

# Rules worth drawing on a cost axis, and how to say them in words.
BUDGET_LABELS = [(1, "1s"), (60, "1 min"), (3600, "1 hour"), (86400, "1 day"), (604800, "1 week")]


def load(path: Path, algorithm: str | None, property_name: str | None):
    series: dict[int, list[tuple[int, float, int, bool]]] = defaultdict(list)
    pairs: set[tuple[str, str]] = set()

    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if algorithm and row["algorithm"] != algorithm:
                continue
            if property_name and row["property"] != property_name:
                continue
            pairs.add((row["algorithm"], row["property"]))
            series[int(row["clients"])].append(
                (int(row["depth"]), float(row["seconds"]), int(row["traces"]), bool(int(row["complete"])))
            )

    for points in series.values():
        points.sort()
    return series, pairs


def extrapolate(points: list[tuple[int, float, int, bool]], column: int, to_depth: int):
    # The last two measured depths give the branching factor, which is what makes it
    # meaningful to say anything about depths nobody has run. Drawn dotted and never
    # presented as measurement.
    if len(points) < 2:
        return None
    (depth_a, *values_a), (depth_b, *values_b) = points[-2], points[-1]
    previous, latest = values_a[column - 1], values_b[column - 1]
    if previous <= 0 or latest <= 0 or depth_b <= depth_a:
        return None

    factor = (latest / previous) ** (1 / (depth_b - depth_a))
    xs = list(range(depth_b, to_depth + 1))
    return xs, [latest * factor ** (x - depth_b) for x in xs], factor


def draw(series, pairs, column: int, budgets: list[float], to_depth: int):
    figure, axis = plt.subplots(figsize=(3.4, 2.8), constrained_layout=True)
    seconds = column == 1

    if seconds:
        for budget, label in BUDGET_LABELS:
            if budget in budgets:
                axis.axhline(budget, color="#c9c8c2", linewidth=0.5, dashes=[2, 2], zorder=1)
                axis.annotate(
                    label,
                    xy=(0.01, budget),
                    xycoords=("axes fraction", "data"),
                    va="bottom",
                    ha="left",
                    fontsize=5.4,
                    color=MUTED,
                )

    for index, clients in enumerate(sorted(series)):
        points = series[clients]
        colour, dash, marker = STYLES[index % len(STYLES)]
        xs = [p[0] for p in points]
        ys = [p[column] for p in points]

        line = axis.plot(
            xs,
            ys,
            color=colour,
            linewidth=1.1,
            marker=marker,
            markersize=2.6,
            markeredgewidth=0,
            zorder=3,
            label=f"{clients} clients",
        )[0]
        if dash != (None, None):
            line.set_dashes(list(dash))

        projected = extrapolate(points, column, to_depth)
        if projected:
            forward_x, forward_y, _ = projected
            axis.plot(forward_x, forward_y, color=colour, linewidth=0.8, dashes=[1, 1.6], alpha=0.6, zorder=2)

    axis.set_yscale("log")
    axis.set_xlabel("Operations per execution", fontsize=7.5, color=INK)
    axis.set_ylabel("Seconds to cover the space" if seconds else "Executions in the space", fontsize=7.5, color=INK)
    axis.grid(axis="y", color="#e6e5e0", linewidth=0.5, zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(labelsize=6.5, colors=MUTED, length=2, width=0.5)
    axis.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_linewidth(0.5)
        axis.spines[side].set_color("#c9c8c2")

    if len(pairs) == 1:
        algorithm, property_name = next(iter(pairs))
        axis.set_title(
            f"{named(ALGORITHMS, algorithm).label}, {named(PROPERTIES, property_name).label.lower()}",
            fontsize=7.5,
            color=INK,
            pad=3,
        )

    axis.legend(
        loc="upper left",
        frameon=False,
        fontsize=6.2,
        labelcolor=INK,
        handlelength=2.4,
        labelspacing=0.35,
        borderpad=0,
    )
    return figure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plot_depth_cost", description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "data" / "depth_cost.csv")
    parser.add_argument("--out", type=Path, default=HERE / "figures" / "depth_cost.pdf")
    parser.add_argument("--algorithm", help="filter, when the CSV holds more than one")
    parser.add_argument("--property", help="filter, when the CSV holds more than one")
    parser.add_argument("--y", choices=("seconds", "traces"), default="seconds")
    parser.add_argument("--budgets", nargs="*", type=float, default=[60, 3600, 86400], help="rules to draw, in seconds")
    parser.add_argument("--to-depth", type=int, default=0, help="extrapolate the trend out to this depth (0 for none)")
    arguments = parser.parse_args(argv)

    if not arguments.data.exists():
        parser.error(f"{arguments.data} does not exist -- run sweep_depth_cost.py first")

    series, pairs = load(arguments.data, arguments.algorithm, arguments.property)
    if not series:
        parser.error(f"no matching rows in {arguments.data}")
    if len(pairs) > 1:
        parser.error(f"{arguments.data} holds {len(pairs)} pairs; narrow it with --algorithm / --property")

    column = 1 if arguments.y == "seconds" else 2
    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7})
    figure = draw(series, pairs, column, arguments.budgets, arguments.to_depth)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(arguments.out)
    preview = arguments.out.with_suffix(".png")
    figure.savefig(preview, dpi=220)
    print(f"wrote {arguments.out} and {preview}", file=sys.stderr)

    algorithm, property_name = next(iter(pairs))
    print(f"\n{algorithm} / {property_name}, full enumeration:", file=sys.stderr)
    for clients in sorted(series):
        points = series[clients]
        deepest = points[-1]
        projected = extrapolate(points, column, arguments.to_depth or deepest[0])
        factor = f", x{projected[2]:.1f} per operation" if projected else ""
        print(
            f"  {clients} clients: measured to depth {deepest[0]} "
            f"({deepest[2]:,} executions, {deepest[1]:.1f}s){factor}",
            file=sys.stderr,
        )
        if projected and arguments.to_depth > deepest[0]:
            for depth, value in zip(projected[0], projected[1], strict=True):
                if depth > deepest[0]:
                    unit = f"{value:,.0f}s ({value / 3600:,.1f} h)" if column == 1 else f"{value:,.0f} executions"
                    print(f"      depth {depth} would be about {unit}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
