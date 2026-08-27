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
from loro.lorodocument import LoroDocument, LoroId
from loro.loromessage import (
    LoroDeleteOperation,
    LoroInsertOperation,
    LoroMessage,
    LoroOperation,
)
from unique_char.uniquechar import UniqueChar


class LoroClient(ClientDevice):
    """Peer to peer Loro client.

    Every client holds a full copy of the rope and broadcasts each local
    operation to all the others. Messages carry a vector clock so that they
    are only applied once everything they depend on has arrived, which is
    where Loro differs from the other peer to peer algorithms here: the clock
    is not only a delivery guard but the version the rope is checked out to
    before the operation is integrated. Loro's operations carry a plain
    visible index and no origins, so that checkout is what makes the index
    mean the same thing on the receiver as it did on the sender.

    Every operation, insert or delete, takes one id from this client's own
    counter, as in Loro where all operations draw from a single per peer
    counter (op/content.rs `RawOp`).
    """

    client_id: int

    document: LoroDocument
    clients: list[LoroClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[LoroMessage]]

    __next_counter: int

    def __init__(self, client_id: int):
        self.document = LoroDocument()
        self.client_id = client_id
        self.__next_counter = 0

    def set_clients(self, clients: list[LoroClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Perform change to local document
        op_id = self.__next_id()
        self.document.insert_char(op_id, operation.position, operation.character)
        # Send message to all other clients
        self.__send_to_other_clients(
            LoroMessage(
                self.vector_clock.copy(),
                LoroInsertOperation(op_id, operation.position, operation.character),
                operation,
            )
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local document
        op_id = self.__next_id()
        item = self.document.delete_char(op_id, operation.position)
        if item.char != operation.character:
            raise ValueError("Delete removed a different character")
        # Send message to all other clients
        self.__send_to_other_clients(
            LoroMessage(
                self.vector_clock.copy(),
                LoroDeleteOperation(op_id, item.op_id, operation.position),
                operation,
            )
        )

    def perform_remote_insert(self, version: dict[int, int], op_id: LoroId, pos: int, char: UniqueChar) -> None:
        self.document.integrate_insert(version, op_id, pos, char)

    def perform_remote_delete(self, version: dict[int, int], op_id: LoroId, target_id: LoroId, pos: int) -> None:
        self.document.integrate_delete(version, op_id, target_id, pos)

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

    def read_origins(self) -> list[tuple[UniqueChar, LoroId | None, LoroId | None]]:
        return self.document.origins()

    def __apply_operation(self, version: dict[int, int], operation: LoroOperation):
        match operation:
            case LoroInsertOperation(op_id, pos, char):
                self.perform_remote_insert(version, op_id, pos, char)
            case LoroDeleteOperation(op_id, target_id, pos):
                self.perform_remote_delete(version, op_id, target_id, pos)
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

        self.__apply_operation(message.vector_clock, message.operation)

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

    def send_message(self, client_id: int, message: LoroMessage):
        self.message_buffer[client_id].append(message)

    def __next_id(self) -> LoroId:
        op_id = LoroId(self.client_id, self.__next_counter)
        self.__next_counter += 1
        return op_id

    def __send_to_other_clients(self, message: LoroMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: LoroMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
