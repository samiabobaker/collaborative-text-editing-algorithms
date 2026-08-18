from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from jupiter.jupitermessage import (
    JupiterDeletionOperation,
    JupiterInsertionOperation,
    JupiterMessage,
    JupiterNoOperation,
    JupiterOperation,
)
from jupiter.jupitertransform import JupiterTransform
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from jupiter.jupiterserver import JupiterServer

class JupiterClient(ClientDevice):
    client_id: int

    message_buffer: list[JupiterMessage]
    jupiter_server: JupiterServer

    client_message_count: int
    server_message_count: int

    outgoing: list[JupiterMessage]

    state: list[UniqueChar]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.message_buffer = []
        self.client_message_count = 0
        self.server_message_count = 0
        self.outgoing = []
        self.state = []
    
    def set_server(self, server: JupiterServer) -> None:
        self.jupiter_server = server

    def __insert_character(self, position: int, character: UniqueChar) -> None:
        self.state = self.state[:position] + [character] + self.state[position:]

    def __delete_character(self, position:int) -> None:
        del self.state[position]

    def __apply_operation(self, operation: JupiterOperation) -> None:
        match operation:
            case JupiterInsertionOperation(position, character):
                self.__insert_character(position, character)
            case JupiterDeletionOperation(position):
                self.__delete_character(position)
            case JupiterNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def __perform_local_operation(self, operation: JupiterOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation) -> None:
        self.__apply_operation(operation)

        message = JupiterMessage(self.client_message_count, self.server_message_count, operation, causing_operation)

        self.jupiter_server.send_message(self.client_id, message)
        self.outgoing.append(message)
        self.client_message_count += 1


    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.__perform_local_operation(JupiterInsertionOperation(operation.position, operation.character), operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.__perform_local_operation(JupiterDeletionOperation(operation.position), operation)

    def receive_message(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if len(self.message_buffer) == 0:
            return []
        
        received_message = self.message_buffer.pop(0)

        self.outgoing = [m for m in self.outgoing if m.client_message_count >= received_message.client_message_count]

        transformed_operation = received_message.operation

        for index, message in enumerate(self.outgoing):
            transformed_outgoing_operation, transformed_operation = JupiterTransform.transform_jupiter_operation(message.operation, transformed_operation)
            self.outgoing[index] = JupiterMessage(message.client_message_count, message.server_message_count, transformed_outgoing_operation, message.causing_operation)
        
        self.__apply_operation(transformed_operation)
        self.server_message_count += 1

        return [received_message.causing_operation]

    def send_message(self, message: JupiterMessage) -> None:
        self.message_buffer.append(message)

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation(_):
                return self.receive_message()
            case ClientReceiveFromClientOperation(_,_):
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.state
    
    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0
    
    def can_receive_from(self) -> list[int]:
        return []