from abc import ABC, abstractmethod

from device.operations import ServerOperation


class ServerDevice(ABC):

    #Performs the operation
    @abstractmethod
    def perform_operation(self, operation: ServerOperation) -> None:
        pass

    #Returns the current state of the server
    #@abstractmethod
    #def read_state(self) -> list[UniqueChar]:
    #    pass

    #Returns a list id of client_ids that the server has messages from, but not yet received
    @abstractmethod
    def can_receive_from(self) -> list[int]:
        pass