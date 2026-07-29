from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientInsertOperation, ClientDeleteOperation
from unique_char.uniquechar import UniqueChar
from yjsmod.yjsmoddocument import YjsModId


@dataclass
class YjsModInsertionOperation:
    id: YjsModId
    origin_left: YjsModId | None
    origin_right: YjsModId | None
    char: UniqueChar


@dataclass
class YjsModDeletionOperation:
    id: YjsModId


YjsModOperation = YjsModInsertionOperation | YjsModDeletionOperation


@dataclass
class YjsModMessage:
    vector_clock: dict[int, int]
    operation: YjsModOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
