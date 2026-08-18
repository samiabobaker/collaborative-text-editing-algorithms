from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from sync9.sync9document import Sync9Id
from unique_char.uniquechar import UniqueChar


@dataclass
class Sync9InsertionOperation:
    id: Sync9Id
    origin_left: Sync9Id | None
    insert_after: bool
    char: UniqueChar


@dataclass
class Sync9DeletionOperation:
    id: Sync9Id


Sync9Operation = Sync9InsertionOperation | Sync9DeletionOperation


@dataclass
class Sync9Message:
    vector_clock: dict[int, int]
    operation: Sync9Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
