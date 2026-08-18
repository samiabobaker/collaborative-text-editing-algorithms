from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from gottombstone.operations.operation import GOTTombstoneOperation


@dataclass
class GOTTombstoneMessage:
    operation: GOTTombstoneOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation