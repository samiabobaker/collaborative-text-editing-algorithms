from __future__ import annotations

from typing import assert_never

from automerge.automergedocument import AutomergeDocument
from automerge.automergemessage import (
    HEAD,
    AutomergeChange,
    AutomergeChangeOp,
    OpId,
)
from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from unique_char.uniquechar import UniqueChar

# Stand in for the op id of a local change before build_local_change stamps the real one.
PLACEHOLDER_ID: OpId = (0, 0)


class AutomergeClient(ClientDevice):
    """Peer to peer Automerge client.

    Every client holds the full op columns and change graph and broadcasts each local
    change to all the others. A change names its dependencies by hash rather than by a
    vector clock, so `can_receive_from` reports a peer once the next change in its
    buffer has all of its deps applied, which is what keeps an insertion's anchor
    present when it is integrated.

    Automerge moves changes between peers over a sync protocol that negotiates what
    each side is missing. That is a transport, and every other client here models
    transport as an idealised broadcast, so it is left out and the change graph
    underneath it kept.
    """

    client_id: int

    document: AutomergeDocument
    clients: list[AutomergeClient]
    message_buffer: dict[int, list[AutomergeChange]]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.document = AutomergeDocument(client_id)
        self.clients = []
        self.message_buffer = {}

    def set_clients(self, clients: list[AutomergeClient]) -> None:
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            # Registering every peer up front makes the actor table the same everywhere,
            # so an actor index is a client id (automerge.rs put_actor_ref).
            self.document.register_actor(client.client_id)
            if client.client_id != self.client_id:
                self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Perform change to local document (transaction/inner.rs do_insert with
        # InsertQuery): the predecessor is the last visible element before the position.
        key: OpId = self.document.visible_op(operation.position - 1).id if operation.position > 0 else HEAD
        # The id is a placeholder: build_local_change assigns the real one, max_op + 1
        # for this actor, as automerge.rs transaction_args does.
        change = self.document.build_local_change(
            AutomergeChangeOp(PLACEHOLDER_ID, key, True, "set", operation.character, ()), operation
        )
        self.document.integrate_insert(key, change.ops[0].id, operation.character)
        self.document.record_change(change)
        # Send message to all other clients
        self.__send_to_other_clients(change)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local document (transaction/inner.rs inner_splice with
        # next_delete): a delete only adds a succ pointer to the target element.
        target = self.document.visible_op(operation.position)
        change = self.document.build_local_change(
            AutomergeChangeOp(PLACEHOLDER_ID, target.id, False, "del", None, (target.id,)), operation
        )
        self.document.add_succ(target, change.ops[0].id)
        self.document.record_change(change)
        # Send message to all other clients
        self.__send_to_other_clients(change)

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

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        return self.document.apply_change(client_message_buffer.pop(0))

    def can_receive_from(self) -> list[int]:
        return sorted(
            client_id
            for client_id, buffer in self.message_buffer.items()
            if len(buffer) != 0 and self.document.is_causally_ready(buffer[0])
        )

    def can_receive_from_server(self) -> bool:
        return False

    def send_message(self, client_id: int, change: AutomergeChange) -> None:
        self.message_buffer[client_id].append(change)

    def __send_to_other_clients(self, change: AutomergeChange) -> None:
        for client in self.clients:
            if client.client_id != self.client_id:
                client.send_message(self.client_id, change)
