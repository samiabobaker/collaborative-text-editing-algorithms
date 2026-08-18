from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class TIBOTInsertionOperation:
    position: int
    character: UniqueChar

@dataclass
class TIBOTDeletionOperation:
    position: int
    character: UniqueChar

class TIBOTNoOperation:
    pass

@dataclass
class TIBOTOperation:
    time_interval: int
    client_id: int
    sequence_number: int #To tie break operations from the same time_interval and client_id
    operation: TIBOTInsertionOperation | TIBOTDeletionOperation | TIBOTNoOperation

#Operations in the same time interval from the same client are treated as one group operation
#Synchronization rule 3.
@dataclass
class TIBOTMessage:
    client_id: int
    time_interval: int
    group_operation: list[TIBOTOperation] #I will use the group operation being the empty list as an announcement of the end of a time interval
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]