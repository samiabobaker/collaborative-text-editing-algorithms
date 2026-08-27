from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from unique_char.uniquechar import UniqueChar

# The state of an item at the prepare version, as in Diamond Types
# (src/listmerge/yjsspan.rs, SpanState). Deletes are counted rather than flagged so
# that concurrent deletes of the same item nest and can be undone one at a time.
NOT_INSERTED_YET = 0
INSERTED = 1
DELETED_ONCE = 2


@dataclass(frozen=True, order=True)
class DiamondTypesId:
    """Identity of a single operation: the agent that made it and its sequence number.

    Diamond Types names agents with a string and breaks ties between concurrent
    inserts by comparing agent names and then sequence numbers
    (src/causalgraph/agent_assignment/mod.rs, tie_break_agent_versions). Here the
    agent name is the model checker's client id, compared numerically. Any total
    order over agents does, as long as every client uses the same one.
    """

    client_id: int
    seq: int


@dataclass(frozen=True)
class DiamondTypesOperation:
    """One entry of the oplog, which is also what goes on the wire.

    Nothing about an operation is rewritten as it travels. position is the index
    in the document at the version the operation was made against, not in the
    receiver's document: for an insert the place the character was typed, for a
    delete the place the character was removed from. That is Diamond Types'
    TextOperation.loc.span.start (src/list/operation.rs).

    parents is the frontier of the causal graph at the moment the operation was
    made, named by agent version, which is what Diamond Types puts on the wire for
    the causal graph. It is what lets a receiver replay the event graph instead of
    transforming against it.

    Diamond Types stores a typed run as one span, but every character in a run
    still takes its own sequence number (INTERNALS.md), so storing one operation
    per character is equivalent. The reference TypeScript implementation splits
    runs the same way.
    """

    kind: Literal["ins", "del"]
    position: int
    character: UniqueChar | None  # the content of an insert, None for a delete
    parents: tuple[DiamondTypesId, ...]


class DiamondTypesItem:
    """One character of the merged document, in YjsMod / FugueMax form.

    This is the single character form of Diamond Types' CRDTSpan
    (src/listmerge/yjsspan.rs). Origins are local versions, with -1 standing for
    the start or the end of the document.

    cur_state is the state at the prepare version, the part of the event graph
    that has been replayed so far: NOT_INSERTED_YET, INSERTED, or a count of the
    deletes replayed. Retreat and advance move it down and up.

    end_state_deleted is the state in the merged document. The first delete to
    reach the item sets it and nothing unsets it, since retreating only rewinds
    the prepare version. It decides whether the item is visible, and it gates the
    transformed delete: only the first delete of an item takes a character out of
    the merged document, which is what Rust reports as BaseMoved rather than
    DeleteAlreadyHappened.
    """

    lv: int
    cur_state: int
    end_state_deleted: bool
    origin_left: int
    origin_right: int
    value: UniqueChar

    def __init__(self, lv: int, origin_left: int, origin_right: int, value: UniqueChar):
        self.lv = lv
        self.cur_state = INSERTED
        self.end_state_deleted = False
        self.origin_left = origin_left
        self.origin_right = origin_right
        self.value = value

    def cur_width(self) -> int:
        """Whether the item takes up space at the prepare version (Rust: takes_up_space::<true>)."""
        return 1 if self.cur_state == INSERTED else 0

    def end_width(self) -> int:
        """Whether the item takes up space in the merged document (Rust: takes_up_space::<false>)."""
        return 0 if self.end_state_deleted else 1


