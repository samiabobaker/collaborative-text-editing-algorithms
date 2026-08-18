from __future__ import annotations

from dataclasses import dataclass

from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class YjsId:
    """Identity of a single inserted character.

    Yjs identifies items by (client, sequence number) rather than by a global
    counter, because the client component doubles as the tie breaker when two
    clients insert into exactly the same slot.
    """

    client_id: int
    seq: int


class YjsItem:
    """One character in the document, plus the two anchors it was typed between.

    origin_left / origin_right are the ids of the items that sat immediately to
    the left and right of this one at the moment it was created, tombstones
    included. None means "start of document" / "end of document".
    """

    id: YjsId
    origin_left: YjsId | None
    origin_right: YjsId | None
    value: UniqueChar
    deleted: bool

    def __init__(
        self,
        id: YjsId,
        origin_left: YjsId | None,
        origin_right: YjsId | None,
        value: UniqueChar,
    ):
        self.id = id
        self.origin_left = origin_left
        self.origin_right = origin_right
        self.value = value
        self.deleted = False


class YjsDocument:
    """The YATA sequence: every item ever inserted, held in document order.

    Deleted items stay in the list as tombstones so that concurrent operations
    which anchored to them can still be positioned.
    """

    items: list[YjsItem]
    version: dict[int, int]  # client_id -> last integrated seq
    count: int  # number of items that are not tombstones

    def __init__(self):
        self.items = []
        self.version = {}
        self.count = 0

    # ---- reading -------------------------------------------------------

    def traverse(self) -> list[UniqueChar]:
        return [item.value for item in self.items if not item.deleted]

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return [item.value for item in self.items]

    # ---- lookups -------------------------------------------------------

    def __find_item(self, id: YjsId | None) -> int:
        """Index of the item with this id, or -1 for None (start of document)."""
        if id is None:
            return -1

        for index, item in enumerate(self.items):
            if item.id == id:
                return index

        raise IndexError("Could not find item")

    def __find_index_at_position(self, position: int) -> int:
        """Raw index in self.items of the position'th visible character.

        Tombstones are skipped when counting but still occupy an index, so the
        result can point just after a run of deleted items.
        """
        if position < 0 or position > self.count:
            raise IndexError()

        remaining = position
        for index, item in enumerate(self.items):
            if item.deleted:
                continue
            if remaining == 0:
                return index
            remaining -= 1

        if remaining == 0:
            return len(self.items)

        raise IndexError()

    # ---- local operations ----------------------------------------------

    def insert_char(self, position: int, id: YjsId, char: UniqueChar) -> YjsItem:
        """Insert locally at a visible position, returning the item created.

        The anchors are the raw neighbours in the item list, which may well be
        tombstones - that is deliberate, since only ids are stable enough to
        anchor concurrent insertions against.
        """
        index = self.__find_index_at_position(position)

        item = YjsItem(
            id,
            self.items[index - 1].id if index > 0 else None,
            self.items[index].id if index < len(self.items) else None,
            char,
        )
        self.integrate(item)
        return item

    def delete_char(self, position: int) -> YjsItem:
        index = self.__find_index_at_position(position)
        item = self.items[index]
        self.__mark_deleted(item)
        return item

    # ---- remote operations ---------------------------------------------

    def delete_item_with_id(self, id: YjsId) -> None:
        self.__mark_deleted(self.items[self.__find_item(id)])

    def integrate(self, new_item: YjsItem) -> None:
        """Place new_item in the sequence - the YATA integration rule.

        Everything strictly between origin_left and origin_right was inserted
        concurrently with new_item, so the loop walks that window and works out
        where among those competitors new_item belongs.
        """
        last_seen = self.version.get(new_item.id.client_id, -1)
        if new_item.id.seq != last_seen + 1:
            raise ValueError("Operations out of order")
        self.version[new_item.id.client_id] = new_item.id.seq

        left = self.__find_item(new_item.origin_left)
        right = len(self.items) if new_item.origin_right is None else self.__find_item(new_item.origin_right)

        dest_index = left + 1
        scanning = False

        index = dest_index
        while True:
            # While scanning we have a candidate position but cannot commit to
            # it yet, so dest_index stays frozen where the scan began.
            if not scanning:
                dest_index = index

            if index == len(self.items):
                break
            if index == right:
                # No concurrency left to resolve - this slot is ours.
                break

            other = self.items[index]
            other_left = self.__find_item(other.origin_left)
            other_right = len(self.items) if other.origin_right is None else self.__find_item(other.origin_right)

            if other_left < left:
                # Anchored further left than us, so it and its subtree come
                # first. Insert here.
                break
            elif other_left == left:
                # Same anchor: a genuine conflict, broken by client id.
                if new_item.id.client_id > other.id.client_id:
                    scanning = False
                elif other_right == right:
                    break
                else:
                    scanning = True
            else:
                # Descendant of something we have already passed - skip it.
                pass

            index += 1

        self.items.insert(dest_index, new_item)
        if not new_item.deleted:
            self.count += 1

    # ---- internals -----------------------------------------------------

    def __mark_deleted(self, item: YjsItem) -> None:
        if not item.deleted:
            item.deleted = True
            self.count -= 1
