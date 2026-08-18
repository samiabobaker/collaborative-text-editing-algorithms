from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar
from woot.wootstring import WOOTIdentifier


@dataclass
class WOOTInsertionOperation:
    id: WOOTIdentifier
    character: UniqueChar
    prev_id: WOOTIdentifier
    next_id: WOOTIdentifier


@dataclass
class WOOTDeletionOperation:
    character_id: WOOTIdentifier

WOOTOperation = WOOTInsertionOperation | WOOTDeletionOperation

@dataclass
class WOOTMessage:
    operation: WOOTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation