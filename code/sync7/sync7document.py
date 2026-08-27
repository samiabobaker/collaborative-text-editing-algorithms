from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from sync7.sync7diff import (
    Sync7Diff,
    Sync7DiffComponent,
    Sync7Equal,
    Sync7Replace,
    Sync7Text,
    apply_diff,
    compose_diffs,
    push_equal,
)


@dataclass(frozen=True, order=True)
class Sync7Id:
    client_id: int
    seq: int


# The version every document starts from, holding the empty text. No client has -1, so
# it sorts before everything and never collides with a version a client made.
ROOT = Sync7Id(-1, 0)


@dataclass
class Sync7Version:
    to_parents: dict[Sync7Id, Sync7Diff]
    from_kids: dict[Sync7Id, Sync7Diff]


@dataclass
class Sync7Region:
    """A stretch of one version's text that the merge treats as a single thing.

    position and length are in the text of whichever version the region belongs to. The
    rest is filled in against the other side of the merge: whether the region reached the
    common ancestors unchanged, the index of the same region on the other side if the
    other side has it too, and the last region on the other side that this one is known to
    come after.
    """

    position: int
    length: int
    untouched: bool = False
    same_as: int = -1
    after: int = -1


@dataclass
class Sync7Untouched:
    # A stretch of a version's text that reached some ancestor unchanged: where it is in
    # the version's text, how long it is, and where it is in the ancestor's text.
    position: int
    length: int
    projected: int


@dataclass
class Sync7Endpoint:
    # A region boundary being carried down to an ancestor. is_end says whether it closes a
    # region, which decides which way it moves when it lands inside a change.
    value: int
    is_end: bool
    projected: int


def component_length(component: Sync7DiffComponent) -> int:
    match component:
        case Sync7Equal(length):
            return length
        case Sync7Replace(deleted, _):
            return len(deleted)
        case _ as unreachable:
            assert_never(unreachable)


def parent_length(component: Sync7DiffComponent) -> int:
    match component:
        case Sync7Equal(length):
            return length
        case Sync7Replace(_, inserted):
            return len(inserted)
        case _ as unreachable:
            assert_never(unreachable)


def copy_versions(versions: dict[Sync7Id, Sync7Version]) -> dict[Sync7Id, Sync7Version]:
    # Every replica keeps its own record of which versions are children of which, so a
    # version put into a message is a copy. The diffs inside are not: they are only ever
    # read, and the characters in them have to stay the same objects.
    return {
        identifier: Sync7Version(dict(version.to_parents), dict(version.from_kids))
        for identifier, version in versions.items()
    }


def get_leaves(
    versions: dict[Sync7Id, Sync7Version], ignore: dict[Sync7Id, Sync7Version] | None = None
) -> list[Sync7Id]:
    ignored = ignore if ignore is not None else {}
    leaves = {identifier: True for identifier in versions if identifier not in ignored}
    for identifier, version in versions.items():
        if identifier in ignored:
            continue
        for parent in version.to_parents:
            leaves.pop(parent, None)
    return list(leaves)


def endpoints_for(dividers: set[int], length: int) -> list[Sync7Endpoint]:
    # Turns the positions where something changed into the boundaries of a run of regions
    # covering the whole text, an opening and a closing endpoint per region.
    endpoints = [Sync7Endpoint(0, False, 0)]
    for divider in sorted(dividers):
        endpoints.append(Sync7Endpoint(divider, True, divider))
        endpoints.append(Sync7Endpoint(divider, False, divider))
    endpoints.append(Sync7Endpoint(length, True, length))
    return endpoints


def divide_against(mine: list[Sync7Untouched], theirs: list[Sync7Untouched], dividers: set[int]) -> None:
    # Where a stretch the other side kept starts or ends inside a stretch this side kept,
    # this side has to be cut there as well, or the two cannot be laid against each other.
    index = 0
    for region in mine:
        while index < len(theirs) and theirs[index].projected + theirs[index].length <= region.projected:
            index += 1
        if index < len(theirs) and theirs[index].projected < region.projected:
            dividers.add(region.projected - theirs[index].projected + theirs[index].position)
        while (
            index < len(theirs) and theirs[index].projected + theirs[index].length <= region.projected + region.length
        ):
            index += 1
        if index < len(theirs) and theirs[index].projected < region.projected + region.length:
            dividers.add(region.projected + region.length - theirs[index].projected + theirs[index].position)


