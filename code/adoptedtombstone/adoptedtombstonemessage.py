from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

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

