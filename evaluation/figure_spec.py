"""Which algorithms appear in which panel of the violation-rate figure.

Both the sweep and the plot read this, so the cells that get measured and the lines that
get drawn cannot drift apart.

Each panel lists only algorithms that actually violate that property: a line flat on zero
says nothing the table does not already say, and it costs a colour that a violating
algorithm could have used. Within a panel the algorithms are ordered by how often they
violate on the longest traces, so the list reads top curve first, and the sets are chosen
to spread the onset -- from violations that show up in a five-operation trace to ones that
need fifty -- because the spread is the point the figure is making.

The maximal non-interleaving panel is drawn only from algorithms that satisfy *forward*
non-interleaving, so that it isolates the gap between the two properties rather than
re-showing algorithms that fail both.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Named:
    """A property or an algorithm: its name in the CSV, and how to write it."""

    key: str
    label: str  # panel titles and legends
    short: str  # the label at the end of a line, where there is far less room


# Table 1's column order, which is also the order the properties are introduced in.
PROPERTIES = [
    Named("convergence", "Convergence", "Conv."),
    Named("weak-list-spec", "Weak list spec.", "Weak"),
    Named("strong-list-spec", "Strong list spec.", "Strong"),
    Named("forward-interleaving", "Forward non-interleaving", "Forward"),
    Named("interleaving", "Maximal non-interleaving", "Maximal"),
]

ALGORITHMS = [
    Named("abt", "ABT", "ABT"),
    Named("adopted-randolph", "AdOPTed + Randolph", "Randolph"),
    Named("adopted-ressel", "AdOPTed + Ressel", "Ressel"),
    Named("adopted-tm11", "AdOPTed + TM1.1", "TM1.1"),
    Named("cot", "COT", "COT"),
    Named("diffsync", "Diffsync", "Diffsync"),
    Named("dopt", "dOPT + Ellis", "dOPT"),
    Named("easysync", "Etherpad (EasySync)", "EasySync"),
    Named("fugue", "Fugue", "Fugue"),
    Named("got", "GOT", "GOT"),
    Named("jupiter", "Jupiter", "Jupiter"),
    Named("lbt", "LBT", "LBT"),
    Named("logoot", "Logoot", "Logoot"),
    Named("loro", "Loro", "Loro"),
    Named("lseq", "LSEQ", "LSEQ"),
    Named("prosemirror", "ProseMirror", "ProseMirror"),
    Named("rga", "RGA", "RGA"),
    Named("sdt", "SDT", "SDT"),
    Named("sharedb", "ShareDB", "ShareDB"),
    Named("soct4", "SOCT4", "SOCT4"),
    Named("sync7", "Sync7", "Sync7"),
    Named("tibot", "TIBOT", "TIBOT"),
    Named("treedoc", "TreeDoc", "TreeDoc"),
    Named("soct2", "SOCT2 + TTF", "SOCT2"),
    Named("soct3", "SOCT3 + TTF", "SOCT3"),
    Named("woot", "WOOT", "WOOT"),
    Named("yjs", "Yjs", "Yjs"),
]

# Avoid putting two of these in the same panel: they induce the same ordering, so their
# curves coincide at every point and the second one reads as a plotting fault rather than
# as a result. Each group is interchangeable, not additive.
EQUIVALENT = [
    ("tibot", "tibot2"),
    ("cot", "pot"),
    ("woot", "wooto"),
    ("abt", "adopted-tombstone"),
    ("automerge", "rga"),
]

PANELS: dict[str, list[str]] = {
    "convergence": ["dopt", "lbt", "sdt", "got", "adopted-ressel", "sync7"],
    # "weak-list-spec": ["adopted-tm11", "diffsync", "lbt", "adopted-ressel", "prosemirror"],
    "strong-list-spec": ["cot", "jupiter", "easysync", "sharedb", "tibot", "soct4"],
    "forward-interleaving": ["treedoc", "logoot", "lseq", "woot", "soct3", "soct4"],
    "interleaving": ["rga", "yjs", "loro", "collabs", "loro", "fugue"],
}


# Pairs for the detection-curve figure (sweep_seeds.py, plot_detection.py): how many seeds a
# randomised search needs before it finds a violation.
#
# Chosen to span the per-trace violation probability rather than to be representative --
# from roughly 0.4% to 80% at ten operations, which is three orders of magnitude in the
# number of seeds required -- with all five properties represented. A pair whose violations
# are common is what makes the cheap end of the curve legible; a rare one sets the budget.
DETECTION_PAIRS: list[tuple[str, str]] = [
    ("jupiter", "strong-list-spec"),
    ("prosemirror", "weak-list-spec"),
    ("fugue", "interleaving"),
    ("adopted-tm11", "weak-list-spec"),
    ("got", "convergence"),
    ("adopted-ressel", "convergence"),
]


def cells() -> list[tuple[str, str]]:
    """Every (algorithm, property) pair the figure needs, deduplicated.

    A panel listing the same algorithm twice is a typo rather than an instruction to measure
    it twice, so the pairs are deduplicated here; the panel itself still draws what it lists.
    """
    seen: dict[tuple[str, str], None] = {}
    for property_name, algorithms in PANELS.items():
        for algorithm in algorithms:
            seen[(algorithm, property_name)] = None
    return list(seen)


def named(known: list[Named], key: str) -> Named:
    """The display names for a key, falling back to the key itself for anything unlisted."""
    for item in known:
        if item.key == key:
            return item
    return Named(key, key, key)
