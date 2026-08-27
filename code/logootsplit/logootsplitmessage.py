from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from logootsplit.logootsplitdocument import LogootSplitId
from unique_char.uniquechar import UniqueChar


@dataclass
class LogootSplitInsertionOperation:
    id: LogootSplitId
    character: UniqueChar


@dataclass
class LogootSplitDeletionOperation:
    id: LogootSplitId


LogootSplitOperation = LogootSplitInsertionOperation | LogootSplitDeletionOperation


@dataclass
class LogootSplitMessage:
    vector_clock: dict[int, int]
    operation: LogootSplitOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
