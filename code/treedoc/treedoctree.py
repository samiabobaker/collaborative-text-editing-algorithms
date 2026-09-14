from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from unique_char.uniquechar import UniqueChar

# Treedoc identifies atoms by their path in an extended binary tree (section 3.1). The
# nodes of the binary tree are called major nodes; each of them holds any number of
# mini-nodes, and it is the mini-nodes that hold the atoms. Concurrent inserts at the
# same place become mini-nodes of the same major node.
#
# The order of atoms is the infix walk of that tree: the left child of a major node
# comes before its mini-nodes, mini-nodes are ordered by disambiguator, and they come
# before the right child. A mini-node has children of its own, which sit immediately to
# its left and to its right, i.e. inside the slot of that one mini-node.
#
# Deviation from the paper: the root major node holds no atom. Figure 2 draws an atom
# there, but its PosID would be the empty path, which cannot carry the disambiguator
# that rule (i) of section 3.1 demands, so the root is kept as a pure branch point.


# Disambiguators (section 3.3). This is the SDIS variant: a disambiguator is just the
# identifier of the site that created the mini-node, with no counter. SDIS alone does
# not keep PosIDs unique, so, as the paper requires, a delete never discards a node, it
# only turns it into a tombstone. A site therefore never re-generates a PosID it has
# used before, because the node holding it is still in the way.
@dataclass(frozen=True)
class Disambiguator:
    site_id: int

    def less_than(self, other: Disambiguator) -> bool:
        return self.site_id < other.site_id

    def __str__(self) -> str:
        return f"d{self.site_id}"


# One element of a path: the branch taken out of the current node (0 = left, 1 = right)
# and a disambiguator, which is present only when needed (section 3.1): at the last
# element of the path, and whenever the path carries on through a mini-node rather than
# through the major node containing it.
@dataclass(frozen=True)
class TreedocPosIDEntry:
    direction: Literal[0, 1]
    disambiguator: Disambiguator | None

    def __str__(self) -> str:
        if self.disambiguator is None:
            return f"{self.direction}"
        return f"({self.direction}:{self.disambiguator})"


@dataclass(frozen=True)
class TreedocPosID:
    entries: tuple[TreedocPosIDEntry, ...]

    def __str__(self) -> str:
        return "[" + "".join(str(entry) for entry in self.entries) + "]"

    # PosID ⊙ (direction : disambiguator): a child of the mini-node this PosID names.
    def mini_node_child(self, direction: Literal[0, 1], disambiguator: Disambiguator) -> TreedocPosID:
        return TreedocPosID(self.entries + (TreedocPosIDEntry(direction, disambiguator),))

    # c1 ⊙ ... ⊙ pn ⊙ (direction : disambiguator) for this PosID c1 ⊙ ... ⊙ (pn : un): a
    # child of the major node that *contains* the mini-node this PosID names. Dropping
    # the last disambiguator is what lines 4, 5 and 7 of Algorithm 1 do.
    def major_node_child(self, direction: Literal[0, 1], disambiguator: Disambiguator) -> TreedocPosID:
        last_entry = self.entries[-1]
        return TreedocPosID(
            self.entries[:-1]
            + (TreedocPosIDEntry(last_entry.direction, None),)
            + (TreedocPosIDEntry(direction, disambiguator),)
        )

    # The steps of the infix walk that lead to this PosID's atom, as a list that can be
    # compared lexicographically. Each element contributes the branch it takes, plus the
    # mini-node it stops on when it carries a disambiguator; the atom itself sits between
    # the left and right children of its mini-node, which is what the final step marks.
    #
    # This replaces the element-by-element order of section 3.1, which is ambiguous when
    # a bare element p meets an element (p : d): the bare element stands for the whole
    # subtree of a major node, and that major node's mini-nodes sit in the middle of the
    # subtree, so the comparison is not settled until the following element. Where the
    # paper's rules do settle it, the two agree.
    def infix_key(self) -> list[tuple[int, int]]:
        key: list[tuple[int, int]] = []
        for entry in self.entries:
            # A branch out of a major node steps over that node's mini-nodes: taking the
            # left branch lands before all of them, the right branch after all of them.
            key.append((2 * entry.direction, 0))
            if entry.disambiguator is not None:
                key.append((1, entry.disambiguator.site_id))
        key.append(ATOM_STEP)
        return key

    def less_than(self, other: TreedocPosID) -> bool:
        return self.infix_key() < other.infix_key()


# The step onto the atom of a mini-node. Like a mini-node it sits between the left and
# the right branch, and it is only ever compared against those two: two PosIDs that
# reach this step have already agreed on the mini-node they are standing on.
ATOM_STEP = (1, -1)


