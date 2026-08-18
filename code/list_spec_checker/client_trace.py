from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


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
