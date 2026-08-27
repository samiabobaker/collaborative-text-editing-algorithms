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
from diamondtypes.diamondtypesdocument import DiamondTypesDocument, DiamondTypesId
from diamondtypes.diamondtypesmessage import DiamondTypesMessage
from unique_char.uniquechar import UniqueChar


class DiamondTypesClient(ClientDevice):
    """Peer to peer Diamond Types client.

    Diamond Types implements eg-walker, the algorithm of the paper. This is a
    port of the Rust implementation's position map merge, src/listmerge: merge.rs
    (M2Tracker::apply and M2Tracker::integrate), advance_retreat.rs, yjsspan.rs
    and markers.rs, cross checked against the reference TypeScript
    implementation. A replica holds no CRDT state: it keeps the operations it was
    given, unchanged, and replays the event graph over them. That replay is
    DiamondTypesDocument, and this class is only the peer wiring around it.

    Every client holds its own replica of the oplog and broadcasts each local
    operation to all the others. Where the other peer to peer clients here carry
    a vector clock to decide when a message may be applied, this one does not
    need one: an eg-walker operation names its own parents, so a message is ready
    exactly when all of them have already arrived. That is the same test Diamond
    Types applies when it merges a remote oplog.
    """

    client_id: int

    document: DiamondTypesDocument
    clients: list[DiamondTypesClient]
    message_buffer: dict[int, list[DiamondTypesMessage]]

    __next_seq: int

    def __init__(self, client_id: int):
        self.document = DiamondTypesDocument()
        self.client_id = client_id
        self.__next_seq = 0

    def set_clients(self, clients: list[DiamondTypesClient]) -> None:
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Perform change to local document
        id = self.__next_id()
        diamond_types_operation = self.document.insert_char(operation.position, id, operation.character)
        # Send message to all other clients
        self.__send_to_other_clients(DiamondTypesMessage(id, diamond_types_operation, operation))

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local document
        id = self.__next_id()
        diamond_types_operation = self.document.delete_char(operation.position, id)
        # Send message to all other clients
        self.__send_to_other_clients(DiamondTypesMessage(id, diamond_types_operation, operation))

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
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        # A client only ever broadcasts its own operations, and each one goes to
        # each peer once into that peer's buffer for this sender, so an operation
        # cannot arrive twice. Appending it a second time would give one id two
        # local versions and quietly corrupt the oplog, so say so instead.
        assert not self.document.knows(message.id), f"Operation {message.id} was received twice"

        self.document.integrate(message.id, message.operation)

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

    def send_message(self, client_id: int, message: DiamondTypesMessage):
        self.message_buffer[client_id].append(message)

    def __next_id(self) -> DiamondTypesId:
        id = DiamondTypesId(self.client_id, self.__next_seq)
        self.__next_seq += 1
        return id

    def __send_to_other_clients(self, message: DiamondTypesMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def __is_causally_ready(self, message: DiamondTypesMessage) -> bool:
        return self.document.is_causally_ready(message.operation)
