from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation
from typing import Literal
from got.operations.operation import GOTOperation

@dataclass
class GOTMessage:
    operation: GOTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation