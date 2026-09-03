from dataclasses import dataclass
from typing import Literal

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class LBTInsertionOperation:
    vector_clock: dict[int, int]
    position: int
    character: UniqueChar
    client_id: int


@dataclass
class LBTDeletionOperation:
    vector_clock: dict[int, int]
    position: int
    client_id: int


LBTOperation = LBTDeletionOperation | LBTInsertionOperation
EffectRelation = Literal["<", ">", "="]


@dataclass
class LBTMessage:
    vector_clock: dict[int, int]
    operation: LBTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
