from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation

@dataclass
class JupiterInsertionOperation:
    position: int
    character: UniqueChar

@dataclass
class JupiterDeletionOperation:
    position: int

class JupiterNoOperation:
    pass


JupiterOperation = JupiterInsertionOperation | JupiterDeletionOperation | JupiterNoOperation

@dataclass
class JupiterMessage:
    client_message_count: int
    server_message_count: int
    operation: JupiterOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation #The client operation that triggered this message to be sent.

