import math
from typing import Any

DIFF_DELETE = -1
DIFF_INSERT = 1
DIFF_EQUAL = 0

# A diff entry is [type, text] where type is one of the three constants above.
# The entries are mutated in place while the diff is cleaned up, so they are
# lists rather than tuples.
Diff = list[list[Any]]


def diff_texts(text1: str, text2: str) -> Diff:
    """Find the differences between two texts.

    This is the Myers algorithm as described in the paper, with the common
    prefix and suffix trimmed off first so that only the middle block is
    searched. The reference implementation also takes a cursor position and a
    deadline; diffsync passes neither, so they are omitted.
    """
    if text1 == text2:
        if text1:
            return [[DIFF_EQUAL, text1]]
        return []

    common_length = __common_prefix(text1, text2)
    common_prefix = text1[:common_length]
    text1 = text1[common_length:]
    text2 = text2[common_length:]

    common_length = __common_suffix(text1, text2)
    common_suffix = text1[len(text1) - common_length :]
    text1 = text1[: len(text1) - common_length]
    text2 = text2[: len(text2) - common_length]

    diffs = __compute(text1, text2)

    if common_prefix:
        diffs.insert(0, [DIFF_EQUAL, common_prefix])
    if common_suffix:
        diffs.append([DIFF_EQUAL, common_suffix])
    __cleanup_merge(diffs)
    return diffs


def __compute(text1: str, text2: str) -> Diff:
    """Diff two texts that share no common prefix or suffix.

    Everything before the bisection is a shortcut for a case whose answer is
    already known: one side empty, one side contained in the other, or a
    single character left over.
    """
    if not text1:
        return [[DIFF_INSERT, text2]]
    if not text2:
        return [[DIFF_DELETE, text1]]

    longtext = text1 if len(text1) > len(text2) else text2
    shorttext = text2 if len(text1) > len(text2) else text1
    i = longtext.find(shorttext)
    if i != -1:
        diffs = [
            [DIFF_INSERT, longtext[:i]],
            [DIFF_EQUAL, shorttext],
            [DIFF_INSERT, longtext[i + len(shorttext) :]],
        ]
        if len(text1) > len(text2):
            diffs[0][0] = DIFF_DELETE
            diffs[2][0] = DIFF_DELETE
        return diffs

    if len(shorttext) == 1:
        # After the containment shortcut above, a single character cannot be
        # an equality.
        return [[DIFF_DELETE, text1], [DIFF_INSERT, text2]]

    half_match = __half_match(text1, text2)
    if half_match:
        text1_a, text1_b, text2_a, text2_b, mid_common = half_match
        diffs_a = diff_texts(text1_a, text2_a)
        diffs_b = diff_texts(text1_b, text2_b)
        return diffs_a + [[DIFF_EQUAL, mid_common]] + diffs_b

    return __bisect(text1, text2)


def __bisect(text1: str, text2: str) -> Diff:
    """Find the middle snake of a diff, split the problem in two and recurse.

    This is Section 4b of the Myers paper: two paths are walked, one from each
    end, until they overlap.
    """
    text1_length = len(text1)
    text2_length = len(text2)
    max_d = math.ceil((text1_length + text2_length) / 2)
    v_offset = max_d
    v_length = 2 * max_d
    v1 = [-1] * v_length
    v2 = [-1] * v_length
    v1[v_offset + 1] = 0
    v2[v_offset + 1] = 0
    delta = text1_length - text2_length
    # If the total number of characters is odd the front path collides with
    # the reverse path.
    front = delta % 2 != 0
    # Offsets for the start and end of the k loop, which stop the search
    # running off the edge of the grid.
    k1start = 0
    k1end = 0
    k2start = 0
    k2end = 0
    for d in range(max_d):
        # Walk the front path one step.
        for k1 in range(-d + k1start, d - k1end + 1, 2):
            k1_offset = v_offset + k1
            if k1 == -d or (k1 != d and v1[k1_offset - 1] < v1[k1_offset + 1]):
                x1 = v1[k1_offset + 1]
            else:
                x1 = v1[k1_offset - 1] + 1
            y1 = x1 - k1
            while x1 < text1_length and y1 < text2_length and text1[x1] == text2[y1]:
                x1 += 1
                y1 += 1
            v1[k1_offset] = x1
            if x1 > text1_length:
                # Ran off the right of the grid.
                k1end += 2
            elif y1 > text2_length:
                # Ran off the bottom of the grid.
                k1start += 2
            elif front:
                k2_offset = v_offset + delta - k1
                if 0 <= k2_offset < v_length and v2[k2_offset] != -1:
                    # Mirror x2 onto the top-left coordinate system.
                    x2 = text1_length - v2[k2_offset]
                    if x1 >= x2:
                        return __bisect_split(text1, text2, x1, y1)

        # Walk the reverse path one step.
        for k2 in range(-d + k2start, d - k2end + 1, 2):
            k2_offset = v_offset + k2
            if k2 == -d or (k2 != d and v2[k2_offset - 1] < v2[k2_offset + 1]):
                x2 = v2[k2_offset + 1]
            else:
                x2 = v2[k2_offset - 1] + 1
            y2 = x2 - k2
            while (
                x2 < text1_length and y2 < text2_length and text1[text1_length - x2 - 1] == text2[text2_length - y2 - 1]
            ):
                x2 += 1
                y2 += 1
            v2[k2_offset] = x2
            if x2 > text1_length:
                # Ran off the left of the grid.
                k2end += 2
            elif y2 > text2_length:
                # Ran off the top of the grid.
                k2start += 2
            elif not front:
                k1_offset = v_offset + delta - k2
                if 0 <= k1_offset < v_length and v1[k1_offset] != -1:
                    x1 = v1[k1_offset]
                    y1 = v_offset + x1 - k1_offset
                    # Mirror x2 onto the top-left coordinate system.
                    x2 = text1_length - x2
                    if x1 >= x2:
                        return __bisect_split(text1, text2, x1, y1)
    # The number of diffs equals the number of characters, so there is no
    # commonality at all.
    return [[DIFF_DELETE, text1], [DIFF_INSERT, text2]]


