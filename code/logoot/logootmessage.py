from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from logoot.logootdocument import LogootPosition
from unique_char.uniquechar import UniqueChar


@dataclass
class LogootInsertionOperation:
    position: LogootPosition
    character: UniqueChar

@dataclass
class LogootDeletionOperation:
    position: LogootPosition

LogootOperation = LogootInsertionOperation | LogootDeletionOperation

@dataclass
class LogootMessage:
    vector_clock: dict[int, int]
    operation: LogootOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
