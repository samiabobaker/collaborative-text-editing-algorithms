from typing import Any

from diffsync.diffsyncmyers import DIFF_DELETE, DIFF_EQUAL, DIFF_INSERT, Diff, diff_texts

# A patch entry is [pos, delete_len, insert_text], meaning: at position pos of
# the input text, delete delete_len characters and insert insert_text. Applying
# the patch computed as a -> b to text a yields b. Entries are ordered by
# position in the input text.
Patch = list[list[Any]]


def to_patch(diff: Diff, factor: int = 1) -> Patch:
    """Convert a diff into a patch, fusing adjacent non-equal entries into one.

    A factor of -1 swaps the roles of insert and delete, which produces the
    reverse patch.
    """
    patch: Patch = []
    position = 0
    i = 0
    while i < len(diff):
        entry = diff[i]
        if entry[0] == DIFF_EQUAL:
            position += len(entry[1])
            i += 1
            continue
        merged: list[Any] = [position, 0, ""]
        if entry[0] == DIFF_INSERT * factor:
            merged[2] = entry[1]
        elif entry[0] == DIFF_DELETE * factor:
            merged[1] = len(entry[1])
            position += merged[1]
        if i + 1 < len(diff):
            entry = diff[i + 1]
            if entry[0] != DIFF_EQUAL:
                if entry[0] == DIFF_INSERT * factor:
                    merged[2] = entry[1]
                elif entry[0] == DIFF_DELETE * factor:
                    merged[1] = len(entry[1])
                    position += merged[1]
                i += 1
        patch.append(merged)
        i += 1
    return patch


def get_diff_patch(a: str, b: str) -> Patch:
    """The patch taking a to b."""
    return to_patch(diff_texts(a, b))


def get_diff_patch_2(a: str, b: str) -> tuple[Patch, Patch]:
    """Both directions at once: the patch taking a to b, and the one taking b to a.

    Both come from a single diff, so they describe the same alignment.
    """
    diff = diff_texts(a, b)
    return to_patch(diff), to_patch(diff, -1)


def apply_diff_patch(s: str, patch: Patch) -> str:
    """Apply a patch to a text.

    Positions are relative to the input text, so an offset accumulates as earlier
    entries change the length.
    """
    offset = 0
    for entry in patch:
        s = s[: entry[0] + offset] + entry[2] + s[entry[0] + offset + entry[1] :]
        offset += len(entry[2]) - entry[1]
    return s


def get_merged_diff_patch(a: str, b: str, o: str) -> Patch:
    """Three-way merge of the patches o -> a and o -> b, against merge base o.

    Entries are consumed in order of position; a tie on position is broken by
    the lexicographically smaller insertion text, and a tie there in favour of
    b. When an entry's delete range starts strictly before the previous entry's
    delete range ends, both sides edited the same region: the two are fused,
    the delete range becoming the union of the two ranges and the insertions
    being concatenated in the order they were consumed.

    So a conflicting edit never loses. Where git would emit conflict markers,
    this keeps both sides' insertions and applies both sides' deletions, with
    no choice of a winning side. That is not a convergence guarantee: the two
    sides are aligned only by position in the base, several minimal diffs can
    describe the same edit, and fusing overlapping entries widens what is
    deleted, so a merge can revive a deleted character or order the survivors
    in ways neither side wrote. The examples show both, and it is a property
    of the algorithm rather than of this port.
    """
    a_diff = get_diff_patch(o, a)
    b_diff = get_diff_patch(o, b)
    merged: Patch = []
    previous: list[Any] | None = None
    while len(a_diff) > 0 or len(b_diff) > 0:
        if len(a_diff) == 0:
            entry = b_diff.pop(0)
        elif len(b_diff) == 0 or a_diff[0][0] < b_diff[0][0]:
            entry = a_diff.pop(0)
        elif a_diff[0][0] > b_diff[0][0]:
            entry = b_diff.pop(0)
        elif a_diff[0][2] < b_diff[0][2]:
            entry = a_diff.pop(0)
        else:
            entry = b_diff.pop(0)
        if previous is not None and entry[0] < previous[0] + previous[1]:
            # The delete ranges overlap, so fuse the two entries. previous is
            # aliased from merged, so mutating it here edits the merged patch.
            if entry[0] + entry[1] > previous[0] + previous[1]:
                previous[1] = entry[0] + entry[1] - previous[0]
            previous[2] += entry[2]
        else:
            merged.append(entry)
            previous = entry
    return merged
