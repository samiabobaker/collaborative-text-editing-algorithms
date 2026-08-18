from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class SOCT3InsertOperation:
    vector_clock: dict[int, int]
    timestamp: int
    client_id: int
    character: UniqueChar
    position: int
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT3DeleteOperation:
    vector_clock: dict[int, int]
    timestamp: int
    client_id: int
    position: int
    causing_operation: ClientInsertOperation | ClientDeleteOperation


SOCT3Operation = SOCT3DeleteOperation | SOCT3InsertOperation


@dataclass
class SOCT3TicketRequestMessage:
    client_id: int
    n: int
    operation: SOCT3Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT3TicketResponseMessage:
    client_id: int
    n: int
    ticket: int
    operation: SOCT3Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class SOCT3OperationMessage:
    client_id: int
    operation: SOCT3Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


SOCT3Message = SOCT3TicketRequestMessage | SOCT3TicketResponseMessage | SOCT3OperationMessage
