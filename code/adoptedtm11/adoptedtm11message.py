from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class AdOPTedTM11InsertionOperation:
    position: int
    string: list[UniqueChar]
    priority: int

@dataclass
class AdOPTedTM11DeletionOperation:
    position: int
    length: int
    priority: int

class AdOPTedTM11NoOperation:
    pass


AdOPTedTM11Operation = AdOPTedTM11InsertionOperation | AdOPTedTM11DeletionOperation | AdOPTedTM11NoOperation

@dataclass
class AdOPTedTM11Message:
    client_id: int
    vector_clock: dict[int, int]
    operation: AdOPTedTM11Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation #The client operation that triggered this message to be sent.

