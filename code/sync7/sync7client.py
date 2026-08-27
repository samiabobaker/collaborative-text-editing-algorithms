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
from sync7.sync7diff import Sync7Text, diff_to_previous_text
from sync7.sync7document import Sync7Document, Sync7Id, copy_versions
from sync7.sync7message import Sync7Message
from unique_char.uniquechar import UniqueChar


class Sync7Client(ClientDevice):
    """Peer to peer Sync7 client.

    An edit is a new version of the whole text rather than an operation, so what a client
    sends is the version it just made together with any merge results it was built on, and
    what it does on receiving is put those into its own version graph and merge whatever
    leaves that leaves it with.

    Nothing here needs messages to arrive in any particular order. A version whose parents
    have not turned up yet is held back inside the document until they do, and every merge
    reconsiders what is being held, so the last message to arrive is what brings everything
    that was waiting on it into the graph.
    """

    client_id: int

    document: Sync7Document
    clients: list[Sync7Client]
    message_buffer: dict[int, list[Sync7Message]]
    causing_operations: dict[Sync7Id, ClientInsertOperation | ClientDeleteOperation]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.document = Sync7Document(client_id)
        self.causing_operations = {}

    def set_clients(self, clients: list[Sync7Client]) -> None:
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        text = (
            self.document.text[: operation.position] + [operation.character] + self.document.text[operation.position :]
        )
        self.__commit(operation, text, [operation.character], [])

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        character = self.document.text[operation.position]
        text = self.document.text[: operation.position] + self.document.text[operation.position + 1 :]
        self.__commit(operation, text, [], [character])

    def __commit(
        self,
        operation: ClientInsertOperation | ClientDeleteOperation,
        text: Sync7Text,
        own: Sync7Text,
        parent: Sync7Text,
    ) -> None:
        identifier = self.document.mint()
        diff = diff_to_previous_text(text, operation.position, own, parent)
        versions = self.document.commit(identifier, text, diff)

        self.causing_operations[identifier] = operation
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, Sync7Message(copy_versions(versions), {identifier: operation}))

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        message = client_message_buffer.pop(0)
        self.causing_operations.update(message.causing_operations)

        known = set(self.document.versions)
        self.document.merge(message.versions)

        # A version whose parents have not all arrived is held back, so what this receive
        # made visible is whatever went into the graph, which can include versions that
        # arrived earlier and were waiting on this one.
        added = sorted(identifier for identifier in self.document.versions if identifier not in known)
        return [self.causing_operations[identifier] for identifier in added if identifier in self.causing_operations]

    def send_message(self, client_id: int, message: Sync7Message) -> None:
        self.message_buffer[client_id].append(message)

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
        return self.document.text

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            if len(self.message_buffer[client.client_id]) != 0:
                client_ids.append(client.client_id)
        return client_ids
