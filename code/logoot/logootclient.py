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
from logoot.logootdocument import LogootDocument, LogootPosition
from logoot.logootmessage import (
    LogootDeletionOperation,
    LogootInsertionOperation,
    LogootMessage,
    LogootOperation,
)
from unique_char.uniquechar import UniqueChar


class LogootClient(ClientDevice):
    client_id: int

    document: LogootDocument
    clients: list[LogootClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[LogootMessage]]


    def __init__(self, client_id: int):
        self.document = LogootDocument(client_id)
        self.client_id = client_id


    def set_clients(self, clients: list[LogootClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []


    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        position = self.document.insert_char(operation.character, operation.position)
        #Send message to all other clients
        self.__send_to_other_clients(LogootMessage(self.vector_clock.copy(), LogootInsertionOperation(position, operation.character), operation))

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        position = self.document.delete_char(operation.position)
        #Send message to all other clients
        self.__send_to_other_clients(LogootMessage(self.vector_clock.copy(), LogootDeletionOperation(position), operation))

    def perform_remote_insert(self, position: LogootPosition, character: UniqueChar) -> None:
        #Insert into local tree, at the right index to keep ids in order
        self.document.integrate_insert(position, character)

    def perform_remote_delete(self, position: LogootPosition) -> None:
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

    def __apply_operation(self, operation: LogootOperation):
        match operation:
            case LogootInsertionOperation(position, character):
                self.perform_remote_insert(position, character)
            case LogootDeletionOperation(position):
                self.perform_remote_delete(position)
            case _ as unreachable:
                assert_never(unreachable)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        #Check if message from client exists, and is causally ready.
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
    
    def send_message(self, client_id: int, message: LogootMessage):
        self.message_buffer[client_id].append(message)
    
    def __send_to_other_clients(self, message: LogootMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: LogootMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
