from dataclasses import dataclass
from fractions import Fraction

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class PPSInsertionOperation:
    position_stamp: Fraction
    char: UniqueChar


@dataclass
class PPSDeletionOperation:
    position_stamp: Fraction


PPSOperation = PPSInsertionOperation | PPSDeletionOperation


@dataclass
class PPSMessage:
    vector_clock: dict[int, int]
    operation: PPSOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
