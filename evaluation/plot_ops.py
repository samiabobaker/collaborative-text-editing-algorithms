"""Draws the violation-rate-against-trace-length figure from sweep_ops.py's CSV.

    python -m plot_ops
    python -m plot_ops --facet algorithm
    python -m plot_ops --data data/violation_rate.csv --out figures/violation_rate.pdf

By default each panel is one property and carries only the algorithms that violate it,
which figure_spec.py lists per property. Because the panels then have different lines there
is no legend to share, so every line is named where it leaves the axis; colour separates
the lines within a panel and carries no meaning across panels.

--facet property or --facet algorithm instead draws one shared set of lines in every panel,
with a legend, which is what a cross-product sweep produces.

The output is a vector PDF sized for a two-column \\figure* and, next to it, a PNG for
looking at while iterating.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from figure_spec import ALGORITHMS, PANELS, PROPERTIES, Named, named  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = Path(__file__).resolve().parent

# Slots of a categorical palette validated for colour-vision deficiency, assigned in fixed
# order to the lines within a panel. The dash and the marker repeat the same distinction,
# so the figure survives being printed in greyscale.
#
# Six lines is past what any six hues can keep apart for every pair at once, and here every
# pair genuinely does need it: each curve starts at zero and several saturate at 100, so
# measured against the data every pair comes within a few percentage points of another
# somewhere. Violet is in the sixth slot rather than the palette's green because green
# against the second slot's orange is the pair that both runs together on the page and is
# indistinguishable under protanopia (dE 3.2). With violet there the worst remaining pair
# is in the band that secondary encoding covers, which is why every line here carries its
# own dash, marker and label rather than colour alone. Do not extend a panel past six.
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

X_LABELS = {"ops": "Operations per trace", "clients": "Clients"}


def load(
    path: Path, x_column: str, held: int | None
) -> tuple[dict[tuple[str, str], list[tuple[int, float]]], dict[str, int]]:
    # Returns the points keyed by (algorithm, property), and the seed count seen per
    # algorithm so a caption can state the sample size rather than have it hardcoded.
    #
    # The two sweeps share a schema and differ only in which column varies: sweep_ops fixes
    # the clients and varies the operations, sweep_clients does the reverse. `held` filters
    # the other one so a CSV holding several of its values still draws one curve per series.
    other = "clients" if x_column == "ops" else "ops"
    series: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    seeds: dict[str, int] = {}

    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if held is not None and int(row[other]) != held:
                continue
            series[(row["algorithm"], row["property"])].append((int(row[x_column]), 100 * float(row["violation_rate"])))
            seeds[row["algorithm"]] = max(seeds.get(row["algorithm"], 0), int(row["seeds"]))

    for points in series.values():
        points.sort()
    return series, seeds


def spread(values: list[float], gap: float, low: float, high: float) -> list[float]:
    # Pushes labels apart until none are within `gap` of another, moving each as little as
    # possible in either direction rather than stacking them all upwards, then clamps the
    # result into the axis. Relaxation rather than a closed form because the clamping at
    # both ends can otherwise reintroduce an overlap it has just resolved.
    placed = list(values)

    for _ in range(200):
        moved = False
        for index in range(len(placed) - 1):
            overlap = gap - (placed[index + 1] - placed[index])
            if overlap > 1e-9:
                placed[index] -= overlap / 2
                placed[index + 1] += overlap / 2
                moved = True

        placed = [min(max(value, low), high) for value in placed]
        if not moved:
            break

    return placed


def place_labels(axis, x: float, leader_from: float, labels: list[tuple[float, str, str]]) -> None:
    # Direct labels at the right-hand end of each line, inside the axis: the x limit leaves
    # room for them, so they cannot be clipped by the figure edge the way an annotation
    # placed outside the axis would be.
    #
    # Lines routinely end at the same rate, and in the default layout these labels are the
    # only thing naming a line at all, so a label that had to be displaced to be legible
    # gets a leader back to the value it belongs to and never silently stands somewhere its
    # line does not reach.
    labels.sort()
    placed = spread([y for y, _, _ in labels], gap=5.6, low=0.0, high=100.0)

    for (y, text, colour), position in zip(labels, placed, strict=True):
        if abs(position - y) > 1.2:
            # `leader_from` is the end of the line rather than an offset from the label,
            # because on a log axis a fixed offset in data units is not a fixed distance.
            axis.plot([leader_from, x], [y, position], color=colour, linewidth=0.4, clip_on=False, zorder=2)
        axis.annotate(text, xy=(x, position), va="center", ha="left", fontsize=5.4, color=colour, annotation_clip=False)


def geometry(shortest: int, widest: int, log_x: bool) -> tuple[float, float, float]:
    """Left limit, right limit, and the x the end-of-line labels sit at."""
    if log_x:
        # A ratio, not an addend: on a log axis a fixed offset is not a fixed distance.
        return shortest * 0.9, widest * 2.2, widest * 1.15
    if widest <= 12:
        # A client-count axis: a handful of small integers, so the margin is proportionally
        # wider to leave the labels room next to a very short span.
        span = widest - shortest + 1
        return shortest - 0.4, widest + span * 0.55, widest + span * 0.09
    return 0, widest * 1.34, widest * 1.06


def style_axis(axis, title: str, shortest: int, widest: int, last_in_column: bool, log_x: bool) -> None:
    axis.set_title(title, fontsize=7.5, color=INK, pad=3)

    if log_x:
        # The onset of a violation spans a wide ratio of trace lengths rather than a wide
        # difference, and the lengths are sampled densely at the short end, so a linear axis
        # spends most of its width on the region where the curves have stopped moving.
        # The margin for the end-of-line labels has to be a ratio here, not an addend.
        axis.set_xscale("log")
        axis.set_xlim(*geometry(shortest, widest, log_x)[:2])
        ticks = [tick for tick in (2, 3, 5, 10, 20, 30, 50, 100) if shortest <= tick <= widest]
        axis.set_xticks(ticks)
        axis.set_xticklabels([str(tick) for tick in ticks])
        # Log minor ticks would crowd a panel this size, and the majors are already labelled.
        axis.minorticks_off()
    elif widest <= 12:
        # Every client count measured gets its own tick; there are only a handful.
        axis.set_xlim(*geometry(shortest, widest, log_x)[:2])
        axis.set_xticks(list(range(shortest, widest + 1)))
    else:
        axis.set_xlim(*geometry(shortest, widest, log_x)[:2])
        # Ticks stop at the longest trace measured; past that is the label margin, not data.
        axis.set_xticks([tick for tick in (0, 10, 20, 30, 40, 50, 60, 80, 100) if tick <= widest])

    # Linear in every case: the rates run from zero to saturation, a log axis cannot place
    # the zeros -- a quarter of the points here are exactly zero -- and it compresses the
    # difference between a curve that reaches 100% and one that plateaus in the teens, which
    # is one of the readings the figure exists for.
    axis.set_ylim(-3, 103)
    axis.set_yticks([0, 25, 50, 75, 100])
    axis.grid(axis="y", color="#e6e5e0", linewidth=0.5, zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(labelsize=6.5, colors=MUTED, length=2, width=0.5)
    # A shared x axis draws the tick labels on the bottom row only, which leaves a column
    # whose last row is a spare cell with no scale at all. Whichever panel is last in its
    # column carries them.
    if last_in_column:
        axis.tick_params(labelbottom=True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_linewidth(0.5)
        axis.spines[side].set_color("#c9c8c2")


def draw_panel(
    axis, lines: list[tuple[Named, list[tuple[int, float]]]], label_x: float, leader_from: float, label_lines: bool
) -> None:
    labels: list[tuple[float, str, str]] = []

    for index, (line, points) in enumerate(lines):
        colour, dash, marker = STYLES[index]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]

        drawn = axis.plot(
            xs, ys, color=colour, linewidth=1.1, marker=marker, markersize=2.4, markeredgewidth=0, zorder=3
        )[0]
        if dash != (None, None):
            drawn.set_dashes(list(dash))

        labels.append((ys[-1], line.short, colour))

    if label_lines and labels:
        place_labels(axis, label_x, leader_from, labels)


def figure_grid(count: int, columns: int):
    rows = -(-count // columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(7.0, 1.85 * rows), sharex=True, sharey=True, constrained_layout=True
    )
    flat = list(axes.flat) if hasattr(axes, "flat") else [axes]
    return figure, flat


def finish(figure, x_column: str) -> None:
    figure.supxlabel(X_LABELS[x_column], fontsize=7.5, color=INK)
    figure.supylabel("Traces with a violation (%)", fontsize=7.5, color=INK)


def draw_spec(series, columns: int, label_lines: bool, log_x: bool, x_column: str):
    """One panel per property, each with only the algorithms that violate it."""
    panels = [item for item in PROPERTIES if PANELS.get(item.key)]
    figure, flat = figure_grid(len(panels), columns)

    lengths = sorted({x for points in series.values() for x, _ in points})
    shortest = lengths[0] if lengths else 1
    widest = lengths[-1] if lengths else 1
    _, _, label_x = geometry(shortest, widest, log_x)

    missing: list[str] = []
    for index, (axis, panel) in enumerate(zip(flat, panels, strict=False)):
        lines = []
        for key in PANELS[panel.key]:
            points = series.get((key, panel.key))
            if points:
                lines.append((named(ALGORITHMS, key), points))
            else:
                missing.append(f"{key}/{panel.key}")

        draw_panel(axis, lines, label_x, widest, label_lines)
        style_axis(axis, panel.label, shortest, widest, index + columns >= len(panels), log_x)

    for axis in flat[len(panels) :]:
        axis.set_visible(False)

    if missing:
        print(f"warning: no rows for {', '.join(missing)} -- run sweep_ops.py", file=sys.stderr)

    finish(figure, x_column)
    return figure


def draw_uniform(
    series,
    panels: list[Named],
    lines: list[Named],
    by_property: bool,
    columns: int,
    label_lines: bool,
    log_x: bool,
    x_column: str,
):
    """One shared set of lines in every panel, with a legend, for a cross-product sweep."""
    figure, flat = figure_grid(len(panels), columns)

    lengths = sorted({x for points in series.values() for x, _ in points})
    shortest = lengths[0] if lengths else 1
    widest = lengths[-1] if lengths else 1
    _, _, label_x = geometry(shortest, widest, log_x)

    for index, (axis, panel) in enumerate(zip(flat, panels, strict=False)):
        drawn = []
        for line in lines:
            key = (line.key, panel.key) if by_property else (panel.key, line.key)
            points = series.get(key)
            if points:
                drawn.append((line, points))

        draw_panel(axis, drawn, label_x, widest, label_lines)
        style_axis(axis, panel.label, shortest, widest, index + columns >= len(panels), log_x)

    handles = [
        Line2D(
            [],
            [],
            color=STYLES[index][0],
            linewidth=1.1,
            dashes=list(STYLES[index][1]) if STYLES[index][1] != (None, None) else (None, None),
            marker=STYLES[index][2],
            markersize=2.6,
            markeredgewidth=0,
            label=line.label,
        )
        for index, line in enumerate(lines)
    ]

    spare = len(flat) - len(panels)
    if spare:
        # An empty cell in the grid is a better home for the legend than a band across the
        # figure: it costs no height, and it sits at the end of the reading order.
        host = flat[len(panels)]
        host.set_axis_off()
        host.legend(
            handles=handles,
            loc="center left",
            frameon=False,
            fontsize=6.8,
            labelcolor=INK,
            handlelength=2.4,
            labelspacing=0.85,
            borderpad=0,
        )
        for axis in flat[len(panels) + 1 :]:
            axis.set_visible(False)
    else:
        # Above the panels rather than below: constrained_layout gives the bottom strip to
        # supxlabel, and a legend placed there lands on top of it.
        figure.legend(
            handles=handles,
            loc="outside upper center",
            ncol=len(handles),
            frameon=False,
            fontsize=6.8,
            labelcolor=INK,
            handlelength=2.4,
            columnspacing=1.4,
            borderpad=0.2,
        )

    finish(figure, x_column)
    return figure


def resolve(known: list[Named], present: set[str], chosen: list[str] | None) -> list[Named]:
    # Keeps the documented order for the names we know about and appends anything else
    # alphabetically, so a sweep over algorithms this script has never heard of still draws.
    if chosen:
        return [named(known, key) for key in chosen]

    ordered = [item for item in known if item.key in present]
    extra = sorted(present - {item.key for item in known})
    return ordered + [Named(key, key, key) for key in extra]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plot_ops", description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "data" / "violation_rate.csv")
    parser.add_argument("--out", type=Path, default=HERE / "figures" / "violation_rate.pdf")
    parser.add_argument(
        "--facet",
        choices=("property", "algorithm"),
        help="draw one shared set of lines in every panel instead of the figure's per-property sets",
    )
    parser.add_argument("--algorithms", nargs="+", help="--facet only: which algorithms to draw, in order")
    parser.add_argument("--properties", nargs="+", help="--facet only: which properties to draw, in order")
    parser.add_argument(
        "--x",
        choices=("ops", "clients"),
        default="ops",
        help="what varies along the x axis: trace length (sweep_ops) or client count (sweep_clients)",
    )
    parser.add_argument(
        "--held",
        type=int,
        help="the value of the other column to keep, when the CSV holds several "
        "(defaults to 3 clients for --x ops, and to every row for --x clients)",
    )
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument(
        "--log-x",
        action="store_true",
        help="log scale for trace length, which spreads the onset region the curves turn in",
    )
    parser.add_argument("--no-labels", action="store_true", help="--facet only: legend without labels at the line ends")
    arguments = parser.parse_args(argv)

    if not arguments.data.exists():
        parser.error(f"{arguments.data} does not exist -- run sweep_ops.py first")

    # sweep_ops writes many client counts only if asked, but its default CSV is all one
    # count; sweep_clients always writes one trace length. Defaulting the filter this way
    # means neither sweep needs --held in the common case.
    held = arguments.held if arguments.held is not None else (3 if arguments.x == "ops" else None)
    series, seeds = load(arguments.data, arguments.x, held)
    if not series:
        parser.error(f"no rows in {arguments.data} matching --x {arguments.x} --held {held}")

    # ACM rejects Type 3 fonts, which is what matplotlib embeds by default.
    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7})

    if arguments.facet:
        algorithms = resolve(ALGORITHMS, {algorithm for algorithm, _ in series}, arguments.algorithms)
        properties = resolve(PROPERTIES, {property_name for _, property_name in series}, arguments.properties)
        by_property = arguments.facet == "property"
        panels, lines = (properties, algorithms) if by_property else (algorithms, properties)

        if len(lines) > len(STYLES):
            parser.error(f"{len(lines)} lines per panel but only {len(STYLES)} styles -- narrow it down")

        figure = draw_uniform(
            series,
            panels,
            lines,
            by_property,
            arguments.columns,
            not arguments.no_labels,
            arguments.log_x,
            arguments.x,
        )
    else:
        oversized = {name: keys for name, keys in PANELS.items() if len(keys) > len(STYLES)}
        if oversized:
            parser.error(f"more than {len(STYLES)} algorithms in {', '.join(oversized)} -- see STYLES in this file")

        # Without a shared legend the end-of-line labels are the only thing naming a line,
        # so they are not optional here.
        figure = draw_spec(series, arguments.columns, label_lines=True, log_x=arguments.log_x, x_column=arguments.x)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(arguments.out)
    preview = arguments.out.with_suffix(".png")
    figure.savefig(preview, dpi=220)

    drawn = sorted({key for keys in PANELS.values() for key in keys} if not arguments.facet else seeds)
    sample = ", ".join(f"{key}: {seeds[key]}" for key in drawn if key in seeds)
    print(f"wrote {arguments.out} and {preview}", file=sys.stderr)
    print(f"seeds per point -- {sample}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
