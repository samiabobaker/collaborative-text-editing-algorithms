from __future__ import annotations

from dataclasses import dataclass

from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class Sync9Id:
    """Identity of a single inserted character.

    As in Yjs, items are identified by (client, sequence number), and the
    client component doubles as the tie breaker between concurrent siblings.
    """

    client_id: int
    seq: int


class Sync9Item:
    """One entry in the document.

    Sync9 items are splittable spans. This implementation stores one character
    per item, so a span has length 0 or 1 and `value` is nullable: an item with
    value None is a *split marker*, a zero length remnant left behind when an
    item had to be opened up so that something could be inserted immediately
    before its content. A marker carries the same id as the item it was split
    from, so the document can hold two entries sharing one id.

    Unlike Yjs there is no origin_right. A new item names a single anchor,
    origin_left, plus a flag saying which side of that anchor it attaches to:

      insert_after=True   - attach after the anchor's content
      insert_after=False  - attach before the anchor's content

    That pair is what gives Sync9 an insertion position both before and after
    every existing character.
    """

    id: Sync9Id
    origin_left: Sync9Id | None
    insert_after: bool
    value: UniqueChar | None
    deleted: bool

    def __init__(
        self,
        id: Sync9Id,
        origin_left: Sync9Id | None,
        insert_after: bool,
        value: UniqueChar | None,
    ):
        self.id = id
        self.origin_left = origin_left
        self.insert_after = insert_after
        self.value = value
        self.deleted = False


class Sync9Document:
    """The Sync9 sequence: every item ever inserted, held in document order.

    Deleted items stay in the list as tombstones so that concurrent operations
    which anchored to them can still be positioned. Split markers stay too, for
    the same reason - they are the anchor for "before this character".
    """

    items: list[Sync9Item]
    version: dict[int, int]  # client_id -> last integrated seq
    count: int  # number of items that carry a character and are not tombstones

    def __init__(self):
        self.items = []
        self.version = {}
        self.count = 0

    # ---- reading -------------------------------------------------------

    def traverse(self) -> list[UniqueChar]:
        return [item.value for item in self.items if not item.deleted and item.value is not None]

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return [item.value for item in self.items if item.value is not None]

    # ---- lookups -------------------------------------------------------

    def __find_item(self, id: Sync9Id | None, at_end: bool = False) -> int:
        """Index of the item with this id, or -1 for None (start of document).

        A split id matches two entries: the marker first, then the content. If
        at_end is set only the entry carrying content matches, which is how
        "after this character" is distinguished from "before" it.
        """
        if id is None:
            return -1

        for index, item in enumerate(self.items):
            if item.id == id and (not at_end or item.value is not None):
                return index

        raise IndexError("Could not find item")

    def __find_index_at_position(self, position: int, stick_end: bool = False) -> int:
        """Raw index in self.items of the position'th visible character.

        Tombstones and split markers are skipped when counting but still occupy
        an index. With stick_end set the search stops at the first index the
        position could refer to, markers included, which is what a local insert
        wants so that it can then walk down into the children there.
        """
        remaining = position
        for index, item in enumerate(self.items):
            if stick_end and remaining == 0:
                return index
            if item.deleted or item.value is None:
                continue
            if remaining == 0:
                return index
            remaining -= 1

        if remaining == 0:
            return len(self.items)

        raise IndexError("past end of the document")

    # ---- local operations ----------------------------------------------

    def insert_char(self, position: int, id: Sync9Id, char: UniqueChar) -> Sync9Item:
        """Insert locally at a visible position, returning the item created.

        Where Yjs simply reads off its two neighbours, Sync9 has to choose an
        anchor and a side. It starts by attaching after the character on the
        left, then walks down the chain of that anchor's leftmost children,
        switching to "before" as it descends, until it reaches something that
        actually carries content or runs out of children. That keeps a new
        character as deep in the tree as it can go, next to the item it was
        really typed against.
        """
        index = self.__find_index_at_position(position, stick_end=True)

        parent_id = self.items[index - 1].id if index > 0 else None
        origin_left = parent_id
        insert_after = True

        while True:
            next_item = self.items[index] if index < len(self.items) else None
            if next_item is None or next_item.origin_left != parent_id:
                break

            parent_id = next_item.id
            origin_left = next_item.id
            insert_after = False

            # Once we reach real content we stop and insert before it, which
            # is what forces the split in integrate.
            if next_item.value is not None:
                break

            index += 1

        item = Sync9Item(id, origin_left, insert_after, char)
        self.integrate(item)
        return item

    def delete_char(self, position: int) -> Sync9Item:
        index = self.__find_index_at_position(position)
        item = self.items[index]
        self.__mark_deleted(item)
        return item

    # ---- remote operations ---------------------------------------------

    def delete_item_with_id(self, id: Sync9Id) -> None:
        # Only the entry carrying content can be deleted; if the item has been
        # split, its marker is not a character and stays put.
        self.__mark_deleted(self.items[self.__find_item(id, at_end=True)])

    def integrate(self, new_item: Sync9Item) -> None:
        """Place new_item in the sequence - the Sync9 integration rule.

        There are two cases. If we are attaching before an anchor that still
        holds its content, we split the anchor and drop straight in, because
        being the anchor's "before" child makes us an only child and there is
        nobody to compare against. Otherwise we scan forward over the anchor's
        existing children and order ourselves among them by client id.
        """
        last_seen = self.version.get(new_item.id.client_id, -1)
        if new_item.id.seq != last_seen + 1:
            raise ValueError("Operations out of order")
        self.version[new_item.id.client_id] = new_item.id.seq

        parent_index = self.__find_item(new_item.origin_left, new_item.insert_after)
        dest_index = parent_index + 1

        if (
            parent_index >= 0
            and new_item.origin_left is not None
            and not new_item.insert_after
            and self.items[parent_index].value is not None
        ):
            # Split the anchor: a zero length marker keeps its identity and its
            # own anchoring, and its content moves to the right of us.
            parent = self.items[parent_index]
            marker = Sync9Item(parent.id, parent.origin_left, parent.insert_after, None)
            marker.deleted = parent.deleted
            self.items.insert(parent_index, marker)
            # We know we are an only child, so there is nothing to scan past.
        else:
            while dest_index < len(self.items):
                other = self.items[dest_index]
                other_parent = self.__find_item(other.origin_left, other.insert_after)

                if other_parent < parent_index:
                    # Anchored further left than us, so it comes first.
                    break
                elif other_parent == parent_index:  # noqa: SIM102
                    # A sibling. Order broken by client id.
                    if new_item.id.client_id < other.id.client_id:
                        break
                # Otherwise it is a descendant of a sibling we have passed, or
                # of us - either way, skip over it.
                dest_index += 1

        self.items.insert(dest_index, new_item)
        if not new_item.deleted and new_item.value is not None:
            self.count += 1

    # ---- internals -----------------------------------------------------

    def __mark_deleted(self, item: Sync9Item) -> None:
        if not item.deleted:
            item.deleted = True
            if item.value is not None:
                self.count -= 1
