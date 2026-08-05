from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation
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