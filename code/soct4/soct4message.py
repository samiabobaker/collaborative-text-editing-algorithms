from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class SOCT4InsertOperation:
    timestamp: int
    client_id: int
    character: UniqueChar
    position: int
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT4DeleteOperation:
    timestamp: int
    client_id: int
    position: int
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT4NoOperation:
    timestamp: int
    client_id: int
    causing_operation: ClientInsertOperation | ClientDeleteOperation


SOCT4Operation = SOCT4DeleteOperation | SOCT4InsertOperation | SOCT4NoOperation


@dataclass
class SOCT4TicketRequestMessage:
    client_id: int
    n: int
    operation: SOCT4Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT4TicketResponseMessage:
    client_id: int
    n: int
    ticket: int
    operation: SOCT4Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT4OperationMessage:
    client_id: int
    operation: SOCT4Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


SOCT4Message = SOCT4TicketRequestMessage | SOCT4TicketResponseMessage | SOCT4OperationMessage
