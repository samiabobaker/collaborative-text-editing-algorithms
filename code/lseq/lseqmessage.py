from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from lseq.lseqdocument import LSEQPosition
from unique_char.uniquechar import UniqueChar


@dataclass
class LSEQInsertionOperation:
    position: LSEQPosition
    character: UniqueChar


@dataclass
class LSEQDeletionOperation:
    position: LSEQPosition


LSEQOperation = LSEQInsertionOperation | LSEQDeletionOperation


@dataclass
class LSEQMessage:
    vector_clock: dict[int, int]
    operation: LSEQOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