class TreedocTree:
    site_id: int
    root: TreedocMajorNode

    def __init__(self, site_id: int):
        self.site_id = site_id
        self.root = TreedocMajorNode(None)

    def traverse(self) -> list[UniqueChar]:
        return self.root.traverse()

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return self.root.traverse_with_tombstones()

    def insert_char(self, position: int, char: UniqueChar) -> TreedocMiniNode:
        if position < 0 or position > self.root.count:
            raise IndexError()

        return self.insert_char_at_pos_id(self.__new_pos_id(position), char)

    def delete_char(self, position: int) -> TreedocMiniNode:
        node = self.root.get_node_at_index(position)
        node.mark_deleted()
        return node

    # Algorithm 1 of section 3.2, read off the tree rather than off the two PosIDs.
    #
    # The atom goes between the atom at `position` - 1 and whatever node follows that one
    # in the walk of the whole tree, tombstones included. Those two nodes are adjacent in
    # that walk, so every slot used below is empty: any node in it would have to lie
    # between them.
    def __new_pos_id(self, position: int) -> TreedocPosID:
        disambiguator = Disambiguator(self.site_id)

        if position == 0:
            # Algorithm 1 assumes an atom on either side. Inserting at the front of the
            # document has none on the left, so the new atom goes to the left of the
            # first node of the tree, which is what line 4 would do.
            if self.root.count + self.root.tombstone_count == 0:
                return TreedocPosID((TreedocPosIDEntry(0, disambiguator),))

            following = self.root.leftmost_node()
            return following.pos_id.major_node_child(0, disambiguator)

        preceding = self.root.get_node_at_index(position - 1)

        # The following node hangs below the preceding one, so there is no room after the
        # preceding node; the new node goes to the left of the following one instead,
        # under the major node holding it (line 4).
        if preceding.right_child is not None:
            following = preceding.right_child.leftmost_node()
            return following.pos_id.major_node_child(0, disambiguator)

        # A mini-sibling to the right is in the way, so the only room left between the two
        # is below the preceding mini-node itself (line 6).
        if preceding is not preceding.parent.mini_nodes[-1]:
            return preceding.pos_id.mini_node_child(1, disambiguator)

        # As above, but the following node hangs below the preceding node's major node.
        if preceding.parent.right_child is not None:
            following = preceding.parent.right_child.leftmost_node()
            return following.pos_id.major_node_child(0, disambiguator)

        # The preceding node ends the subtree of its major node, so the new node becomes
        # the right child of that major node (lines 5 and 7).
        return preceding.pos_id.major_node_child(1, disambiguator)

    # Walks the path, creating the major nodes it passes through that do not exist yet -
    # a concurrent insert reaches this replica before any of its own descendants, but the
    # major node it names is only created by the insert itself.
    def insert_char_at_pos_id(self, pos_id: TreedocPosID, char: UniqueChar) -> TreedocMiniNode:
        node: TreedocMajorNode | TreedocMiniNode = self.root

        for entry in pos_id.entries[:-1]:
            major_node = node.get_or_create_child(entry.direction)
            if entry.disambiguator is None:
                node = major_node
            else:
                # The path carries on through a mini-node, so that mini-node holds an atom
                # that was inserted before this one and has already been delivered.
                mini_node = major_node.get_mini_node(entry.disambiguator)
                assert mini_node is not None
                node = mini_node

        last_entry = pos_id.entries[-1]
        assert last_entry.disambiguator is not None

        major_node = node.get_or_create_child(last_entry.direction)
        return major_node.add_mini_node(last_entry.disambiguator, char, pos_id)

    def delete_node_with_pos_id(self, pos_id: TreedocPosID) -> None:
        node = self.get_node_with_pos_id(pos_id)
        node.mark_deleted()

    def get_node_with_pos_id(self, pos_id: TreedocPosID) -> TreedocMiniNode:
        node: TreedocMajorNode | TreedocMiniNode = self.root

        for entry in pos_id.entries:
            major_node = node.get_child(entry.direction)
            assert major_node is not None
            if entry.disambiguator is None:
                node = major_node
            else:
                mini_node = major_node.get_mini_node(entry.disambiguator)
                assert mini_node is not None
                node = mini_node

        assert isinstance(node, TreedocMiniNode)
        return node


