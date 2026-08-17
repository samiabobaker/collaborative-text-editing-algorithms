from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class POTInsertionOperation:
    position: int
    character: UniqueChar
    client_id: int

@dataclass
class POTDeletionOperation:
    position: int

class POTNoOperation:
    pass

POTOperation = POTInsertionOperation | POTDeletionOperation | POTNoOperation

@dataclass
class POTMessage:
    client_id: int
    rto: int
    to: int
    operation: POTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

