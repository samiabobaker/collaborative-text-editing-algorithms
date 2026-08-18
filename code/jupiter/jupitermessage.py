from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


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