def mark_untouched(
    base: list[Sync7Region],
    projected: list[Sync7Region],
    untouched: list[Sync7Untouched],
    by_position: dict[int, int],
) -> None:
    index = 0
    for region in untouched:
        while index < len(projected) and projected[index].position + projected[index].length <= region.projected:
            index += 1
        while index < len(projected) and projected[index].position < region.projected + region.length:
            by_position[projected[index].position] = index
            base[index].untouched = True
            projected[index].untouched = True
            index += 1


def mark_shared(
    regions_for: dict[Sync7Id, list[Sync7Region]],
    node: Sync7Id,
    lowest_common: list[Sync7Id],
    other_by_position: dict[Sync7Id, dict[int, int]],
) -> None:
    # For a region this side did not change, finds the same region on the other side. One
    # that this side kept and the other side has no counterpart for is one the other side
    # changed, and the other side's answer is the one the merge takes.
    for index, region in enumerate(regions_for[node]):
        region.after = -1
        if not region.untouched:
            continue
        region.same_as = -1
        for ancestor in lowest_common:
            projected = regions_for[ancestor][index]
            other_index = other_by_position[ancestor].get(projected.position)
            if projected.untouched and other_index is not None:
                region.same_as = other_index
                break


def definitely_before(
    mine: dict[Sync7Id, list[Sync7Region]],
    my_index: int,
    theirs: dict[Sync7Id, list[Sync7Region]],
    their_index: int,
    lowest_common: list[Sync7Id],
) -> bool:
    # Two regions are in a forced order only if at least one common ancestor they both
    # reach puts them that way round and none puts them the other way. Two empty regions
    # at the same place force nothing.
    before = False
    after = False

    for ancestor in lowest_common:
        one = mine[ancestor][my_index]
        two = theirs[ancestor][their_index]

        if (one.length or two.length) and one.position + one.length <= two.position:
            before = True
        if not one.length and not two.length and one.position < two.position:
            before = True

        if (one.length or two.length) and two.position + two.length <= one.position:
            after = True
        if not one.length and not two.length and two.position < one.position:
            after = True

    return before and not after


def known_orderings(
    mine: dict[Sync7Id, list[Sync7Region]],
    my_node: Sync7Id,
    theirs: dict[Sync7Id, list[Sync7Region]],
    their_node: Sync7Id,
    lowest_common: list[Sync7Id],
) -> None:
    their_index = 0
    for my_index in range(len(mine[my_node])):
        while their_index < len(theirs[their_node]):
            if definitely_before(mine, my_index, theirs, their_index, lowest_common):
                theirs[their_node][their_index].after = my_index
                break
            their_index += 1


def weave(
    first_text: Sync7Text,
    second_text: Sync7Text,
    first_regions: list[Sync7Region],
    second_regions: list[Sync7Region],
) -> tuple[Sync7Text, Sync7Diff, Sync7Diff]:
    # Reads the two sides in step and writes the merged text, taking from whichever side is
    # free to go next. A region both sides kept is written once and both sides move on; a
    # region one side kept and the other changed is dropped, because the other side's
    # version of it is the one that is written.
    text: Sync7Text = []
    first_diff: Sync7Diff = []
    second_diff: Sync7Diff = []
    on_first = True
    first_index = 0
    second_index = 0

    while True:
        one = first_regions[first_index] if first_index < len(first_regions) else None
        two = second_regions[second_index] if second_index < len(second_regions) else None
        if one is None and two is None:
            break
        if one is None:
            on_first = False
        if two is None:
            on_first = True

        here_index = first_index if on_first else second_index
        there_index = second_index if on_first else first_index
        here = one if on_first else two
        there = two if on_first else one
        here_text = first_text if on_first else second_text
        here_diff = first_diff if on_first else second_diff
        there_diff = second_diff if on_first else first_diff

        if here is None:
            raise ValueError("Merge ran off the end of a side")

        if here.after < there_index:
            taken = here_text[here.position : here.position + here.length]
            if here.untouched and here.same_as < there_index:
                # One region per component, rather than running neighbouring ones
                # together the way the diffs made anywhere else are. Each region is a
                # unit the rest of the algorithm counts in, so joining two of them here
                # would lose a boundary.
                here_diff.append(Sync7Replace([], taken))
            elif here.untouched and here.same_as == there_index:
                text += taken
                push_equal(here_diff, here.length)
                push_equal(there_diff, here.length)
                if on_first:
                    second_index += 1
                else:
                    first_index += 1
            else:
                text += taken
                push_equal(here_diff, here.length)
                there_diff.append(Sync7Replace(taken, []))
            if on_first:
                first_index += 1
            else:
                second_index += 1
        elif there is not None and there.after < here_index:
            on_first = not on_first
        else:
            raise ValueError("Neither side of the merge can go next")

    return text, first_diff, second_diff


