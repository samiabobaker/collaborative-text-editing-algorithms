from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class COTMessage:
    client_id: int
    timestamp: int | None
    operation: COTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


@dataclass
class COTInsertOperation:
    position: int
    character: UniqueChar


@dataclass
class COTDeleteOperation:
    position: int


@dataclass
class COTNoOperation:
    pass


@dataclass
class COTOperation:
    client_id: int
    context_vector: dict[int, int]
    timestamp: int | None
    operation: COTInsertOperation | COTDeleteOperation | COTNoOperation
