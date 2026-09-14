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
from treedoc.treedocmessage import (
    TreedocDeletionOperation,
    TreedocInsertionOperation,
    TreedocMessage,
    TreedocOperation,
)
from treedoc.treedoctree import TreedocPosID, TreedocTree
from unique_char.uniquechar import UniqueChar


# Treedoc is a CRDT: concurrent operations commute, so a replica only has to replay every
# operation it receives, in happened-before order (section 2.2). That order is what the
# vector clock below enforces; nothing else is needed to converge.
class TreedocClient(ClientDevice):
    client_id: int

    tree: TreedocTree
    clients: list[TreedocClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[TreedocMessage]]

    def __init__(self, client_id: int):
        self.client_id = client_id
        # The site identifier is used as the disambiguator of every mini-node this
        # replica creates (SDIS, section 3.3.2).
        self.tree = TreedocTree(client_id)

    def set_clients(self, clients: list[TreedocClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Allocate a fresh PosID for the new atom, and insert it into the local tree.
        node = self.tree.insert_char(operation.position, operation.character)
        # Send message to all other clients
        self.__send_to_other_clients(
            TreedocMessage(self.vector_clock.copy(), TreedocInsertionOperation(node.pos_id, node.value), operation)
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local tree
        node = self.tree.delete_char(operation.position)
        # Send message to all other clients
        self.__send_to_other_clients(
            TreedocMessage(self.vector_clock.copy(), TreedocDeletionOperation(node.pos_id), operation)
        )

    def perform_remote_insert(self, pos_id: TreedocPosID, char: UniqueChar) -> None:
        self.tree.insert_char_at_pos_id(pos_id, char)

    def perform_remote_delete(self, pos_id: TreedocPosID) -> None:
        self.tree.delete_node_with_pos_id(pos_id)

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
        return self.tree.traverse()

    def read_state_with_tombstones(self) -> list[UniqueChar]:
        return self.tree.traverse_with_tombstones()

    def __apply_operation(self, operation: TreedocOperation) -> None:
        match operation:
            case TreedocInsertionOperation(pos_id, char):
                self.perform_remote_insert(pos_id, char)
            case TreedocDeletionOperation(pos_id):
                self.perform_remote_delete(pos_id)
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

    def send_message(self, client_id: int, message: TreedocMessage) -> None:
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: TreedocMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: TreedocMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
