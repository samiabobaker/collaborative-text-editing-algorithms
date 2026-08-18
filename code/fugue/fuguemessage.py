from dataclasses import dataclass
from typing import Literal

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


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

