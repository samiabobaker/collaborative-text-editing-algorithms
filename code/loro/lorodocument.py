from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class LoroId:
    """Identity of a single operation, and so of the element it inserted.

    Loro's `ID` is a (peer, counter) pair (loro-common/src/id.rs). Every
    operation draws from the same per peer counter, deletes as well as
    inserts, so an element's id is simply the id of the insert that created
    it. The peer component doubles as the tie breaker between concurrent
    siblings that share both of their origins.
    """

    peer: int
    counter: int

    def __str__(self) -> str:
        return f"{self.peer}@{self.counter}"


@dataclass
class LoroElement:
    """One entry in the rope: a FugueSpan holding a single character.

    Loro's spans are runs of characters that carry an id, both origins and a
    status (container/richtext/fugue_span.rs, lines 191-207). This model
    checker only ever inserts and deletes one character at a time, so a span
    is always one character long and never has to be split.

    A span is visible exactly when `delete_times == 0 and not future`
    (fugue_span.rs, lines 381-386). `delete_times` is an i16 counter in Loro;
    it is kept here as the set of delete operation ids that have been applied,
    because a checkout has to roll individual deletes back when it retreats
    past them (tracker.rs `_checkout`, lines 354-461), and the set makes that
    exact. `future` marks a span the operation being integrated has not seen,
    and is only ever set while an integration is in progress.
    """

    op_id: LoroId
    char: UniqueChar
    origin_left: LoroId | None
    origin_right: LoroId | None
    delete_ops: set[LoroId] = field(default_factory=set[LoroId])
    future: bool = False

    @property
    def peer(self) -> int:
        return self.op_id.peer

    def is_activated(self) -> bool:
        return len(self.delete_ops) == 0 and not self.future


