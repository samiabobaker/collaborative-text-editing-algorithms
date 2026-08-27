from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from device.operations import ServerOperation, ServerReceiveFromClientOperation
from device.serverdevice import ServerDevice
from sharedb.sharedbmessage import ShareDBMessage
from sharedb.sharedbtransform import apply, transform
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from sharedb.sharedbclient import ShareDBClient


class ShareDBServer(ServerDevice):
    """The one copy of the document that decides what order the operations happened in.

    A submitted operation names the version it was made against. The server transforms
    it forward over every operation committed since then, treating the submitted one as
    the left one, applies it, and gives it the next version number. The committed form
    goes to every client, the submitter included, which is how a client learns that its
    own operation is in.
    """

    clients: list[ShareDBClient]
    message_buffer: dict[int, list[ShareDBMessage]]

    state: list[UniqueChar]
    version: int
    committed: list[ShareDBMessage]

    def __init__(self, clients: list[ShareDBClient]):
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []
        self.state = []
        self.version = 0
        self.committed = []

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def receive_message(self, client_id: int) -> None:
        if len(self.message_buffer[client_id]) == 0:
            return

        message = self.message_buffer[client_id].pop(0)

        if message.version > self.version:
            raise ValueError(f"Operation submitted against version {message.version}, later than the document")

        operation = message.operation
        for earlier in self.committed[message.version :]:
            operation = transform(operation, earlier.operation, "left")

        self.state = apply(self.state, operation)

        committed = ShareDBMessage(
            message.client_id, message.sequence, self.version, operation, message.causing_operations
        )
        self.committed.append(committed)
        self.version += 1

        for client in self.clients:
            client.send_message(committed)

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) != 0:
                client_ids.append(client_id)
        return client_ids

    def send_message(self, client_id: int, message: ShareDBMessage) -> None:
        self.message_buffer[client_id].append(message)
