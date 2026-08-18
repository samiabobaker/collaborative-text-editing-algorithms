from dataclasses import dataclass
from typing import Literal

from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class WOOTOIdentifier:
    client_id: int
    number: int


StartWOOTOId = WOOTOIdentifier(-1, 0)
EndWOOTOId = WOOTOIdentifier(-1, 1)


@dataclass
class WOOTOCharacter:
    id: WOOTOIdentifier
    character: UniqueChar
    visible: bool
    prev_id: WOOTOIdentifier
    next_id: WOOTOIdentifier
    degree: int


WOOTOStringEntry = WOOTOCharacter | Literal["start"] | Literal["end"]


def get_string_entry_id(c: WOOTOStringEntry) -> WOOTOIdentifier:
    if c == "start":
        return StartWOOTOId
    elif c == "end":
        return EndWOOTOId
    else:
        return c.id


class WOOTOString:
    string: list[WOOTOStringEntry]

    def __init__(self):
        self.string = ["start", "end"]

    def get_index_of(self, c: WOOTOIdentifier) -> int:
        ids = [get_string_entry_id(s) for s in self.string]
        return ids.index(c)

    def get_substring_between(self, start: int, end: int):
        return self.string[start + 1 : end]

    def insert_char(self, pos: int, c: WOOTOCharacter):
        self.string.insert(pos, c)

    def less_than_or_equal_to(self, a: WOOTOIdentifier, b: WOOTOIdentifier):
        return self.get_index_of(a) <= self.get_index_of(b)

    def read_state(self) -> list[UniqueChar]:
        return [c.character for c in self.string if c != "start" and c != "end" and c.visible]

    def ith_visible(self, index: int) -> WOOTOStringEntry:
        visible_string: list[WOOTOStringEntry] = [c for c in self.string if c == "start" or c == "end" or c.visible]
        return visible_string[index]

    def contains(self, character_id: WOOTOIdentifier) -> bool:
        return any(get_string_entry_id(character) == character_id for character in self.string)
