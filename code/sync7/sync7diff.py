from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from unique_char.uniquechar import UniqueChar

Sync7Text = list[UniqueChar]


@dataclass
class Sync7Equal:
    length: int


@dataclass
class Sync7Replace:
    deleted: Sync7Text  # What the version this diff belongs to has here.
    inserted: Sync7Text  # What its parent has instead.


# A diff runs from a version to one of its parents: the equal runs are the text the two
# have in common, and a replace holds the version's text on one side and the parent's on
# the other. Everything the algorithm does with the version graph is done with these.
Sync7DiffComponent = Sync7Equal | Sync7Replace
Sync7Diff = list[Sync7DiffComponent]


def push_equal(diff: Sync7Diff, length: int) -> None:
    if len(diff) > 0 and isinstance(diff[-1], Sync7Equal):
        diff[-1] = Sync7Equal(diff[-1].length + length)
        return
    diff.append(Sync7Equal(length))


def push_replace(diff: Sync7Diff, deleted: Sync7Text, inserted: Sync7Text) -> None:
    if len(deleted) == 0 and len(inserted) == 0:
        return
    if len(diff) > 0:
        last = diff[-1]
        if isinstance(last, Sync7Replace):
            diff[-1] = Sync7Replace(last.deleted + deleted, last.inserted + inserted)
            return
    diff.append(Sync7Replace(deleted, inserted))


def apply_diff(text: Sync7Text, diff: Sync7Diff) -> Sync7Text:
    offset = 0
    result: Sync7Text = []

    for component in diff:
        match component:
            case Sync7Equal(length):
                result += text[offset : offset + length]
                offset += length
            case Sync7Replace(deleted, inserted):
                result += inserted
                offset += len(deleted)
            case _ as unreachable:
                assert_never(unreachable)

    return result + text[offset:]


def sides(component: Sync7Replace, inverted: bool) -> tuple[Sync7Text, Sync7Text]:
    if inverted:
        return component.inserted, component.deleted
    return component.deleted, component.inserted


def compose_diffs(
    first: Sync7Diff, second: Sync7Diff, invert_first: bool = False, invert_second: bool = False
) -> Sync7Diff:
    # Walks two diffs that meet in the middle and produces the one that goes all the way,
    # so a chain of versions can be turned into a single diff between its two ends. A diff
    # is read backwards by inverting it, which is what walking down the graph needs.
    result: Sync7Diff = []
    first_index = 0
    second_index = 0
    first_offset = 0
    second_offset = 0
    first_dumped = False
    second_dumped = False

    while first_index < len(first) and second_index < len(second):
        one = first[first_index]
        two = second[second_index]
        first_left = 0
        second_left = 0

        match one, two:
            case Sync7Equal(one_length), Sync7Equal(two_length):
                first_left = one_length - first_offset
                second_left = two_length - second_offset
                push_equal(result, min(first_left, second_left))
            case Sync7Equal(one_length), Sync7Replace():
                two_source, two_target = sides(two, invert_second)
                first_left = one_length - first_offset
                second_left = len(two_source) - second_offset
                taken = two_source[second_offset : second_offset + min(first_left, second_left)]
                push_replace(result, taken, [] if second_dumped else two_target)
                second_dumped = True
            case Sync7Replace(), Sync7Equal(two_length):
                one_source, one_target = sides(one, invert_first)
                first_left = len(one_target) - first_offset
                second_left = two_length - second_offset
                taken = one_target[first_offset : first_offset + min(first_left, second_left)]
                push_replace(result, [] if first_dumped else one_source, taken)
                first_dumped = True
            case Sync7Replace(), Sync7Replace():
                one_source, one_target = sides(one, invert_first)
                two_source, two_target = sides(two, invert_second)
                first_left = len(one_target) - first_offset
                second_left = len(two_source) - second_offset
                push_replace(result, [] if first_dumped else one_source, [] if second_dumped else two_target)
                first_dumped = True
                second_dumped = True
            case _ as unreachable:
                assert_never(unreachable)

        if first_left > second_left:
            first_offset += second_left
        else:
            first_index += 1
            first_offset = 0
            first_dumped = False

        if first_left < second_left:
            second_offset += first_left
        else:
            second_index += 1
            second_offset = 0
            second_dumped = False

    while first_index < len(first):
        one = first[first_index]
        match one:
            case Sync7Equal(length):
                push_equal(result, length)
            case Sync7Replace():
                one_source, one_target = sides(one, invert_first)
                push_replace(result, [] if first_dumped else one_source, one_target[first_offset:])
            case _ as unreachable:
                assert_never(unreachable)
        first_index += 1
        first_offset = 0
        first_dumped = False

    while second_index < len(second):
        two = second[second_index]
        match two:
            case Sync7Equal(length):
                push_equal(result, length)
            case Sync7Replace():
                two_source, two_target = sides(two, invert_second)
                push_replace(result, two_source[second_offset:], [] if second_dumped else two_target)
            case _ as unreachable:
                assert_never(unreachable)
        second_index += 1
        second_offset = 0
        second_dumped = False

    return result


def diff_to_previous_text(text: Sync7Text, position: int, own: Sync7Text, parent: Sync7Text) -> Sync7Diff:
    # The diff from the text a local edit produced back to the text before it, where own is
    # what the edit put there and parent is what was there instead. The original diffs the
    # two texts against each other; here the edit is one character at a known position and
    # every character carries a unique id, so there is only one way to line the two texts
    # up and the diff can be written down directly.
    diff: Sync7Diff = []
    if position > 0:
        push_equal(diff, position)
    push_replace(diff, own, parent)
    rest = len(text) - position - len(own)
    if rest > 0:
        push_equal(diff, rest)
    return diff
