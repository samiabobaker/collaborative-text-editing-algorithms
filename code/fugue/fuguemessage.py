from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation
from typing import Literal

@dataclass
class FugueInsertionOperation:
    parent_node_id: int
    node_id: int
    char: UniqueChar
    direction: Literal['left','right']


@dataclass
class FugueDeletionOperation:
    node_id: int

FugueOperation = FugueInsertionOperation | FugueDeletionOperation

@dataclass
class FugueMessage:
    vector_clock: dict[int, int]
    operation: FugueOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

