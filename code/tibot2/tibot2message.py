from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class TIBOT2InsertionOperation:
    position: int
    character: UniqueChar


@dataclass
class TIBOT2DeletionOperation:
    position: int
    character: UniqueChar


class TIBOT2NoOperation:
    pass


@dataclass
class TIBOT2Operation:
    time_interval: int
    client_id: int
    sequence_number: int  # To tie break operations from the same time_interval and client_id
    operation: TIBOT2InsertionOperation | TIBOT2DeletionOperation | TIBOT2NoOperation


# Operations in the same time interval from the same client are treated as one group operation
# Synchronization rule 3.
@dataclass
class TIBOT2Message:
    client_id: int
    time_interval: int
    group_operation: list[
        TIBOT2Operation
    ]  # I will use the group operation being the empty list as an announcement of the end of a time interval
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]
