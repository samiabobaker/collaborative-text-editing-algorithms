from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class AdOPTedInsertionOperation:
    position: int
    character: UniqueChar
    priority: int
    b: set[AdOPTedOperation]
    a: set[AdOPTedOperation]
    vector_clock: dict[int,int]

@dataclass
class AdOPTedDeletionOperation:
    position: int
    priority: int
    vector_clock: dict[int, int]

class AdOPTedNoOperation:
    vector_clock: dict[int, int]


AdOPTedOperation = AdOPTedInsertionOperation | AdOPTedDeletionOperation | AdOPTedNoOperation

@dataclass
class AdOPTedMessage:
    client_id: int
    vector_clock: dict[int, int]
    operation: AdOPTedOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation #The client operation that triggered this message to be sent.