def __bisect_split(text1: str, text2: str, x: int, y: int) -> Diff:
    """Given the location of the middle snake, split the diff in two.

    Each half is then diffed recursively.
    """
    text1a = text1[:x]
    text2a = text2[:y]
    text1b = text1[x:]
    text2b = text2[y:]

    return diff_texts(text1a, text2a) + diff_texts(text1b, text2b)


def __common_prefix(text1: str, text2: str) -> int:
    """The length of the common prefix of two strings, by binary search."""
    if not text1 or not text2 or text1[0] != text2[0]:
        return 0
    pointer_min = 0
    pointer_max = min(len(text1), len(text2))
    pointer_mid = pointer_max
    pointer_start = 0
    while pointer_min < pointer_mid:
        if text1[pointer_start:pointer_mid] == text2[pointer_start:pointer_mid]:
            pointer_min = pointer_mid
            pointer_start = pointer_min
        else:
            pointer_max = pointer_mid
        pointer_mid = math.floor((pointer_max - pointer_min) / 2 + pointer_min)
    return pointer_mid


def __common_suffix(text1: str, text2: str) -> int:
    """The length of the common suffix of two strings, by binary search."""
    if not text1 or not text2 or text1[len(text1) - 1] != text2[len(text2) - 1]:
        return 0
    pointer_min = 0
    pointer_max = min(len(text1), len(text2))
    pointer_mid = pointer_max
    pointer_end = 0
    while pointer_min < pointer_mid:
        if (
            text1[len(text1) - pointer_mid : len(text1) - pointer_end]
            == text2[len(text2) - pointer_mid : len(text2) - pointer_end]
        ):
            pointer_min = pointer_mid
            pointer_end = pointer_min
        else:
            pointer_max = pointer_mid
        pointer_mid = math.floor((pointer_max - pointer_min) / 2 + pointer_min)
    return pointer_mid


def __half_match_at(longtext: str, shorttext: str, i: int) -> list[str] | None:
    """Look for a half match seeded by a quarter-length substring of longtext.

    The substring starts at i. Returns the two halves of each text either side of
    the match and the matched text itself, or None.
    """
    seed = longtext[i : i + math.floor(len(longtext) / 4)]
    j = -1
    best_common = ""
    best_longtext_a = best_longtext_b = ""
    best_shorttext_a = best_shorttext_b = ""
    while True:
        j = shorttext.find(seed, j + 1)
        if j == -1:
            break
        prefix_length = __common_prefix(longtext[i:], shorttext[j:])
        suffix_length = __common_suffix(longtext[:i], shorttext[:j])
        if len(best_common) < suffix_length + prefix_length:
            best_common = shorttext[j - suffix_length : j] + shorttext[j : j + prefix_length]
            best_longtext_a = longtext[: i - suffix_length]
            best_longtext_b = longtext[i + prefix_length :]
            best_shorttext_a = shorttext[: j - suffix_length]
            best_shorttext_b = shorttext[j + prefix_length :]
    if best_common and len(best_common) * 2 >= len(longtext):
        return [best_longtext_a, best_longtext_b, best_shorttext_a, best_shorttext_b, best_common]
    return None


