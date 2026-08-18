from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class MarkAndRetraceInsertionOperation:
    client_id: int
    state_vector: dict[int, int]
    character: UniqueChar
    position: int


@dataclass
class MarkAndRetraceDeletionOperation:
    client_id: int
    state_vector: dict[int, int]
    position: int


MarkAndRetraceOperation = MarkAndRetraceInsertionOperation | MarkAndRetraceDeletionOperation


@dataclass
class MarkAndRetraceMessage:
    vector_clock: dict[int, int]
    operation: MarkAndRetraceOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