class DiamondTypesDocument:
    """An eg-walker replica: the oplog, the event graph over it, and the merged document.

    Diamond Types does not hold a CRDT as its state. A replica keeps the
    operations it has seen exactly as they were made, plus the causal graph over
    them, and replays that graph to work out the merged document (the paper,
    section 3). An operation is named by its local version, the index it was
    appended at, called lv throughout; lv_to_id holds what goes on the wire.

    The replay tracks two versions. version is the frontier of the whole oplog,
    which is what a new local operation names as its parents. prepare_version is
    the frontier of the operations that have been replayed into items. Before an
    operation is applied the prepare version has to be moved onto that operation's
    parents, by retreating the operations that are in the prepare version but not
    in the parents and advancing the ones that are in the parents but not in the
    prepare version. Retreating and advancing only touch cur_state, so no item is
    ever moved or removed.
    """

    oplog: list[DiamondTypesOperation]
    parents: list[tuple[int, ...]]  # lv -> the lvs of its parents, ascending
    lv_to_id: list[DiamondTypesId]
    id_to_lv: dict[DiamondTypesId, int]
    version: list[int]  # frontier of the oplog, ascending

    items: list[DiamondTypesItem]  # every item ever inserted, in merged document order
    items_by_lv: list[DiamondTypesItem | None]  # lv -> the item an insert made, None for a delete
    delete_targets: dict[int, int]  # lv of a delete -> lv of the item it deleted
    prepare_version: list[int]  # frontier of what has been replayed, ascending
    snapshot: list[UniqueChar]  # the merged document, tombstones removed

    def __init__(self):
        self.oplog = []
        self.parents = []
        self.lv_to_id = []
        self.id_to_lv = {}
        self.version = []
        self.items = []
        self.items_by_lv = []
        self.delete_targets = {}
        self.prepare_version = []
        self.snapshot = []

    # ---- reading -------------------------------------------------------

    def traverse(self) -> list[UniqueChar]:
        return list(self.snapshot)

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return [item.value for item in self.items]

    # ---- lookups -------------------------------------------------------

    def knows(self, id: DiamondTypesId) -> bool:
        return id in self.id_to_lv

    def is_causally_ready(self, operation: DiamondTypesOperation) -> bool:
        # An operation can only be replayed once every one of its parents is here,
        # which is also what makes the append order a topological order.
        return all(parent in self.id_to_lv for parent in operation.parents)

    def __index_of(self, lv: int) -> int:
        for index, item in enumerate(self.items):
            if item.lv == lv:
                return index

        raise IndexError("Could not find item")

    def __find_by_cur_pos(self, position: int) -> tuple[int, int]:
        """Cursor to the item holding a position at the prepare version.

        Returns an index into items and the matching index into the merged
        document. The two run at different speeds because they count different
        things: one counts what is visible at the prepare version, the other what
        is visible at the end. Reference implementation: findByCurPos.
        """
        cur_position = 0
        end_position = 0
        index = 0
        while cur_position < position:
            item = self.items[index]
            cur_position += item.cur_width()
            end_position += item.end_width()
            index += 1

        return index, end_position

    # ---- local operations ----------------------------------------------

    def insert_char(self, position: int, id: DiamondTypesId, char: UniqueChar) -> DiamondTypesOperation:
        return self.__add_local_operation(DiamondTypesOperation("ins", position, char, self.__parent_ids()), id)

    def delete_char(self, position: int, id: DiamondTypesId) -> DiamondTypesOperation:
        return self.__add_local_operation(DiamondTypesOperation("del", position, None, self.__parent_ids()), id)

    def __parent_ids(self) -> tuple[DiamondTypesId, ...]:
        return tuple(self.lv_to_id[head] for head in self.version)

    def __add_local_operation(self, operation: DiamondTypesOperation, id: DiamondTypesId) -> DiamondTypesOperation:
        # As in apply_local_operations (src/list/list.rs): a local operation's
        # position is relative to the local document and its parents are that
        # document's version, so the new operation dominates the whole frontier.
        lv = self.__append(operation, id, tuple(self.version))
        self.version = [lv]
        self.__walk(lv)
        return operation

    # ---- remote operations ---------------------------------------------

    def integrate(self, id: DiamondTypesId, operation: DiamondTypesOperation) -> None:
        parent_lvs = tuple(sorted(self.id_to_lv[parent] for parent in operation.parents))
        lv = self.__append(operation, id, parent_lvs)
        # Advance the frontier: the heads the new operation dominates drop out and
        # it takes their place (Rust: Frontier::advance, Graph::find_dominators_2).
        heads = [head for head in self.version if head not in parent_lvs]
        heads.append(lv)
        self.version = sorted(heads)
        self.__walk(lv)

    def __append(self, operation: DiamondTypesOperation, id: DiamondTypesId, parent_lvs: tuple[int, ...]) -> int:
        lv = len(self.oplog)
        self.oplog.append(operation)
        self.parents.append(parent_lvs)
        self.lv_to_id.append(id)
        self.id_to_lv[id] = lv
        self.items_by_lv.append(None)
        return lv

    # ---- the walk ------------------------------------------------------

    def __walk(self, lv: int) -> None:
        """Move the prepare version onto an operation's parents, then apply it.

        This is the body of traverseAndApply in the reference implementation and of
        M2Tracker::walk in Rust. Sequential editing takes the fast path, where the
        prepare version is already sitting on the operation's parents and nothing
        has to be rewound; that is the same case Rust's plan fast forwards through.

        Any topological order over the event graph produces the same document, so
        operations are replayed in append order. Rust instead builds a plan that
        visits them in whichever order needs the least retreating
        (src/listmerge/plan.rs), for the same result.
        """
        parent_lvs = self.parents[lv]
        if tuple(self.prepare_version) != parent_lvs:
            replayed = self.__ancestors(self.prepare_version)
            wanted = self.__ancestors(parent_lvs)
            # Retreat in reverse local version order, so a delete is rewound before
            # the item it deleted is un-inserted. This is the order the paper gives
            # (retreat in reverse topological order); Rust's advance_retreat.rs
            # walks its spans the other way round and leans on the counter in
            # cur_state to make the order not matter.
            for other in sorted(replayed - wanted, reverse=True):
                self.__retreat(other)
            for other in sorted(wanted - replayed):
                self.__advance(other)

        self.__apply(lv)
        # Everything replayed is now the ancestors of the parents plus lv itself,
        # and lv dominates all of them, so the frontier is just lv.
        self.prepare_version = [lv]

    def __ancestors(self, frontier: list[int] | tuple[int, ...]) -> set[int]:
        """Every operation reachable from a frontier, the frontier included."""
        seen: set[int] = set()
        stack = list(frontier)
        while len(stack) != 0:
            lv = stack.pop()
            if lv in seen:
                continue
            seen.add(lv)
            stack.extend(self.parents[lv])

        return seen

    def __target_of(self, lv: int) -> DiamondTypesItem:
        # What an operation acts on: the item a delete deleted, or the item an
        # insert made. Deletes name their target through the map Rust keeps in the
        # index as Marker::Del (src/listmerge/markers.rs).
        target = self.delete_targets[lv] if self.oplog[lv].kind == "del" else lv
        item = self.items_by_lv[target]
        assert item is not None
        return item

    def __retreat(self, lv: int) -> None:
        item = self.__target_of(lv)
        if self.oplog[lv].kind == "del":
            assert item.cur_state >= DELETED_ONCE, "Retreating a delete of an item that is not deleted"
            assert item.end_state_deleted, "Retreating a delete of an item that is not deleted at the end"
        else:
            assert item.cur_state == INSERTED, "Retreating an insert of an item that is not inserted"
        item.cur_state -= 1

    def __advance(self, lv: int) -> None:
        item = self.__target_of(lv)
        if self.oplog[lv].kind == "del":
            assert item.cur_state >= INSERTED, "Advancing a delete of an item that is not inserted"
            assert item.end_state_deleted, "Advancing a delete of an item that is not deleted at the end"
        else:
            assert item.cur_state == NOT_INSERTED_YET, "Advancing an insert of an item that is already inserted"
        item.cur_state += 1

    def __apply(self, lv: int) -> None:
        operation = self.oplog[lv]
        index, end_position = self.__find_by_cur_pos(operation.position)

        if operation.kind == "del":
            # Step over anything that is not there at the prepare version. Rust
            # asserts the target is INSERTED outright rather than skipping
            # (merge.rs, apply); skipping is the defensive form of the same thing.
            while self.items[index].cur_state != INSERTED:
                end_position += self.items[index].end_width()
                index += 1

            item = self.items[index]
            if not item.end_state_deleted:
                del self.snapshot[end_position]
            item.end_state_deleted = True
            item.cur_state += 1
            self.delete_targets[lv] = item.lv
            return

        character = operation.character
        assert character is not None, "An insert must carry a character"

        # The left origin is whatever sits immediately before the cursor
        # (merge.rs: cursor_before_cur_pos(start - 1)).
        origin_left = self.items[index - 1].lv if index > 0 else -1

        # The right origin is the next item that exists at the prepare version,
        # whatever its own left origin is. This is the one place where Diamond
        # Types parts company with plain Fugue, which would use the end of the
        # document unless that next item shares this one's left origin; the
        # reference TypeScript implementation carries both rules, one commented
        # out. Diamond Types' own source says the rule it uses is YjsMod, and that
        # YjsMod and FugueMax merge identically (src/listmerge/yjsspan.rs: "This is
        # a span of YjsMod / FugueMax items. (Those two algorithms generate
        # identical merge behaviour)").
        origin_right = -1
        for other in self.items[index:]:
            if other.cur_state != NOT_INSERTED_YET:
                origin_right = other.lv
                break

        item = DiamondTypesItem(lv, origin_left, origin_right, character)
        self.items_by_lv[lv] = item
        index, end_position = self.__integrate(item, index, end_position)
        self.items.insert(index, item)
        self.snapshot.insert(end_position, item.value)

    def __integrate(self, new_item: DiamondTypesItem, index: int, end_position: int) -> tuple[int, int]:
        """Order a new item against the concurrent items sitting at the cursor.

        Ported from M2Tracker::integrate (src/listmerge/merge.rs). If the item at
        the cursor already exists at the prepare version then nothing is concurrent
        with the new item and it goes straight in. Otherwise the scan walks the run
        of items that do not exist yet, which is bounded by the new item's right
        origin, and orders the new item among them: an item anchored further left
        comes first and ends the scan, an item anchored at the same place is
        ordered by right origin and then by id, and an item anchored further right
        is a descendant of something already passed and is skipped over.

        scanning holds the difference between Yjs and YjsMod. While a competing
        item's right origin sits before the new item's, the cursor is left where it
        was, so a run typed by another client is stepped over whole instead of
        being split apart.
        """
        items = self.items
        if index >= len(items) or items[index].cur_state != NOT_INSERTED_YET:
            return index, end_position

        scanning = False
        scan_index = index
        scan_end_position = end_position
        left_index = index - 1
        right_index = len(items) if new_item.origin_right == -1 else self.__index_of(new_item.origin_right)
        new_id = self.lv_to_id[new_item.lv]

        while scan_index < len(items):
            other = items[scan_index]
            # The run of concurrent items ends at the first item that exists at the
            # prepare version, which by construction is the right origin.
            if other.cur_state != NOT_INSERTED_YET:
                break

            other_left_index = -1 if other.origin_left == -1 else self.__index_of(other.origin_left)
            if other_left_index < left_index:
                break
            if other_left_index == left_index:
                other_right_index = len(items) if other.origin_right == -1 else self.__index_of(other.origin_right)
                if other_right_index == right_index and new_id < self.lv_to_id[other.lv]:
                    # Same pair of origins, so the tie falls to the smaller id.
                    break
                scanning = other_right_index < right_index

            scan_end_position += other.end_width()
            scan_index += 1
            if not scanning:
                index = scan_index
                end_position = scan_end_position

        return index, end_position
