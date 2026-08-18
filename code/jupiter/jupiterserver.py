from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ServerOperation,
    ServerReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
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
    from jupiter.jupiterclient import JupiterClient

class ClientView:
    client_id: int
    client: JupiterClient
    message_buffer: list[JupiterMessage]
    client_message_count: int
    server_message_count: int
    outgoing: list[JupiterMessage]

    def __init__(self, client_id: int, client: JupiterClient):
        self.client_id = client_id
        self.client = client
        self.message_buffer = []
        self.client_message_count = 0
        self.server_message_count = 0
        self.outgoing = []
    

class JupiterServer(ServerDevice):
    clients: dict[int, ClientView]
    
    state: list[UniqueChar]

    def __init__(self, clients: list[JupiterClient]):
        self.clients = {}
        self.state = []
        for client in clients:
            client_view = ClientView(client.client_id, client)
            self.clients[client.client_id] = client_view

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

    def __send_operation_to_other_clients(self, client_view_from: ClientView, operation: JupiterOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation):
        for client_id in self.clients:
            if client_id == client_view_from.client_id:
                continue
            
            client_view = self.clients[client_id]

            message = JupiterMessage(client_view.client_message_count, client_view.server_message_count, operation, causing_operation)
            client_view.client.send_message(message)
            client_view.outgoing.append(message)
            client_view.server_message_count += 1

    def __apply_message(self, client_view: ClientView, received_message: JupiterMessage) -> None:
        client_view.outgoing = [m for m in client_view.outgoing if m.server_message_count >= received_message.server_message_count]

        transformed_operation = received_message.operation

        for index, message in enumerate(client_view.outgoing):
            transformed_operation, transformed_outgoing_operation = JupiterTransform.transform_jupiter_operation(transformed_operation, message.operation)
            client_view.outgoing[index] = JupiterMessage(message.client_message_count, message.server_message_count, transformed_outgoing_operation, message.causing_operation)
        
        self.__apply_operation(transformed_operation)
        self.__send_operation_to_other_clients(client_view, transformed_operation, received_message.causing_operation)

        client_view.client_message_count += 1

    def send_message(self, client_id: int, message: JupiterMessage) -> None:
        self.clients[client_id].message_buffer.append(message)

    def receive_message(self, client_id: int) -> None:
        if client_id not in self.clients or len(self.clients[client_id].message_buffer) == 0:
            return

        client_view = self.clients[client_id]
        message = client_view.message_buffer.pop(0)

        self.__apply_message(client_view, message)

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.state
    
    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.clients:
            if len(self.clients[client_id].message_buffer) != 0:
                client_ids.append(client_id)
        return client_ids




