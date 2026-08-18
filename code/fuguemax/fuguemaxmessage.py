from dataclasses import dataclass
from typing import Literal

from device.operations import ClientDeleteOperation, ClientInsertOperation
from fuguemax.fuguemaxtree import RightOriginId
from unique_char.uniquechar import UniqueChar


@dataclass
class FugueMaxInsertionOperation:
    parent_node_id: int
    node_id: int
    char: UniqueChar
    direction: Literal['left','right']
    right_origin_id: RightOriginId


@dataclass
class FugueMaxDeletionOperation:
    node_id: int

FugueMaxOperation = FugueMaxInsertionOperation | FugueMaxDeletionOperation

@dataclass
class FugueMaxMessage:
    vector_clock: dict[int, int]
    operation: FugueMaxOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

