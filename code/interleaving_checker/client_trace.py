from dataclasses import dataclass
from typing import Literal

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


class Character:
    char: UniqueChar
    left_origin: UniqueChar | Literal["start"]
    right_origin: UniqueChar | Literal["end"]
    left_origin_of: list[UniqueChar]
    right_origin_of: list[UniqueChar]

    def __init__(
        self, char: UniqueChar, left_origin: UniqueChar | Literal["start"], right_origin: UniqueChar | Literal["end"]
    ):
        self.char = char
        self.left_origin = left_origin
        self.right_origin = right_origin
        self.left_origin_of = []
        self.right_origin_of = []

    def add_to_right_origin_of(self, char: UniqueChar):
        self.right_origin_of.append(char)

    def add_to_left_origin_of(self, char: UniqueChar):
        self.left_origin_of.append(char)

    def copy(self) -> Character:
        character_copy = Character(self.char, self.left_origin, self.right_origin)

        character_copy.left_origin_of = list(self.left_origin_of)
        character_copy.right_origin_of = list(self.right_origin_of)

        return character_copy

    def __str__(self) -> str:
        return f"""Char: {self.char}
                   Left: {self.left_origin} 
                   Right: {self.right_origin}
                   LeftOf: {self.left_origin_of}
                   RightOf: {self.right_origin_of} """


class ClientTrace:
    events_seen: list[Event]
    states_after_events: list[list[UniqueChar]]

    def __init__(self):
        self.events_seen = []
        self.states_after_events = []

    def add_event(self, event: Event, state: list[UniqueChar]) -> None:
        self.events_seen.append(event)
        self.states_after_events.append(list(state))

    def copy(self) -> ClientTrace:
        trace_copy = ClientTrace()
        trace_copy.events_seen = list(self.events_seen)
        trace_copy.states_after_events = list(self.states_after_events)
        return trace_copy


@dataclass
class Event:
    operation: list[ClientInsertOperation | ClientDeleteOperation]
    performed_locally: bool
