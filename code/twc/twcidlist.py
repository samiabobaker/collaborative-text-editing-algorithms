from dataclasses import dataclass

from unique_char.uniquechar import UniqueChar


@dataclass
class TWCIdListEntry:
    element_id: int
    character: UniqueChar
    is_deleted: bool


class TWCIdList:
    """Ordered list of entries, each an element id, a character and a deleted flag.

    The order is fixed by where each entry was inserted rather than by sorting the
    ids, so the ids carry no order of their own.
    """

    def __init__(self) -> None:
        self.entries: list[TWCIdListEntry] = []

    def copy(self) -> TWCIdList:
        new = TWCIdList()
        new.entries = [TWCIdListEntry(entry.element_id, entry.character, entry.is_deleted) for entry in self.entries]
        return new

    def insert_after(self, before: int | None, new_id: int, character: UniqueChar) -> None:
        """Insert immediately after `before` in the known order, tombstones included.

        A `before` of None inserts at the start. Raises if `before` is not known or
        if `new_id` is already in the list.
        """
        if any(entry.element_id == new_id for entry in self.entries):
            raise ValueError(f"TWCIdList.insert_after: inserted id {new_id} is already known")
        if before is None:
            index = -1  # -1 so that index + 1 == 0: insert at the beginning
        else:
            index = -1
            for i, entry in enumerate(self.entries):
                if entry.element_id == before:
                    index = i
                    break
            if index == -1:
                raise ValueError(f"TWCIdList.insert_after: before id {before} is not known")
        self.entries.insert(index + 1, TWCIdListEntry(new_id, character, False))

    def delete(self, element_id: int) -> None:
        """Mark an id deleted, leaving it in place as a tombstone.

        Does nothing if the id is already deleted. The reference editor instead
        resolves the named element back to an index and deletes with a bias to
        the right, which under concurrency can delete the following character;
        this follows the rule as described rather than that behaviour.
        """
        for entry in self.entries:
            if entry.element_id == element_id:
                entry.is_deleted = True
                return

    # ---- views over present (non-deleted) entries -----------------------

    def present_chars(self) -> list[UniqueChar]:
        """The user-visible text: chars of non-deleted entries, in order."""
        return [entry.character for entry in self.entries if not entry.is_deleted]

    def at_present(self, index: int) -> int:
        """Element id of the index-th PRESENT entry (index over visible text)."""
        i = 0
        for entry in self.entries:
            if not entry.is_deleted:
                if i == index:
                    return entry.element_id
                i += 1
        raise IndexError(f"TWCIdList.at_present: index {index} out of bounds")
