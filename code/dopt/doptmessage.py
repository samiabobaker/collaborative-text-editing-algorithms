from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class dOPTInsertionOperation:
    priority: int
    position: int
    character: UniqueChar


@dataclass
class dOPTDeletionOperation:
    priority: int
    position: int

@dataclass
class dOPTNoOperation:
    priority: int


dOPTOperation = dOPTInsertionOperation | dOPTDeletionOperation | dOPTNoOperation

@dataclass
class dOPTMessage:
    client_id: int
    vector_clock: dict[int, int]
    operation: dOPTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation #The client operation that triggered this message to be sent.