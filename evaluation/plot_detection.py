"""Draws the detection curve: P(a randomised search has found a violation by seed n).

    python -m plot_detection
    python -m plot_detection --out figures/detection.pdf

The measured curve is the empirical distribution of the first violating seed over the
independent searches sweep_seeds.py ran. Alongside it, as a thin reference, is the curve
that independent seeds predict from the per-trace violation rate that sweep_ops.py measured
separately: P(found by n) = 1 - (1 - p)^n. The two agreeing is the check that seeds really
are independent draws, which is the assumption the whole randomised mode rests on; the
reference is drawn only where the sweep_ops data covers the same trace length.

A horizontal rule marks 99%, and each curve is annotated with the seed count it needs to
get there, because that number is what a search budget has to be set from.

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
from figure_spec import ALGORITHMS, DETECTION_PAIRS, PROPERTIES, named  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = Path(__file__).resolve().parent

# Same validated slots and dashes as the trace-length figure, so the two read as one system.
STYLES = [
    ("#2a78d6", (None, None)),
    ("#eb6834", (5, 1.6)),
    ("#1baf7a", (1.6, 1.6)),
    ("#eda100", (5, 1.6, 1.4, 1.6)),
    ("#e87ba4", (1.4, 1.4, 4, 1.4)),
    ("#4a3aa7", (7, 1.8)),
]

INK = "#1a1a19"
MUTED = "#6b6a65"
TARGET = 99.0


def load_detection(path: Path) -> dict[tuple[str, str], dict]:
    """First-violation index per replicate, grouped by pair."""
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {"first": [], "block": 0, "ops": 0, "clients": 0})

    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            entry = grouped[(row["algorithm"], row["property"])]
            entry["first"].append(int(row["first_violation"]))
            entry["block"] = max(entry["block"], int(row["block_size"]))
            entry["ops"] = int(row["ops"])
            entry["clients"] = int(row["clients"])
    return grouped


def load_rates(path: Path) -> dict[tuple[str, str, int], tuple[int, int]]:
    """(violations, seeds) per pair and trace length, for the independence reference."""
    rates: dict[tuple[str, str, int], tuple[int, int]] = {}
    if not path.exists():
        return rates
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rates[(row["algorithm"], row["property"], int(row["ops"]))] = (int(row["violations"]), int(row["seeds"]))
    return rates


def curve(first: list[int], block: int) -> tuple[list[int], list[float]]:
    # The empirical CDF of the first violating seed. A replicate that exhausted its block
    # without a violation is recorded as 0: it is censored at `block`, so it counts in the
    # denominator but never contributes a step, which is exactly right as long as the curve
    # is not drawn past `block`.
    found = sorted(index for index in first if index > 0)
    total = len(first)

    xs = [1]
    ys = [0.0]
    seen = 0
    # Grouped by distinct seed index, because a common violation puts hundreds of searches
    # on the same index and each step has to rise by the whole tie at once.
    for index in sorted(set(found)):
        # Two points per step keeps the staircase honest rather than interpolating a rise
        # between seeds where nothing was measured.
        xs.append(index)
        ys.append(100 * seen / total)
        seen += found.count(index)
        xs.append(index)
        ys.append(100 * seen / total)

    xs.append(block)
    ys.append(100 * seen / total)
    return xs, ys


def seeds_for(target: float, first: list[int], block: int) -> int | None:
    """Smallest n at which the measured curve reaches `target`, or None if it never does."""
    found = sorted(index for index in first if index > 0)
    total = len(first)
    seen = 0
    for index in sorted(set(found)):
        seen += found.count(index)
        if 100 * seen / total >= target:
            return index
    return None


def predicted(violations: int, seeds: int, upto: int) -> tuple[list[int], list[float]] | None:
    # 1 - (1 - p)^n, the curve independent seeds imply. Undefined without an estimate of p.
    if not seeds or not violations:
        return None
    p = violations / seeds
    xs = [n for n in range(1, upto + 1) if n <= 10 or n % max(1, upto // 400) == 0]
    return xs, [100 * (1 - (1 - p) ** n) for n in xs]


def draw(detection: dict[tuple[str, str], dict], rates, pairs, show_reference: bool):
    figure, axis = plt.subplots(figsize=(3.4, 2.7), constrained_layout=True)

    block = max((entry["block"] for entry in detection.values()), default=1)
    axis.axhline(TARGET, color="#c9c8c2", linewidth=0.5, dashes=[2, 2], zorder=1)
    axis.annotate(
        f"{TARGET:.0f}%", xy=(1.05, TARGET), va="bottom", ha="left", fontsize=5.4, color=MUTED, annotation_clip=False
    )

    summary: list[tuple[str, int | None, int]] = []

    for index, (algorithm, property_name) in enumerate(pairs):
        entry = detection.get((algorithm, property_name))
        if not entry:
            continue
        colour, dash = STYLES[index % len(STYLES)]
        label = f"{named(ALGORITHMS, algorithm).short} / {named(PROPERTIES, property_name).short}"

        if show_reference:
            reference = predicted(*rates.get((algorithm, property_name, entry["ops"]), (0, 0)), entry["block"])
            if reference:
                axis.plot(*reference, color=colour, linewidth=2.2, alpha=0.22, solid_capstyle="butt", zorder=2)

        xs, ys = curve(entry["first"], entry["block"])
        line = axis.plot(xs, ys, color=colour, linewidth=1.0, zorder=3, label=label)[0]
        if dash != (None, None):
            line.set_dashes(list(dash))

        summary.append((label, seeds_for(TARGET, entry["first"], entry["block"]), len(entry["first"])))

    axis.set_xscale("log")
    axis.set_xlim(1, block)
    axis.set_ylim(-3, 103)
    axis.set_yticks([0, 25, 50, 75, 100])
    # Plain numbers rather than powers of ten, to match the trace-length figure and because
    # these are seed counts a reader compares against a budget, not magnitudes.
    ticks = [tick for tick in (1, 10, 100, 1000, 10000) if tick <= block]
    axis.set_xticks(ticks)
    axis.set_xticklabels([f"{tick:,}" for tick in ticks])
    axis.minorticks_off()
    axis.set_xlabel("Seeds checked", fontsize=7.5, color=INK)
    axis.set_ylabel("Searches that found a violation (%)", fontsize=7.5, color=INK)
    axis.grid(axis="y", color="#e6e5e0", linewidth=0.5, zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(labelsize=6.5, colors=MUTED, length=2, width=0.5)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_linewidth(0.5)
        axis.spines[side].set_color("#c9c8c2")

    # Bottom right: every curve is a rising sigmoid, so that corner is the one part of the
    # panel no line reaches. Upper left is where the fastest-detected pair goes vertical.
    #
    # The reference band needs naming or it reads as a drawing artefact, so it gets an entry
    # of its own, in grey because it is not a seventh series.
    handles, labels = axis.get_legend_handles_labels()
    if show_reference:
        handles.append(Line2D([], [], color=MUTED, linewidth=2.2, alpha=0.3, solid_capstyle="butt"))
        labels.append(r"predicted, $1-(1-p)^n$")

    axis.legend(
        handles,
        labels,
        loc="lower right",
        bbox_to_anchor=(1.0, 0.0),
        frameon=False,
        fontsize=5.8,
        labelcolor=INK,
        handlelength=2.6,
        labelspacing=0.35,
        borderpad=0,
    )
    return figure, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plot_detection", description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "data" / "detection.csv")
    parser.add_argument("--rates", type=Path, default=HERE / "data" / "violation_rate.csv")
    parser.add_argument("--out", type=Path, default=HERE / "figures" / "detection.pdf")
    parser.add_argument("--no-reference", action="store_true", help="omit the 1-(1-p)^n reference band")
    arguments = parser.parse_args(argv)

    if not arguments.data.exists():
        parser.error(f"{arguments.data} does not exist -- run sweep_seeds.py first")

    detection = load_detection(arguments.data)
    if not detection:
        parser.error(f"no rows in {arguments.data}")
    rates = load_rates(arguments.rates)

    pairs = [pair for pair in DETECTION_PAIRS if pair in detection]
    pairs += [pair for pair in detection if pair not in set(DETECTION_PAIRS)]

    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7})
    figure, summary = draw(detection, rates, pairs, not arguments.no_reference)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(arguments.out)
    preview = arguments.out.with_suffix(".png")
    figure.savefig(preview, dpi=220)
    print(f"wrote {arguments.out} and {preview}", file=sys.stderr)

    print(f"\nseeds for {TARGET:.0f}% detection (measured):", file=sys.stderr)
    for label, seeds, replicates in summary:
        reached = f"{seeds:>6d}" if seeds else "  never"
        print(f"  {label:34s} {reached}   ({replicates} searches)", file=sys.stderr)

    censored = [
        (pair, sum(1 for index in entry["first"] if index == 0), len(entry["first"]))
        for pair, entry in detection.items()
        if any(index == 0 for index in entry["first"])
    ]
    if censored:
        print("\nsearches that exhausted their block without a violation:", file=sys.stderr)
        for pair, count, total in censored:
            print(f"  {pair[0]}/{pair[1]}: {count}/{total} -- curve is a lower bound past that point", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