def __half_match(text1: str, text2: str) -> list[str] | None:
    """Do the two texts share a substring at least half the length of the longer one?

    Splitting there is a shortcut that can produce a non-minimal diff, which is
    why it is only taken when the shared run is that long.
    """
    longtext = text1 if len(text1) > len(text2) else text2
    shorttext = text2 if len(text1) > len(text2) else text1
    if len(longtext) < 4 or len(shorttext) * 2 < len(longtext):
        return None

    # Seed from the second quarter, then again from the third.
    half_match1 = __half_match_at(longtext, shorttext, math.ceil(len(longtext) / 4))
    half_match2 = __half_match_at(longtext, shorttext, math.ceil(len(longtext) / 2))
    if not half_match1 and not half_match2:
        return None
    elif not half_match2:
        half_match = half_match1
    elif not half_match1:
        half_match = half_match2
    else:
        # Both matched, so take the longer.
        half_match = half_match1 if len(half_match1[4]) > len(half_match2[4]) else half_match2
    assert half_match is not None

    if len(text1) > len(text2):
        text1_a, text1_b, text2_a, text2_b = (
            half_match[0],
            half_match[1],
            half_match[2],
            half_match[3],
        )
    else:
        text2_a, text2_b, text1_a, text1_b = (
            half_match[0],
            half_match[1],
            half_match[2],
            half_match[3],
        )
    return [text1_a, text1_b, text2_a, text2_b, half_match[4]]


def __cleanup_merge(diffs: Diff) -> None:
    """Reorder and merge like edit sections, and merge equalities.

    An edit section can move as long as it does not cross an equality.
    """
    diffs.append([DIFF_EQUAL, ""])  # A dummy entry, removed at the end.
    pointer = 0
    count_delete = 0
    count_insert = 0
    text_delete = ""
    text_insert = ""
    while pointer < len(diffs):
        if diffs[pointer][0] == DIFF_INSERT:
            count_insert += 1
            text_insert += diffs[pointer][1]
            pointer += 1
        elif diffs[pointer][0] == DIFF_DELETE:
            count_delete += 1
            text_delete += diffs[pointer][1]
            pointer += 1
        elif diffs[pointer][0] == DIFF_EQUAL:
            # An equality ends a run of edits, so check that run for anything
            # redundant before moving past it.
            if count_delete + count_insert > 1:
                if count_delete != 0 and count_insert != 0:
                    # Factor out any common prefix.
                    common_length = __common_prefix(text_insert, text_delete)
                    if common_length != 0:
                        start = pointer - count_delete - count_insert
                        if start > 0 and diffs[start - 1][0] == DIFF_EQUAL:
                            diffs[start - 1][1] += text_insert[:common_length]
                        else:
                            diffs.insert(0, [DIFF_EQUAL, text_insert[:common_length]])
                            pointer += 1
                        text_insert = text_insert[common_length:]
                        text_delete = text_delete[common_length:]
                    # Factor out any common suffix.
                    common_length = __common_suffix(text_insert, text_delete)
                    if common_length != 0:
                        diffs[pointer][1] = text_insert[len(text_insert) - common_length :] + diffs[pointer][1]
                        text_insert = text_insert[: len(text_insert) - common_length]
                        text_delete = text_delete[: len(text_delete) - common_length]
                # Replace the run of edits with the merged ones.
                if count_delete == 0:
                    diffs[pointer - count_insert : pointer] = [[DIFF_INSERT, text_insert]]
                elif count_insert == 0:
                    diffs[pointer - count_delete : pointer] = [[DIFF_DELETE, text_delete]]
                else:
                    diffs[pointer - count_delete - count_insert : pointer] = [
                        [DIFF_DELETE, text_delete],
                        [DIFF_INSERT, text_insert],
                    ]
                pointer = (
                    pointer - count_delete - count_insert + (1 if count_delete else 0) + (1 if count_insert else 0) + 1
                )
            elif pointer != 0 and diffs[pointer - 1][0] == DIFF_EQUAL:
                # Merge this equality with the previous one.
                diffs[pointer - 1][1] += diffs[pointer][1]
                del diffs[pointer]
            else:
                pointer += 1
            count_insert = 0
            count_delete = 0
            text_delete = ""
            text_insert = ""
    if diffs[len(diffs) - 1][1] == "":
        diffs.pop()

    # Second pass: a single edit surrounded on both sides by equalities can be
    # shifted sideways to swallow one of them, as in A<ins>BA</ins>C becoming
    # <ins>AB</ins>AC.
    changes = False
    pointer = 1
    # The first and last entries never need checking.
    while pointer < len(diffs) - 1:
        if diffs[pointer - 1][0] == DIFF_EQUAL and diffs[pointer + 1][0] == DIFF_EQUAL:
            previous = diffs[pointer - 1][1]
            following = diffs[pointer + 1][1]
            if diffs[pointer][1][len(diffs[pointer][1]) - len(previous) :] == previous:
                # Shift the edit over the previous equality.
                diffs[pointer][1] = previous + diffs[pointer][1][: len(diffs[pointer][1]) - len(previous)]
                diffs[pointer + 1][1] = previous + following
                del diffs[pointer - 1]
                changes = True
            elif diffs[pointer][1][: len(following)] == following:
                # Shift the edit over the following equality.
                diffs[pointer - 1][1] += following
                diffs[pointer][1] = diffs[pointer][1][len(following) :] + following
                del diffs[pointer + 1]
                changes = True
        pointer += 1
    # A shift can expose more merging, so sweep again.
    if changes:
        __cleanup_merge(diffs)
