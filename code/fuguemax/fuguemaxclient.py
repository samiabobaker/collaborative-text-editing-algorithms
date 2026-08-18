from typing import Literal, assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from fuguemax.fuguemaxmessage import (
    FugueMaxDeletionOperation,
    FugueMaxInsertionOperation,
    FugueMaxMessage,
    FugueMaxOperation,
)
from fuguemax.fuguemaxtree import FugueMaxTree, RightOriginId
from unique_char.uniquechar import UniqueChar


class FugueMaxClient(ClientDevice):
    client_id: int

    tree: FugueMaxTree
    clients: list[FugueMaxClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[FugueMaxMessage]]

    def __init__(self, client_id: int):
        self.tree = FugueMaxTree()
        self.client_id = client_id

    def set_clients(self, clients: list[FugueMaxClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Perform change to local tree
        node = self.tree.insert_char(operation.position, operation.character)
        # Send message to all other clients
        self.__send_to_other_clients(
            FugueMaxMessage(
                self.vector_clock.copy(),
                FugueMaxInsertionOperation(
                    node.parent_node_id, node.node_id, node.value, node.direction, node.right_origin_id
                ),
                operation,
            )
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local tree
        node = self.tree.delete_char(operation.position)
        # Send message to all other clients
        self.__send_to_other_clients(
            FugueMaxMessage(self.vector_clock.copy(), FugueMaxDeletionOperation(node.node_id), operation)
        )

    def perform_remote_insert(
        self,
        parent_node_id: int,
        node_id: int,
        char: UniqueChar,
        direction: Literal["left", "right"],
        right_origin_id: RightOriginId,
    ) -> None:
        # Insert into local tree, at the right index to keep ids in order
        self.tree.insert_char_at_node(parent_node_id, node_id, char, direction, right_origin_id)

    def perform_remote_delete(self, id: int) -> None:
        self.tree.delete_node_with_id(id)

    def read_state_with_tombstones(self) -> list[UniqueChar]:
        return self.tree.traverse_with_tombstones()

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

    def read_right_origins(self) -> list[tuple[UniqueChar, UniqueChar | Literal["end"]]]:
        return self.tree.traverse_with_right_origins()

    def __apply_operation(self, operation: FugueMaxOperation):
        match operation:
            case FugueMaxInsertionOperation(parent_node_id, node_id, char, direction, right_origin_id):
                self.perform_remote_insert(parent_node_id, node_id, char, direction, right_origin_id)
            case FugueMaxDeletionOperation(node_id):
                self.perform_remote_delete(node_id)
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

    def send_message(self, client_id: int, message: FugueMaxMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: FugueMaxMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: FugueMaxMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