class LoroDocument:
    """The CrdtRope: every span ever inserted, held in document order.

    Ported from the Loro source, commit 4d3d3f1d (loro-crdt 1.14.1), cut down
    to single character atoms and to inserts and deletes. Loro holds the rope
    in a B tree, but that is only an index structure, so a plain list is used
    here and what is ported is the per leaf ordering.

    Operations carry no origins, only an id and the plain visible index they
    were generated at, so every replica recomputes the origins itself against
    the originator's view rather than its own. `__checkout` rebuilds that
    view, which is why the integrate methods take a version vector.

    Siblings go in reverse right origin order, ties broken by peer id, but a
    right origin only counts as a right parent when its element shares our
    left origin. That is Definition 4's right parent rule, so Loro is paper
    Fugue and not FugueMax (Definition 6).
    """

    rope: list[LoroElement]

    def __init__(self) -> None:
        self.rope = []

    # ---- reading -------------------------------------------------------

    def traverse(self) -> list[UniqueChar]:
        return [element.char for element in self.rope if element.is_activated()]

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return [element.char for element in self.rope]

    def origins(self) -> list[tuple[UniqueChar, LoroId | None, LoroId | None]]:
        return [(element.char, element.origin_left, element.origin_right) for element in self.rope]

    # ---- local operations ----------------------------------------------

    def insert_char(self, op_id: LoroId, position: int, char: UniqueChar) -> None:
        """Insert locally at a visible position.

        A local operation needs no checkout: its causal past is everything
        this replica already holds, so no span is `future` and no delete has
        to be rolled back.
        """
        self.__insert_span(op_id, position, char)

    def delete_char(self, op_id: LoroId, position: int) -> LoroElement:
        """Delete locally at a visible position, returning the span tombstoned."""
        target = self.__element_at_visible_position(position)
        self.__delete_span(op_id, target.op_id, position)
        return target

    # ---- remote operations ---------------------------------------------

    def integrate_insert(self, version: dict[int, int], op_id: LoroId, pos: int, char: UniqueChar) -> None:
        rolled_back = self.__checkout(version)
        try:
            self.__insert_span(op_id, pos, char)
        finally:
            self.__restore(rolled_back)

    def integrate_delete(self, version: dict[int, int], op_id: LoroId, target_id: LoroId, pos: int) -> None:
        rolled_back = self.__checkout(version)
        try:
            self.__delete_span(op_id, target_id, pos)
        finally:
            self.__restore(rolled_back)

    # ---- checkout ------------------------------------------------------

    def __checkout(self, version: dict[int, int]) -> list[tuple[LoroElement, set[LoroId]]]:
        """Move the rope back to the state the operation was generated at.

        This is tracker.rs `_checkout` (lines 354-461): every span the version
        does not cover becomes `future`, and every applied delete the version
        does not cover is rolled back. What is visible during the integration
        is then exactly what the originator could see, so the operation's
        plain `pos` index applies directly. The rolled back deletes are
        returned so that `__restore` can put them back, and they are tracked
        by element rather than by rope index because integrating the operation
        shifts the indices.
        """
        rolled_back: list[tuple[LoroElement, set[LoroId]]] = []
        for element in self.rope:
            element.future = not self.__in_version(element.op_id, version)
            if element.delete_ops:
                kept = {delete_id for delete_id in element.delete_ops if self.__in_version(delete_id, version)}
                if len(kept) != len(element.delete_ops):
                    rolled_back.append((element, element.delete_ops - kept))
                    element.delete_ops = kept
        return rolled_back

    def __restore(self, rolled_back: list[tuple[LoroElement, set[LoroId]]]) -> None:
        for element, deletes in rolled_back:
            element.delete_ops |= deletes
        for element in self.rope:
            element.future = False

    @staticmethod
    def __in_version(op_id: LoroId, version: dict[int, int]) -> bool:
        # A version vector entry is the exclusive end of that peer's counters.
        return op_id.counter < version.get(op_id.peer, 0)

    # ---- rope queries --------------------------------------------------

    def __cursor_prefer_left(self, pos: int) -> tuple[int, LoroId | None]:
        """ActiveLenQueryPreferLeft (crdt_rope.rs, lines 557-615).

        Walks the leaves counting activated length and descends into the first
        one where what remains fits, then reads the left origin off the cursor
        (lines 88-108). Returns the rope index the new span goes at, and the
        id at the cursor's offset minus one, which is the previous leaf's last
        id when the cursor sits at offset 0, and None at the very start.
        """
        remaining = pos
        for index, element in enumerate(self.rope):
            active_len = 1 if element.is_activated() else 0
            if remaining <= active_len:
                if active_len == 0 or remaining == 0:
                    # Offset 0, either of an active leaf or of one with no
                    # active length captured at a boundary: the left origin is
                    # the previous leaf's last id.
                    return index, self.rope[index - 1].op_id if index > 0 else None
                # remaining == active_len: the end of this leaf.
                return index + 1, element.op_id
            remaining -= active_len
        if remaining != 0:
            raise IndexError("past end of the document")
        # pos is the whole active length, so the cursor is past the last leaf.
        return len(self.rope), self.rope[-1].op_id if self.rope else None

    def __origin_right_scan(
        self, insert_index: int, origin_left: LoroId | None
    ) -> tuple[LoroId | None, int | None, list[int]]:
        """Find the right origin, scanning right from the cursor.

        crdt_rope.rs lines 110-149: the first span that is not `future` is the
        right origin, tombstones included, and the `future` spans passed on
        the way are the concurrent inserts to be scanned. The right origin is
        also the new span's right parent, but only when it shares our left
        origin, which is the Definition 4 rule described on the class.
        """
        in_between: list[int] = []
        for index in range(insert_index, len(self.rope)):
            element = self.rope[index]
            if not element.future:
                parent_right_leaf = index if element.origin_left == origin_left else None
                return element.op_id, parent_right_leaf, in_between
            in_between.append(index)
        return None, None, in_between

    @staticmethod
    def __cmp_pos(index: int | None, other_index: int | None) -> Literal[-1, 0, 1]:
        """`cmp_pos` (crdt_rope.rs, lines 453-466).

        Compares the rope positions of two right parents. A parent that
        collapsed to None sorts after one that did not, so (Some, None) is
        Less and (None, Some) is Greater.
        """
        match (index, other_index):
            case (None, None):
                return 0
            case (int(), None):
                return -1
            case (None, int()):
                return 1
            case (int(), int()):
                if index < other_index:
                    return -1
                return 1 if index > other_index else 0

    def __scan_in_between(
        self,
        insert_index: int,
        in_between: list[int],
        origin_left: LoroId | None,
        origin_right: LoroId | None,
        parent_right_leaf: int | None,
        peer: int,
    ) -> int:
        """The Fugue sibling scan (crdt_rope.rs, lines 156-237)."""
        scanning = False
        visited: list[LoroId] = []
        for index in in_between:
            other = self.rope[index]
            other_origin_left = other.origin_left
            if other_origin_left != origin_left and (
                other_origin_left is None or all(span_id != other_origin_left for span_id in visited)
            ):
                # This span is anchored further left than we are, and not to
                # anything we have already scanned past, so it comes first.
                break
            visited.append(other.op_id)
            if origin_left == other_origin_left:
                if other.origin_right == origin_right:
                    # Both origins shared, so the peer ids break the tie.
                    if other.peer > peer:
                        break
                    scanning = False
                else:
                    # Different right origins, so their positions decide. A
                    # right origin that does not share our left origin is not
                    # a parent and collapses to None, which is Definition 4's
                    # right parent rule (crdt_rope.rs lines 203-207).
                    other_parent_right_leaf: int | None = None
                    if other.origin_right is not None:
                        other_right_index = self.__index_of_id(other.origin_right)
                        if self.rope[other_right_index].origin_left == origin_left:
                            other_parent_right_leaf = other_right_index
                    match self.__cmp_pos(other_parent_right_leaf, parent_right_leaf):
                        case -1:
                            scanning = True
                        case 0 if other.peer > peer:
                            break
                        case _:
                            scanning = False
            # A span anchored to something already scanned past is a descendant
            # of a sibling rather than a sibling, and inherits whatever was
            # decided for that sibling, which is what carrying `scanning` across
            # iterations does.
            if not scanning:
                insert_index = index + 1
        return insert_index

    def __index_of_id(self, op_id: LoroId) -> int:
        for index, element in enumerate(self.rope):
            if element.op_id == op_id:
                return index
        raise IndexError("Could not find span")

    def __element_at_visible_position(self, position: int) -> LoroElement:
        count = 0
        for element in self.rope:
            if element.is_activated():
                if count == position:
                    return element
                count += 1
        raise IndexError(position)

    # ---- integration ---------------------------------------------------

    def __insert_span(self, op_id: LoroId, pos: int, char: UniqueChar) -> None:
        # `CrdtRope::insert` (container/richtext/tracker/crdt_rope.rs, lines
        # 63-247): find the cursor at visible index pos and read the left
        # origin off it, scan right for the right origin, and if concurrent
        # inserts were stepped over on the way, order the new span among them.
        insert_index, origin_left = self.__cursor_prefer_left(pos)
        origin_right, parent_right_leaf, in_between = self.__origin_right_scan(insert_index, origin_left)
        if in_between:
            insert_index = self.__scan_in_between(
                insert_index, in_between, origin_left, origin_right, parent_right_leaf, op_id.peer
            )
        self.rope.insert(insert_index, LoroElement(op_id, char, origin_left, origin_right))

    def __delete_span(self, op_id: LoroId, target_id: LoroId, pos: int) -> None:
        # tracker.rs `delete` (lines 193-252) and crdt_rope.rs `delete` (lines
        # 256-336): find the span at visible position pos in the checked out
        # state and bump its delete count. Deleting an already deleted span
        # bumps it again and it stays invisible.
        target = self.__element_at_visible_position(pos)
        if target.op_id != target_id:
            raise ValueError("Delete target is not the span at that position")
        target.delete_ops.add(op_id)
