from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


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
