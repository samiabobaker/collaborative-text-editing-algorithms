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
from twc.twcidlist import TWCIdList
from twc.twcmessage import (
    TWCCommittedMessage,
    TWCDeletionOperation,
    TWCInsertionOperation,
    TWCMessage,
    TWCOperation,
)
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from twc.twcserver import TWCServer

# Element ids name a place in the list and update ids name one update. Both are
# opaque and globally unique, so plain increasing integers stand in for both.
_next_element_id = 0
_next_update_id = 0


def allocate_element_id() -> int:
    global _next_element_id
    _next_element_id += 1
    return _next_element_id


def allocate_update_id() -> int:
    global _next_update_id
    _next_update_id += 1
    return _next_update_id


class TWCClient(ClientDevice):
    """One replica, holding a committed state and an optimistic view of it.

    Local operations are applied to the optimistic view at once and held as
    pending until the server commits them. Whenever committed updates arrive the
    optimistic view is rebuilt as the committed state plus whatever is still
    pending, in the order this client made those updates.
    """

    client_id: int

    server_state: TWCIdList  # committed updates applied in server_version order
    server_version: int  # how many committed updates have been applied
    local_state: TWCIdList  # the optimistic view = server_state + pending
    # Pending local updates that the server has not committed yet, keyed by
    # update id. Dictionary order is creation order, which is the order they
    # are replayed in.
    pending: dict[int, TWCOperation]
    # Inbox of committed updates broadcast by the server (FIFO, so arrival
    # order == server_version order).
    message_buffer: list[TWCCommittedMessage]

    twc_server: TWCServer

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.server_state = TWCIdList()
        self.server_version = 0
        self.local_state = TWCIdList()
        self.pending = {}
        self.message_buffer = []

    def set_server(self, server: TWCServer) -> None:
        self.twc_server = server

    # ---- state model -----------------------------------------------------

    @staticmethod
    def __apply_update(idlist: TWCIdList, update: TWCOperation) -> None:
        match update:
            case TWCInsertionOperation(_, before_id, element_id, character):
                # Insert after before_id in the known order, which includes
                # tombstones. None inserts at the start of the list.
                idlist.insert_after(before_id, element_id, character)
            case TWCDeletionOperation(_, element_id):
                idlist.delete(element_id)  # mark tombstone
            case _ as unreachable:
                assert_never(unreachable)

    def __rerun_pending(self) -> None:
        """Rebuild the local view as the committed state plus pending, in creation order."""
        self.local_state = self.server_state.copy()
        for update in self.pending.values():
            self.__apply_update(self.local_state, update)

    def __apply_local_update(self, update: TWCOperation) -> None:
        """Apply an update optimistically and remember it as pending.

        With nothing pending the local view is already a copy of the committed
        state, so the update can go straight on top of it.
        """
        self.__apply_update(self.local_state, update)
        self.pending[update.update_id] = update

    # ---- local operations -------------------------------------------------

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # The anchor is read off the local view, which already includes this
        # client's own pending edits. Position p means after the (p-1)th present
        # character, and position 0 means the start of the list.
        before_id: int | None = None
        if operation.position > 0:
            before_id = self.local_state.at_present(operation.position - 1)

        # The client chooses the new element id, not the server.
        element_id = allocate_element_id()
        update = TWCInsertionOperation(allocate_update_id(), before_id, element_id, operation.character)

        self.__apply_local_update(update)
        self.twc_server.send_message(
            self.client_id,
            TWCMessage(update, operation),
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        element_id = self.local_state.at_present(operation.position)
        update = TWCDeletionOperation(allocate_update_id(), element_id)

        self.__apply_local_update(update)
        self.twc_server.send_message(
            self.client_id,
            TWCMessage(update, operation),
        )

    # ---- remote updates ---------------------------------------------------

    def receive_message(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        """Fold the next committed update into the committed state.

        The inbox is FIFO, so updates arrive in server_version order. An echo of
        this client's own update takes it out of pending, and the local view is
        then rebuilt. Returns the operation that caused the update.
        """
        if len(self.message_buffer) == 0:
            return []

        committed = self.message_buffer.pop(0)

        if committed.server_version != self.server_version:
            raise ValueError(
                f"Server committed version {committed.server_version} but this client is at {self.server_version}"
            )
        self.server_version += 1

        self.__apply_update(self.server_state, committed.operation)
        self.pending.pop(committed.operation.update_id, None)
        self.__rerun_pending()

        return [committed.causing_operation]

    def send_message(self, message: TWCCommittedMessage) -> None:
        self.message_buffer.append(message)

    # ---- ClientDevice interface -------------------------------------------

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation(_):
                return self.receive_message()
            case ClientReceiveFromClientOperation(_, _):
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def read_state(self) -> list[UniqueChar]:
        return self.local_state.present_chars()

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def can_receive_from(self) -> list[int]:
        return []  # client-server algorithm
