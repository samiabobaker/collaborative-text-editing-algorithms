from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class SOCT2InsertionOperation:
    priority: int
    position: int
    character: UniqueChar


@dataclass
class SOCT2DeletionOperation:
    priority: int
    position: int

SOCT2Operation = SOCT2InsertionOperation | SOCT2DeletionOperation

@dataclass
class SOCT2Message:
    client_id: int
    vector_clock: dict[int, int]
    operation: SOCT2Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

