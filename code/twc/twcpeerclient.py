from __future__ import annotations

from dataclasses import dataclass
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
from twc.twcclient import allocate_element_id, allocate_update_id
from twc.twcidlist import TWCIdList
from twc.twcmessage import TWCDeletionOperation, TWCInsertionOperation, TWCOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class TWCPeerMessage:
    timestamp: tuple[int, int]  # Lamport counter, then client id
    vector_clock: dict[int, int]
    operation: TWCOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


class TWCPeerClient(ClientDevice):
    """The blog's decentralized variant, replaying edits in Lamport timestamp order.

    https://mattweidner.com/2025/05/21/text-without-crdts.html#decentralized-variants

    Causal delivery makes every insertion's anchor and deletion's target available
    before replay. Concurrent edits can arrive in either order. When one sorts before
    an edit already applied, rebuilding the list gives the new authoritative state.
    """

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.clock = 0  # Counts insertions and deletions.
        self.state = TWCIdList()
        self.operations: dict[tuple[int, int], TWCPeerMessage] = {}
        self.clients: list[TWCPeerClient] = []
        self.vector_clock: dict[int, int] = {}
        self.message_buffer: dict[int, list[TWCPeerMessage]] = {}

    def set_clients(self, clients: list[TWCPeerClient]) -> None:
        self.clients = clients
        self.vector_clock = {client.client_id: 0 for client in clients}
        self.message_buffer = {client.client_id: [] for client in clients}

    def __replay(self) -> None:
        self.state = TWCIdList()
        for timestamp in sorted(self.operations):
            match self.operations[timestamp].operation:
                case TWCInsertionOperation(_, before_id, element_id, character):
                    self.state.insert_after(before_id, element_id, character)
                case TWCDeletionOperation(_, element_id):
                    self.state.delete(element_id)
                case _ as unreachable:
                    assert_never(unreachable)

    def __local_update(
        self, update: TWCOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        self.clock += 1
        message = TWCPeerMessage((self.clock, self.client_id), self.vector_clock.copy(), update, causing_operation)
        self.operations[message.timestamp] = message
        self.vector_clock[self.client_id] += 1
        self.__replay()
        for client in self.clients:
            if client.client_id != self.client_id:
                client.send_message(self.client_id, message)

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        before_id = self.state.at_present(operation.position - 1) if operation.position else None
        # As in TWCClient, the allocator supplies opaque unique IDs. Only Lamport
        # timestamps determine replay order.
        update = TWCInsertionOperation(allocate_update_id(), before_id, allocate_element_id(), operation.character)
        self.__local_update(update, operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        update = TWCDeletionOperation(allocate_update_id(), self.state.at_present(operation.position))
        self.__local_update(update, operation)

    def __is_causally_ready(self, message: TWCPeerMessage) -> bool:
        return all(count <= self.vector_clock[client_id] for client_id, count in message.vector_clock.items())

    def send_message(self, client_id: int, message: TWCPeerMessage) -> None:
        self.message_buffer[client_id].append(message)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        inbox = self.message_buffer[client_id]
        if not inbox or not self.__is_causally_ready(inbox[0]):
            return []
        message = inbox.pop(0)
        self.clock = max(self.clock, message.timestamp[0])
        self.operations[message.timestamp] = message
        self.vector_clock[client_id] += 1
        self.__replay()
        return [message.causing_operation]

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromClientOperation(_, sender_client_id):
                return self.receive_from_client(sender_client_id)
            case ClientReceiveFromServerOperation() | ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.state.present_chars()

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        return [
            client_id
            for client_id, inbox in self.message_buffer.items()
            if inbox and self.__is_causally_ready(inbox[0])
        ]
