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
from easysync.easysyncchangeset import EasySyncChangeset, EasySyncOp, apply_to_text, compose, follow, identity
from easysync.easysyncmessage import EasySyncMessage, EasySyncSubmission
from easysync.easysyncserver import EasySyncServer
from unique_char.uniquechar import UniqueChar


class EasySyncClient(ClientDevice):
    client_id: int
    server: EasySyncServer

    base_text: list[UniqueChar]
    submitted_changeset: EasySyncChangeset | None
    user_changeset: EasySyncChangeset

    message_buffer: list[EasySyncMessage]

    rev: int

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.base_text = []
        self.submitted_changeset = None
        self.user_changeset = identity(0)
        self.message_buffer = []
        self.rev = -1

    def set_server(self, server: EasySyncServer):
        self.server = server

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local(operation)
                return [operation]
            case ClientReceiveFromServerOperation(_):
                return self.receive_from_server()
            case ClientReceiveFromClientOperation(_, _):
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def get_changeset_from_operation(
        self, operation: ClientInsertOperation | ClientDeleteOperation
    ) -> EasySyncChangeset:
        state_length = len(self.read_state())
        ops: list[EasySyncOp] = []
        position = operation.position
        if position > 0:
            ops.append(EasySyncOp("=", position, None))
        match operation:
            case ClientInsertOperation(_, _, character):
                ops.append(EasySyncOp("+", 1, [character]))
                return EasySyncChangeset(state_length, state_length + 1, ops, [operation])
            case ClientDeleteOperation():
                ops.append(EasySyncOp("-", 1, None))
                return EasySyncChangeset(state_length, state_length - 1, ops, [operation])
            case _ as unreachable:
                assert_never(unreachable)

    def perform_local(self, operation: ClientInsertOperation | ClientDeleteOperation):
        changeset = self.get_changeset_from_operation(operation)
        self.user_changeset = compose(self.user_changeset, changeset)
        self.submit_changeset_to_server()

    def read_state(self) -> list[UniqueChar]:
        state = list(self.base_text)
        if self.submitted_changeset is not None:
            state = apply_to_text(state, self.submitted_changeset)
        state = apply_to_text(state, self.user_changeset)
        return state

    def apply_changes_to_base(self, changeset: EasySyncChangeset):
        self.base_text = apply_to_text(self.base_text, changeset)

        c2 = changeset
        if self.submitted_changeset is not None:
            old_submitted_changeset = self.submitted_changeset
            self.submitted_changeset = follow(changeset, old_submitted_changeset, False)
            c2 = follow(old_submitted_changeset, changeset, True)

        prefer_inserting_after_user_changes = True
        old_user_changeset = self.user_changeset
        self.user_changeset = follow(c2, old_user_changeset, prefer_inserting_after_user_changes)

    def apply_prepared_changeset_to_base(self):
        assert self.submitted_changeset is not None
        self.base_text = apply_to_text(self.base_text, self.submitted_changeset)
        self.submitted_changeset = None

    def receive_from_server(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if not self.can_receive_from_server():
            return []

        message = self.message_buffer.pop(0)
        self.rev = message.new_rev

        if self.client_id == message.client_id:
            self.apply_prepared_changeset_to_base()
            self.submit_changeset_to_server()
            return []

        self.apply_changes_to_base(message.changeset)

        return list(message.changeset.causing_operations)

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def can_receive_from(self) -> list[int]:
        return []

    def submit_changeset_to_server(self):
        if self.submitted_changeset is not None:
            return

        if self.user_changeset.is_identity():
            return

        self.submitted_changeset = self.user_changeset
        self.user_changeset = EasySyncChangeset(self.user_changeset.new_length, self.user_changeset.new_length, [], [])

        self.server.send_message(self.client_id, EasySyncSubmission(self.client_id, self.rev, self.submitted_changeset))

    def send_message(self, message: EasySyncMessage):
        self.message_buffer.append(message)
