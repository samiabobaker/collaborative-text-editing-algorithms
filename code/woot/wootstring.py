from dataclasses import dataclass
from typing import Literal

from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class WOOTIdentifier:
    client_id: int
    number: int


StartWOOTId = WOOTIdentifier(-1, 0)
EndWOOTId = WOOTIdentifier(-1, 1)


@dataclass
class WOOTCharacter:
    id: WOOTIdentifier
    character: UniqueChar
    visible: bool
    prev_id: WOOTIdentifier
    next_id: WOOTIdentifier


WOOTStringEntry = WOOTCharacter | Literal["start"] | Literal["end"]


def get_string_entry_id(c: WOOTStringEntry) -> WOOTIdentifier:
    if c == "start":
        return StartWOOTId
    elif c == "end":
        return EndWOOTId
    else:
        return c.id


class WOOTString:
    string: list[WOOTStringEntry]

    def __init__(self):
        self.string = ["start", "end"]

    def get_index_of(self, c: WOOTIdentifier) -> int:
        ids = [get_string_entry_id(s) for s in self.string]
        return ids.index(c)

    def get_substring_between(self, start: int, end: int):
        return self.string[start + 1 : end]

    def insert_char(self, pos: int, c: WOOTCharacter):
        self.string.insert(pos, c)

    def less_than_or_equal_to(self, a: WOOTIdentifier, b: WOOTIdentifier):
        return self.get_index_of(a) <= self.get_index_of(b)

    def read_state(self) -> list[UniqueChar]:
        return [c.character for c in self.string if c != "start" and c != "end" and c.visible]

    def ith_visible(self, index: int) -> WOOTStringEntry:
        visible_string: list[WOOTStringEntry] = [c for c in self.string if c == "start" or c == "end" or c.visible]
        return visible_string[index]

    def contains(self, character_id: WOOTIdentifier) -> bool:
        return any(get_string_entry_id(character) == character_id for character in self.string)
