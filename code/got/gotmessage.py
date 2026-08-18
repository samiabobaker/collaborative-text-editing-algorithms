from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from got.operations.operation import GOTOperation


@dataclass
class GOTMessage:
    operation: GOTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation