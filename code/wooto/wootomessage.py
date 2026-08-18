from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar
from wooto.wootostring import WOOTOIdentifier


@dataclass
class WOOTOInsertionOperation:
    id: WOOTOIdentifier
    character: UniqueChar
    prev_id: WOOTOIdentifier
    next_id: WOOTOIdentifier
    degree: int


@dataclass
class WOOTODeletionOperation:
    character_id: WOOTOIdentifier


WOOTOOperation = WOOTOInsertionOperation | WOOTODeletionOperation


@dataclass
class WOOTOMessage:
    operation: WOOTOOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