class Sync7Document:
    """The version graph, and the merge that turns its leaves back into one text.

    A version is a whole text, held as the diff between it and each of its parents. A
    local edit makes a child of whatever version the document is on, and taking in other
    people's versions leaves the graph with several leaves. The merge folds those into
    one, two at a time in order of version id so that every replica folds them the same
    way.

    Merging two leaves is a three way merge against their lowest common ancestors. Both
    sides are cut into regions wherever anything between them and those ancestors
    changed, the cuts are carried down so a region of one side can be compared with a
    region of the other, and a region one side left alone but the other changed is the
    other side's to decide. What is left is ordered by whatever the ancestors force.

    A merge result is a version like any other, but a temporary one: it is thrown away
    and worked out again on the next merge, and becomes permanent only if the client
    edits on top of it.
    """

    client_id: int

    versions: dict[Sync7Id, Sync7Version]
    waiting_versions: dict[Sync7Id, Sync7Version]
    temp_versions: dict[Sync7Id, Sync7Version]
    leaf: Sync7Id
    text: Sync7Text

    __next_seq: int

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.versions = {ROOT: Sync7Version({}, {})}
        self.waiting_versions = {}
        self.temp_versions = {}
        self.leaf = ROOT
        self.text = []
        self.__next_seq = 0

    def mint(self) -> Sync7Id:
        # The original names versions with random strings. Naming them after the client
        # that made them keeps a run reproducible and keeps the order the leaves are
        # merged in, which is the order of the names, the same everywhere.
        identifier = Sync7Id(self.client_id, self.__next_seq)
        self.__next_seq += 1
        return identifier

    # ---- making and taking in versions ----------------------------------

    def commit(self, identifier: Sync7Id, text: Sync7Text, to_parent: Sync7Diff) -> dict[Sync7Id, Sync7Version]:
        # Records a new version of the text and returns everything the other replicas have
        # not been told about, which is this version plus any merge results underneath it.
        # Those stop being temporary here, because something now depends on them.
        if text == self.text:
            return {}

        versions_to_send = self.temp_versions
        self.temp_versions = {}

        version = Sync7Version({self.leaf: to_parent}, {})
        self.versions[self.leaf].from_kids[identifier] = to_parent
        self.versions[identifier] = version
        versions_to_send[identifier] = version

        self.leaf = identifier
        self.text = text

        return versions_to_send

    def merge(self, incoming: dict[Sync7Id, Sync7Version]) -> None:
        for identifier, version in incoming.items():
            for parent, diff in version.to_parents.items():
                if parent in self.waiting_versions:
                    self.waiting_versions[parent].from_kids[identifier] = diff
        for identifier, version in self.waiting_versions.items():
            for parent, diff in version.to_parents.items():
                if parent in incoming:
                    incoming[parent].from_kids[identifier] = diff

        cannot_add = self.__versions_missing_a_parent(incoming)

        if len(incoming) + len(self.waiting_versions) - len(cannot_add) <= 0:
            self.waiting_versions.update(incoming)
            return

        for identifier, version in list(incoming.items()):
            self.__add_version(identifier, version, cannot_add, from_incoming=True)
        for identifier, version in list(self.waiting_versions.items()):
            self.__add_version(identifier, version, cannot_add, from_incoming=False)

        leaves = sorted(get_leaves(self.versions, self.temp_versions))
        texts = {leaf: self.get_text(leaf) for leaf in leaves}

        self.__discard_temp_versions()

        merged = leaves[0]
        ancestors = self.__ancestors([merged])
        for leaf in leaves[1:]:
            leaf_ancestors = self.__ancestors([leaf])
            common = [identifier for identifier in ancestors if identifier in leaf_ancestors]
            lowest_common = get_leaves({identifier: self.versions[identifier] for identifier in common})
            for identifier in leaf_ancestors:
                ancestors[identifier] = leaf_ancestors[identifier]

            text, to_merged, to_leaf = self.__merge_two(merged, leaf, texts, common, lowest_common)

            identifier = self.mint()
            self.versions[merged].from_kids[identifier] = to_merged
            self.versions[leaf].from_kids[identifier] = to_leaf
            version = Sync7Version({merged: to_merged, leaf: to_leaf}, {})
            self.versions[identifier] = version
            self.temp_versions[identifier] = version

            merged = identifier
            texts[merged] = text

        self.leaf = merged
        self.text = texts[merged]

    def __versions_missing_a_parent(self, incoming: dict[Sync7Id, Sync7Version]) -> set[Sync7Id]:
        # A version whose parents have not all turned up yet cannot go into the graph, and
        # neither can anything descended from it.
        cannot_add: set[Sync7Id] = set()

        def find(identifier: Sync7Id) -> Sync7Version | None:
            return self.versions.get(identifier) or incoming.get(identifier) or self.waiting_versions.get(identifier)

        def mark(identifier: Sync7Id, version: Sync7Version) -> None:
            if identifier in cannot_add:
                return
            cannot_add.add(identifier)
            for kid in version.from_kids:
                kid_version = find(kid)
                if kid_version is not None:
                    mark(kid, kid_version)

        for identifier, version in list(incoming.items()) + list(self.waiting_versions.items()):
            if any(find(parent) is None for parent in version.to_parents):
                mark(identifier, version)

        return cannot_add

    def __add_version(
        self, identifier: Sync7Id, version: Sync7Version, cannot_add: set[Sync7Id], from_incoming: bool
    ) -> None:
        if identifier in cannot_add:
            if from_incoming:
                self.waiting_versions[identifier] = version
            return

        self.versions[identifier] = version
        self.waiting_versions.pop(identifier, None)
        for parent, diff in version.to_parents.items():
            if parent in self.versions:
                self.versions[parent].from_kids[identifier] = diff

    def __discard_temp_versions(self) -> None:
        for identifier, version in self.temp_versions.items():
            for parent in version.to_parents:
                if parent not in self.temp_versions:
                    del self.versions[parent].from_kids[identifier]
            del self.versions[identifier]
        self.temp_versions = {}

    # ---- walking the graph -----------------------------------------------

    def __ancestors(self, start: list[Sync7Id], include_self: bool = False) -> dict[Sync7Id, Sync7Version]:
        ancestors: dict[Sync7Id, Sync7Version] = {}
        if include_self:
            for identifier in start:
                ancestors[identifier] = self.versions[identifier]

        frontier = list(start)
        while len(frontier) > 0:
            identifier = frontier.pop(0)
            for parent in self.versions[identifier].to_parents:
                if parent not in ancestors:
                    ancestors[parent] = self.versions[parent]
                    frontier.append(parent)
        return ancestors

    def __path_to_ancestor(self, start: Sync7Id, target: Sync7Id) -> list[Sync7Id]:
        if start == target:
            return []

        frontier = [start]
        came_from: dict[Sync7Id, Sync7Id] = {}
        while len(frontier) > 0:
            identifier = frontier.pop(0)
            if identifier == target:
                path: list[Sync7Id] = []
                while identifier != start:
                    path.insert(0, identifier)
                    identifier = came_from[identifier]
                return path
            for parent in self.versions[identifier].to_parents:
                if parent not in came_from:
                    came_from[parent] = identifier
                    frontier.append(parent)

        raise ValueError(f"No path from {start} to {target}")

    def get_text(self, identifier: Sync7Id) -> Sync7Text:
        # The text of a version other than the one the document is on, reached by composing
        # the diffs from here up to a common ancestor and back down to it.
        here = self.__ancestors([self.leaf], include_self=True)
        there = self.__ancestors([identifier], include_self=True)
        common = {version: here[version] for version in here if version in there}
        ancestor = get_leaves(common)[0]

        upwards = self.__path_to_ancestor(self.leaf, ancestor)
        downwards = self.__path_to_ancestor(identifier, ancestor)
        downwards.reverse()
        if len(downwards) > 0:
            downwards.pop(0)
            downwards.append(identifier)

        diff: Sync7Diff = []
        previous = self.leaf
        for step in upwards:
            diff = compose_diffs(diff, self.versions[previous].to_parents[step])
            previous = step

        previous = ancestor
        for step in downwards:
            diff = compose_diffs(diff, self.versions[step].to_parents[previous], False, True)
            previous = step

        return apply_diff(self.text, diff)

    # ---- merging two leaves ----------------------------------------------

    def __merge_two(
        self,
        first: Sync7Id,
        second: Sync7Id,
        texts: dict[Sync7Id, Sync7Text],
        common: list[Sync7Id],
        lowest_common: list[Sync7Id],
    ) -> tuple[Sync7Text, Sync7Diff, Sync7Diff]:
        first_path = self.__nodes_on_path(first, common, lowest_common)
        first_dividers: set[int] = set()
        first_untouched: dict[Sync7Id, list[Sync7Untouched]] = {}
        self.__find_untouched(first, texts, first_path, lowest_common, first_dividers, first_untouched)

        second_path = self.__nodes_on_path(second, common, lowest_common)
        second_dividers: set[int] = set()
        second_untouched: dict[Sync7Id, list[Sync7Untouched]] = {}
        self.__find_untouched(second, texts, second_path, lowest_common, second_dividers, second_untouched)

        for ancestor in lowest_common:
            divide_against(first_untouched[ancestor], second_untouched[ancestor], second_dividers)
            divide_against(second_untouched[ancestor], first_untouched[ancestor], first_dividers)

        first_regions = self.__project_regions(
            endpoints_for(first_dividers, len(texts[first])), first, first_path, lowest_common
        )
        second_regions = self.__project_regions(
            endpoints_for(second_dividers, len(texts[second])), second, second_path, lowest_common
        )

        first_by_position: dict[Sync7Id, dict[int, int]] = {}
        second_by_position: dict[Sync7Id, dict[int, int]] = {}
        for ancestor in lowest_common:
            first_by_position[ancestor] = {}
            second_by_position[ancestor] = {}
            mark_untouched(
                first_regions[first], first_regions[ancestor], first_untouched[ancestor], first_by_position[ancestor]
            )
            mark_untouched(
                second_regions[second],
                second_regions[ancestor],
                second_untouched[ancestor],
                second_by_position[ancestor],
            )

        mark_shared(first_regions, first, lowest_common, second_by_position)
        mark_shared(second_regions, second, lowest_common, first_by_position)

        known_orderings(first_regions, first, second_regions, second, lowest_common)
        known_orderings(second_regions, second, first_regions, first, lowest_common)

        return weave(texts[first], texts[second], first_regions[first], second_regions[second])

    def __nodes_on_path(self, start: Sync7Id, common: list[Sync7Id], lowest_common: list[Sync7Id]) -> set[Sync7Id]:
        # Everything between the leaf and the lowest common ancestors, which is the part of
        # the graph the leaf's text has to be carried down through. The answer for a
        # version does not depend on how it was reached, so it is worked out once.
        on_path: set[Sync7Id] = set()
        reaches: dict[Sync7Id, bool] = {}

        def helper(identifier: Sync7Id) -> bool:
            if identifier in reaches:
                return reaches[identifier]
            reached = identifier in lowest_common
            if identifier not in common:
                for parent in self.versions[identifier].to_parents:
                    reached = helper(parent) or reached
            if reached:
                on_path.add(identifier)
            reaches[identifier] = reached
            return reached

        helper(start)
        return on_path

    def __find_untouched(
        self,
        start: Sync7Id,
        texts: dict[Sync7Id, Sync7Text],
        on_path: set[Sync7Id],
        lowest_common: list[Sync7Id],
        dividers: set[int],
        untouched_for: dict[Sync7Id, list[Sync7Untouched]],
    ) -> None:
        # Carries the leaf's text down to each lowest common ancestor, keeping the stretches
        # that nothing on the way changed and recording every position in the leaf's text
        # where something did.
        untouched_for[start] = [Sync7Untouched(0, len(texts[start]), 0)]

        def helper(identifier: Sync7Id) -> list[Sync7Untouched]:
            if identifier in untouched_for:
                return untouched_for[identifier]

            carried: dict[int, Sync7Untouched] = {}
            for kid, diff in self.versions[identifier].from_kids.items():
                if kid not in on_path:
                    continue
                untouched = helper(kid)

                index = 0
                used = 0
                offset = 0
                parent_offset = 0
                for component in diff:
                    end = offset + component_length(component)

                    while index < len(untouched) and end >= untouched[index].projected + untouched[index].length:
                        if isinstance(component, Sync7Equal):
                            at = untouched[index].projected + used - offset + parent_offset
                            carried[at] = Sync7Untouched(
                                untouched[index].position + used, untouched[index].length - used, at
                            )
                        index += 1
                        used = 0

                    if index >= len(untouched):
                        break

                    if end > untouched[index].projected + used:
                        if isinstance(component, Sync7Equal):
                            at = untouched[index].projected + used - offset + parent_offset
                            carried[at] = Sync7Untouched(
                                untouched[index].position + used, end - (untouched[index].projected + used), at
                            )
                        used = end - untouched[index].projected
                        dividers.add(untouched[index].position + used)

                    offset = end
                    parent_offset += parent_length(component)

            untouched_for[identifier] = sorted(carried.values(), key=lambda region: region.projected)
            return untouched_for[identifier]

        for ancestor in lowest_common:
            helper(ancestor)

    def __project_regions(
        self,
        endpoints: list[Sync7Endpoint],
        start: Sync7Id,
        on_path: set[Sync7Id],
        lowest_common: list[Sync7Id],
    ) -> dict[Sync7Id, list[Sync7Region]]:
        # Carries the region boundaries down to each lowest common ancestor, so a region of
        # one leaf and a region of the other can be compared by where they land in an
        # ancestor they both reach.
        endpoints_by_version: dict[Sync7Id, list[Sync7Endpoint]] = {start: endpoints}

        def helper(identifier: Sync7Id) -> list[Sync7Endpoint]:
            if identifier in endpoints_by_version:
                return endpoints_by_version[identifier]

            carried: dict[tuple[int, bool], int] = {}

            def record(endpoint: Sync7Endpoint, position: int) -> None:
                # A boundary reached by more than one route opens as early as it can and
                # closes as late as it can. The original tests for a boundary it has not
                # placed yet in a way that also catches one it placed at zero, which then
                # gets replaced rather than compared, and that is kept here.
                key = (endpoint.value, endpoint.is_end)
                if not carried.get(key):
                    carried[key] = position
                elif endpoint.is_end:
                    carried[key] = max(carried[key], position)
                else:
                    carried[key] = min(carried[key], position)

            for kid, diff in self.versions[identifier].from_kids.items():
                if kid not in on_path:
                    continue
                kid_endpoints = helper(kid)

                index = 0
                offset = 0
                parent_offset = 0
                for component in diff:
                    end = offset + component_length(component)

                    while index < len(kid_endpoints) and (
                        kid_endpoints[index].projected < end
                        or (kid_endpoints[index].is_end and kid_endpoints[index].projected <= end)
                    ):
                        match component:
                            case Sync7Equal(_):
                                record(kid_endpoints[index], kid_endpoints[index].projected - offset + parent_offset)
                            case Sync7Replace(_, inserted):
                                if kid_endpoints[index].is_end:
                                    record(kid_endpoints[index], parent_offset + len(inserted))
                                else:
                                    record(kid_endpoints[index], parent_offset)
                            case _ as unreachable:
                                assert_never(unreachable)
                        index += 1

                    offset = end
                    parent_offset += parent_length(component)

                while index < len(kid_endpoints):
                    record(kid_endpoints[index], parent_offset)
                    index += 1

            projected = [Sync7Endpoint(value, is_end, position) for (value, is_end), position in carried.items()]
            projected.sort(key=lambda endpoint: (endpoint.projected, not endpoint.is_end))
            endpoints_by_version[identifier] = projected
            return projected

        regions_for: dict[Sync7Id, list[Sync7Region]] = {}

        by_begin: dict[int, int] = {}
        by_end: dict[int, int] = {}
        base: list[Sync7Region] = []
        regions_for[start] = base
        for index in range(0, len(endpoints), 2):
            begin = endpoints[index].value
            end = endpoints[index + 1].value
            base.append(Sync7Region(begin, end - begin))
            by_begin[begin] = len(base) - 1
            by_end[end] = len(base) - 1

        for ancestor in lowest_common:
            bounds: list[list[int | None]] = [[None, None] for _ in base]
            for endpoint in helper(ancestor):
                index = by_end[endpoint.value] if endpoint.is_end else by_begin[endpoint.value]
                bounds[index][1 if endpoint.is_end else 0] = endpoint.projected

            regions: list[Sync7Region] = []
            for begin, end in bounds:
                if begin is None or end is None:
                    raise ValueError("Region boundary did not reach a common ancestor")
                regions.append(Sync7Region(begin, end - begin))
            regions_for[ancestor] = regions

        return regions_for
