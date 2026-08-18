from __future__ import annotations

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
from sync9.sync9document import Sync9Document, Sync9Id, Sync9Item
from sync9.sync9message import (
    Sync9DeletionOperation,
    Sync9InsertionOperation,
    Sync9Message,
    Sync9Operation,
)
from unique_char.uniquechar import UniqueChar


class Sync9Client(ClientDevice):
    """Peer to peer Sync9 client.

    Every client holds a full copy of the document and broadcasts each local
    operation to all the others. Messages carry a vector clock so that they are
    only applied once everything they depend on has arrived; that also
    guarantees an insertion's anchor is already present when it is integrated,
    since the sender had it in its own document beforehand.
    """

    client_id: int

    document: Sync9Document
    clients: list[Sync9Client]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[Sync9Message]]

    __next_seq: int

    def __init__(self, client_id: int):
        self.document = Sync9Document()
        self.client_id = client_id
        self.__next_seq = 0

    def set_clients(self, clients: list[Sync9Client]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Perform change to local document
        id = Sync9Id(self.client_id, self.__next_seq)
        self.__next_seq += 1
        item = self.document.insert_char(operation.position, id, operation.character)
        # Send message to all other clients
        self.__send_to_other_clients(
            Sync9Message(
                self.vector_clock.copy(),
                Sync9InsertionOperation(item.id, item.origin_left, item.insert_after, item.value),
                operation,
            )
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local document
        item = self.document.delete_char(operation.position)
        # Send message to all other clients
        self.__send_to_other_clients(Sync9Message(self.vector_clock.copy(), Sync9DeletionOperation(item.id), operation))

    def perform_remote_insert(
        self,
        id: Sync9Id,
        origin_left: Sync9Id | None,
        insert_after: bool,
        char: UniqueChar,
    ) -> None:
        self.document.integrate(Sync9Item(id, origin_left, insert_after, char))

    def perform_remote_delete(self, id: Sync9Id) -> None:
        self.document.delete_item_with_id(id)

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
        return self.document.traverse()

    def read_state_with_tombstones(self) -> list[UniqueChar]:
        return self.document.traverse_with_tombstones()

    def __apply_operation(self, operation: Sync9Operation):
        match operation:
            case Sync9InsertionOperation(id, origin_left, insert_after, char):
                self.perform_remote_insert(id, origin_left, insert_after, char)
            case Sync9DeletionOperation(id):
                self.perform_remote_delete(id)
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

    def send_message(self, client_id: int, message: Sync9Message):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: Sync9Message) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: Sync9Message) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
