from dataclasses import dataclass
from unique_char.uniquechar import UniqueChar

@dataclass
class ClientInsertOperation:
    client_id: int
    position: int
    character: UniqueChar

@dataclass
class ClientDeleteOperation:
    client_id: int
    position: int
    character: UniqueChar #Store what character got deleted for convenience.

@dataclass
class ClientReceiveFromServerOperation:
    client_id: int

@dataclass
class ClientReceiveFromClientOperation:
    client_id: int
    sender_client_id: int

#Only relevant to algorithms that need some clock.
@dataclass
class ClientTimestepOperation:
    client_id: int


@dataclass
class ServerReceiveFromClientOperation:
    client_id: int

ClientOperation = ClientInsertOperation | ClientDeleteOperation | ClientReceiveFromServerOperation | ClientReceiveFromClientOperation | ClientTimestepOperation
ServerOperation = ServerReceiveFromClientOperation