from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class AdOPTedTombstoneInsertionOperation:
    position: int
    character: UniqueChar
    priority: int

@dataclass
class AdOPTedTombstoneDeletionOperation:
    position: int
    priority: int

class AdOPTedTombstoneNoOperation:
    pass


AdOPTedTombstoneOperation = AdOPTedTombstoneInsertionOperation | AdOPTedTombstoneDeletionOperation | AdOPTedTombstoneNoOperation

@dataclass
class AdOPTedMessage:
    client_id: int
    vector_clock: dict[int, int]
    operation: AdOPTedTombstoneOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation #The client operation that triggered this message to be sent.

