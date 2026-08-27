from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from sharedb.sharedbmessage import (
    ShareDBDelete,
    ShareDBInsert,
    ShareDBMessage,
    ShareDBOperation,
    ShareDBSkip,
    ShareDBSubmission,
)
from sharedb.sharedbtransform import apply, compose, normalise, transform
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from sharedb.sharedbserver import ShareDBServer


class ShareDBClient(ClientDevice):
    """A client of a single server that holds the document and orders the operations.

    The client applies its own operations straight away and keeps them, so at most one
    operation is with the server at a time and the rest wait behind it. An operation
    made while another is with the server is composed into the one waiting, which is
    what makes a run of typing arrive as a single operation.

    When an operation comes back from the server the client transforms whatever it is
    still holding against it, and it against them, before applying it. The operation
    the client is holding is the left one and the one from the server is the right one,
    so where the two insert at the same position the client's own goes first. The
    server resolves the same tie the same way, by treating whoever is submitting as the
    left one, which is how the two ends agree without exchanging anything else.
    """

    client_id: int
    server: ShareDBServer

    state: list[UniqueChar]
    version: int
    inflight: ShareDBSubmission | None
    pending: list[ShareDBSubmission]
    message_buffer: list[ShareDBMessage]

    __next_sequence: int

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.version = 0
        self.inflight = None
        self.pending = []
        self.message_buffer = []
        self.__next_sequence = 0

    def set_server(self, server: ShareDBServer) -> None:
        self.server = server

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.__submit(normalise([ShareDBSkip(operation.position), ShareDBInsert([operation.character])]), operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.__submit(normalise([ShareDBSkip(operation.position), ShareDBDelete(1)]), operation)

    def __submit(
        self, operation: ShareDBOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        self.__push_operation(operation, causing_operation)
        self.state = apply(self.state, operation)
        self.flush()

    def __push_operation(
        self, operation: ShareDBOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        # An operation can only be composed into one that is still waiting to be sent.
        if len(self.pending) != 0:
            waiting = self.pending[-1]
            waiting.operation = compose(waiting.operation, operation)
            waiting.causing_operations.append(causing_operation)
            return

        self.pending.append(ShareDBSubmission(operation, None, [causing_operation]))

    def flush(self) -> None:
        if self.inflight is not None or len(self.pending) == 0:
            return

        submission = self.pending.pop(0)
        submission.sequence = self.__next_sequence
        self.__next_sequence += 1
        self.inflight = submission

        self.server.send_message(
            self.client_id,
            ShareDBMessage(
                self.client_id,
                submission.sequence,
                self.version,
                submission.operation,
                list(submission.causing_operations),
            ),
        )

    def receive_from_server(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if len(self.message_buffer) == 0:
            return []

        message = self.message_buffer.pop(0)

        if message.version != self.version:
            raise ValueError(f"Server committed version {message.version} but this client is at {self.version}")

        inflight = self.inflight
        if inflight is not None and message.client_id == self.client_id and message.sequence == inflight.sequence:
            # This client's own operation, which it applied when it was made. Nothing to
            # apply, and the next operation waiting can now be sent.
            self.version += 1
            self.inflight = None
            self.flush()
            return []

        operation = message.operation

        if inflight is not None:
            inflight.operation, operation = self.__transform_both_ways(inflight.operation, operation)

        for waiting in self.pending:
            waiting.operation, operation = self.__transform_both_ways(waiting.operation, operation)

        self.version += 1
        self.state = apply(self.state, operation)

        return list(message.causing_operations)

    @staticmethod
    def __transform_both_ways(
        client_operation: ShareDBOperation, server_operation: ShareDBOperation
    ) -> tuple[ShareDBOperation, ShareDBOperation]:
        return (
            transform(client_operation, server_operation, "left"),
            transform(server_operation, client_operation, "right"),
        )

    def send_message(self, message: ShareDBMessage) -> None:
        self.message_buffer.append(message)

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation():
                return self.receive_from_server()
            case ClientReceiveFromClientOperation():
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def can_receive_from(self) -> list[int]:
        return []
