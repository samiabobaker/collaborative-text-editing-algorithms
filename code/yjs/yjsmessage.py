from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientInsertOperation, ClientDeleteOperation
from unique_char.uniquechar import UniqueChar
from yjs.yjsdocument import YjsId


@dataclass
class YjsInsertionOperation:
    id: YjsId
    origin_left: YjsId | None
    origin_right: YjsId | None
    char: UniqueChar


@dataclass
class YjsDeletionOperation:
    id: YjsId


YjsOperation = YjsInsertionOperation | YjsDeletionOperation


@dataclass
class YjsMessage:
    vector_clock: dict[int, int]
    operation: YjsOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
