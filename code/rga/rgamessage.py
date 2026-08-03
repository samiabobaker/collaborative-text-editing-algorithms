from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation
from rga.rgatree import RGATimestamp

@dataclass
class RGAInsertionOperation:
    timestamp : RGATimestamp
    parent : RGATimestamp | None
    char : UniqueChar


@dataclass
class RGADeletionOperation:
    timestamp : RGATimestamp

RGAOperation = RGAInsertionOperation | RGADeletionOperation

@dataclass
class RGAMessage:
    vector_clock: dict[int, int]
    operation: RGAOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

