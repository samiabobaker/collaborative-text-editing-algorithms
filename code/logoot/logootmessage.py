from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation
from logoot.logootdocument import LogootPosition

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