class TreedocMajorNode:
    parent: TreedocMajorNode | TreedocMiniNode | None  # None for the root of the tree.

    left_child: TreedocMajorNode | None
    right_child: TreedocMajorNode | None

    mini_nodes: list[TreedocMiniNode]  # Ordered by disambiguator.

    count: int  # Number of atoms in this subtree, not counting tombstones
    tombstone_count: int  # Number of tombstones in this subtree

    def __init__(self, parent: TreedocMajorNode | TreedocMiniNode | None):
        self.parent = parent
        self.left_child = None
        self.right_child = None
        self.mini_nodes = []
        self.count = 0
        self.tombstone_count = 0

    def get_child(self, direction: Literal[0, 1]) -> TreedocMajorNode | None:
        return self.left_child if direction == 0 else self.right_child

    def get_or_create_child(self, direction: Literal[0, 1]) -> TreedocMajorNode:
        child = self.get_child(direction)
        if child is None:
            child = TreedocMajorNode(self)
            if direction == 0:
                self.left_child = child
            else:
                self.right_child = child
        return child

    def get_mini_node(self, disambiguator: Disambiguator) -> TreedocMiniNode | None:
        for mini_node in self.mini_nodes:
            if mini_node.disambiguator == disambiguator:
                return mini_node
        return None

    def add_mini_node(self, disambiguator: Disambiguator, char: UniqueChar, pos_id: TreedocPosID) -> TreedocMiniNode:
        # Two inserts never produce the same PosID: only concurrent inserts land in the
        # same major node, and concurrent inserts come from different sites.
        assert self.get_mini_node(disambiguator) is None

        node = TreedocMiniNode(self, pos_id, disambiguator, char)

        # Insert into mini_nodes while preserving the order of disambiguators.
        current_index = 0
        while current_index < len(self.mini_nodes) and self.mini_nodes[current_index].disambiguator.less_than(
            disambiguator
        ):
            current_index += 1

        self.mini_nodes.insert(current_index, node)

        add_to_counts(self, node.count, node.tombstone_count)

        return node

    def traverse(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []

        if self.left_child is not None:
            result += self.left_child.traverse()

        for mini_node in self.mini_nodes:
            result += mini_node.traverse()

        if self.right_child is not None:
            result += self.right_child.traverse()

        return result

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []

        if self.left_child is not None:
            result += self.left_child.traverse_with_tombstones()

        for mini_node in self.mini_nodes:
            result += mini_node.traverse_with_tombstones()

        if self.right_child is not None:
            result += self.right_child.traverse_with_tombstones()

        return result

    def get_node_at_index(self, index: int) -> TreedocMiniNode:
        if index < 0 or index >= self.count:
            raise IndexError()

        current_count = 0

        if self.left_child is not None:
            if current_count + self.left_child.count >= index + 1:
                return self.left_child.get_node_at_index(index - current_count)
            current_count += self.left_child.count

        for mini_node in self.mini_nodes:
            if current_count + mini_node.count >= index + 1:
                return mini_node.get_node_at_index(index - current_count)
            current_count += mini_node.count

        if self.right_child is not None and current_count + self.right_child.count >= index + 1:
            return self.right_child.get_node_at_index(index - current_count)

        raise IndexError()

    # The first node of this subtree in the walk of the tree, tombstones included.
    def leftmost_node(self) -> TreedocMiniNode:
        if self.left_child is not None:
            return self.left_child.leftmost_node()

        if len(self.mini_nodes) != 0:
            return self.mini_nodes[0].leftmost_node()

        assert self.right_child is not None
        return self.right_child.leftmost_node()


class TreedocMiniNode:
    parent: TreedocMajorNode

    pos_id: TreedocPosID
    disambiguator: Disambiguator
    value: UniqueChar
    deleted: bool

    left_child: TreedocMajorNode | None
    right_child: TreedocMajorNode | None

    count: int  # Number of atoms in this subtree, not counting tombstones
    tombstone_count: int  # Number of tombstones in this subtree

    def __init__(self, parent: TreedocMajorNode, pos_id: TreedocPosID, disambiguator: Disambiguator, value: UniqueChar):
        self.parent = parent
        self.pos_id = pos_id
        self.disambiguator = disambiguator
        self.value = value
        self.deleted = False
        self.left_child = None
        self.right_child = None
        self.count = 1
        self.tombstone_count = 0

    def get_child(self, direction: Literal[0, 1]) -> TreedocMajorNode | None:
        return self.left_child if direction == 0 else self.right_child

    def get_or_create_child(self, direction: Literal[0, 1]) -> TreedocMajorNode:
        child = self.get_child(direction)
        if child is None:
            child = TreedocMajorNode(self)
            if direction == 0:
                self.left_child = child
            else:
                self.right_child = child
        return child

    def traverse(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []

        if self.left_child is not None:
            result += self.left_child.traverse()

        if not self.deleted:
            result.append(self.value)

        if self.right_child is not None:
            result += self.right_child.traverse()

        return result

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []

        if self.left_child is not None:
            result += self.left_child.traverse_with_tombstones()

        result.append(self.value)

        if self.right_child is not None:
            result += self.right_child.traverse_with_tombstones()

        return result

    def get_node_at_index(self, index: int) -> TreedocMiniNode:
        if index < 0 or index >= self.count:
            raise IndexError()

        current_count = 0

        if self.left_child is not None:
            if current_count + self.left_child.count >= index + 1:
                return self.left_child.get_node_at_index(index - current_count)
            current_count += self.left_child.count

        # Only include the atom of this node if it is not a tombstone
        if not self.deleted:
            current_count += 1
            if current_count == index + 1:
                return self

        if self.right_child is not None and current_count + self.right_child.count >= index + 1:
            return self.right_child.get_node_at_index(index - current_count)

        raise IndexError()

    def leftmost_node(self) -> TreedocMiniNode:
        if self.left_child is not None:
            return self.left_child.leftmost_node()
        return self

    # A delete keeps the node, and only discards its atom (section 3.3.2).
    def mark_deleted(self) -> None:
        if not self.deleted:
            self.deleted = True
            add_to_counts(self, -1, 1)


def add_to_counts(node: TreedocMajorNode | TreedocMiniNode | None, count: int, tombstone_count: int) -> None:
    while node is not None:
        node.count += count
        node.tombstone_count += tombstone_count
        node = node.parent
