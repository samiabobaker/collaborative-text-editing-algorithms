from typing import assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from lseq.lseqdocument import LSEQDocument, LSEQPosition
from lseq.lseqmessage import LSEQDeletionOperation, LSEQInsertionOperation, LSEQMessage, LSEQOperation
from unique_char.uniquechar import UniqueChar


class LSEQClient(ClientDevice):
    client_id: int

    document: LSEQDocument
    clients: list[LSEQClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[LSEQMessage]]

    def __init__(self, client_id: int):
        self.document = LSEQDocument(client_id)
        self.client_id = client_id

    def set_clients(self, clients: list[LSEQClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        position = self.document.insert_char(operation.character, operation.position)
        # Send message to all other clients
        self.__send_to_other_clients(
            LSEQMessage(self.vector_clock.copy(), LSEQInsertionOperation(position, operation.character), operation)
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        position = self.document.delete_char(operation.position)
        # Send message to all other clients
        self.__send_to_other_clients(LSEQMessage(self.vector_clock.copy(), LSEQDeletionOperation(position), operation))

    def perform_remote_insert(self, position: LSEQPosition, character: UniqueChar) -> None:
        # Insert into local tree, at the right index to keep ids in order
        self.document.integrate_insert(position, character)

    def perform_remote_delete(self, position: LSEQPosition) -> None:
        self.document.integrate_delete(position)

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation():
                return []
            case ClientReceiveFromClientOperation(_, sender_client_id):
                return self.receive_from_client(sender_client_id)
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.document.read_state()

    def __apply_operation(self, operation: LSEQOperation):
        match operation:
            case LSEQInsertionOperation(position, character):
                self.perform_remote_insert(position, character)
            case LSEQDeletionOperation(position):
                self.perform_remote_delete(position)
            case _ as unreachable:
                assert_never(unreachable)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        self.__apply_operation(message.operation)

        self.vector_clock[client_id] += 1

        return [message.causing_operation]

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def can_receive_from_server(self) -> bool:
        return False

    def send_message(self, client_id: int, message: LSEQMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: LSEQMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: LSEQMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
