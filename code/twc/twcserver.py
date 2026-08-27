from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from device.operations import (
    ServerOperation,
    ServerReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
from twc.twcidlist import TWCIdList
from twc.twcmessage import (
    TWCCommittedMessage,
    TWCDeletionOperation,
    TWCInsertionOperation,
    TWCMessage,
)
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from twc.twcclient import TWCClient


class TWCClientView:
    """Server-side bookkeeping for one client.

    A FIFO inbox of the updates that client has sent and not yet had committed.
    """

    client_id: int
    client: TWCClient
    message_buffer: list[TWCMessage]

    def __init__(self, client_id: int, client: TWCClient):
        self.client_id = client_id
        self.client = client
        self.message_buffer = []


class TWCServer(ServerDevice):
    """Puts every update into a total order and broadcasts it to all clients.

    The order is the order the server took the updates off the client inboxes, and
    every client applies them in that order, so no transforms are needed anywhere.
    """

    clients: dict[int, TWCClientView]
    state: TWCIdList
    next_server_version: int

    def __init__(self, clients: list[TWCClient]):
        self.clients = {}
        self.state = TWCIdList()
        self.next_server_version = 0
        for client in clients:
            self.clients[client.client_id] = TWCClientView(client.client_id, client)

    def send_message(self, client_id: int, message: TWCMessage) -> None:
        self.clients[client_id].message_buffer.append(message)

    def receive_message(self, client_id: int) -> None:
        if client_id not in self.clients or len(self.clients[client_id].message_buffer) == 0:
            return

        client_view = self.clients[client_id]
        message = client_view.message_buffer.pop(0)

        match message.operation:
            case TWCInsertionOperation(_, before_id, element_id, character):
                self.state.insert_after(before_id, element_id, character)
            case TWCDeletionOperation(_, element_id):
                self.state.delete(element_id)
            case _ as unreachable:
                assert_never(unreachable)

        # Commit: assign server_version in receipt order and broadcast to
        # every client (echoes included).
        committed = TWCCommittedMessage(
            self.next_server_version,
            message.operation,
            message.causing_operation,
        )
        self.next_server_version += 1
        for other_view in self.clients.values():
            other_view.client.send_message(committed)

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.state.present_chars()

    def can_receive_from(self) -> list[int]:
        return [client_id for client_id, view in self.clients.items() if len(view.message_buffer) != 0]
