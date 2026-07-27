from device.operations import ClientOperation, ClientInsertOperation, ClientDeleteOperation
from abc import ABC, abstractmethod
from unique_char.uniquechar import UniqueChar

class ClientDevice(ABC):

    client_id: int

    @abstractmethod
    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        pass

    @abstractmethod
    def read_state(self) -> list[UniqueChar]:
        pass

    #Returns whether client has a message to receive from server. Should always return false if algorithm is not client-server.
    @abstractmethod
    def can_receive_from_server(self) -> bool:
        pass

    #Returns list of clients, that this device can receive from. Can return empty list for client-server algorithms.
    @abstractmethod
    def can_receive_from(self) -> list[int]:
        pass

