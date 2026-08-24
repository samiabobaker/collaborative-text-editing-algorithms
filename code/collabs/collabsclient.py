from typing import assert_never

from collabs.collabsdocument import CollabsLocalList
from collabs.collabsmessage import (
    CollabsCreateOperation,
    CollabsDeletionOperation,
    CollabsInsertionOperation,
    CollabsMessage,
    CollabsOperation,
)
from collabs.collabstotalorder import CollabsTotalOrder
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


class CollabsClient(ClientDevice):
    """One replica of a Collabs CText (as used in a model-checker run).

    Holds the tree of positions, the local view of which positions carry values,
    and the transactional send and causally ordered delivery around them.
    """

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.replica_id = str(client_id)
        self.clients: list[CollabsClient] = []
        self.total_order = CollabsTotalOrder(self.replica_id, self.__send_primitive)
        self.list = CollabsLocalList(self.total_order)
        # Causal delivery state: what this replica has seen, and which of those
        # entries are causally maximal.
        self.vc: dict[str, int] = {self.replica_id: 0}
        self.maximal_vc_keys: set[str] = set()
        # In-flight transactions, keyed by sender client id, per-sender FIFO.
        self.message_buffer: dict[int, list[CollabsMessage]] = {}
        # Current-transaction state.
        self.__pending: list[CollabsOperation] = []
        self.__causing: ClientInsertOperation | ClientDeleteOperation | None = None
        self.__maximal_at_send: set[str] = set()

    def set_clients(self, clients: list[CollabsClient]) -> None:
        self.clients = clients
        for client in clients:
            self.message_buffer[client.client_id] = []

    # ---- ClientDevice interface ----

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
        return list(self.list.values())

    def can_receive_from_server(self) -> bool:
        # Client-client (P2P) algorithm.
        return False

    def can_receive_from(self) -> list[int]:
        """Clients whose next (oldest) pending transaction is causally ready."""
        client_ids: list[int] = []
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            buffer = self.message_buffer[client.client_id]
            if len(buffer) != 0 and self.__is_ready(buffer[0]):
                client_ids.append(client.client_id)
        return client_ids

    # ---- local operations --------------------------------------------------

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # A local insert creates one position and sets one value in it.
        self.__begin_transaction(operation)
        prev_position = None if operation.position == 0 else self.list.get_position(operation.position - 1)
        next_position = None if operation.position == self.list.length else self.list.get_position(operation.position)
        first_new_pos = self.total_order.create_positions(prev_position, next_position, 1)[0]
        waypoint, value_index = self.total_order.decode(first_new_pos)
        # The local echo (in __send_primitive) applies this insert to this
        # replica's list; the message is then broadcast in the current transaction.
        self.__send_primitive(CollabsInsertionOperation(waypoint.counter, value_index, operation.character))
        self.__finish_transaction()

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # A local delete clears one position.
        self.__begin_transaction(operation)
        position = self.list.get_position(operation.position)
        self.__send_primitive(CollabsDeletionOperation(position))
        self.__finish_transaction()

    # ---- transactions ------------------------------------------------------

    def __begin_transaction(self, causing: ClientInsertOperation | ClientDeleteOperation) -> None:
        # The maximal keys are captured before the counter is advanced, so they
        # describe what this replica had seen when the transaction began. Advancing
        # the counter then clears them.
        self.__maximal_at_send = set(self.maximal_vc_keys)
        self.vc[self.replica_id] += 1
        self.maximal_vc_keys.clear()
        self.__pending = []
        self.__causing = causing

    def __send_primitive(self, message: CollabsOperation) -> None:
        # The sender applies its own operation immediately, so a local edit is
        # visible before anything is sent, and the operation then joins the
        # current transaction.
        self.__apply_message(message, self.replica_id)
        self.__pending.append(message)

    def __finish_transaction(self) -> None:
        # Ending the transaction sends everything buffered in it as one message,
        # which here means enqueueing it for every other replica.
        assert self.__causing is not None
        txn = CollabsMessage(
            sender_id=self.replica_id,
            sender_counter=self.vc[self.replica_id],
            vc_entries={
                self.replica_id: self.vc[self.replica_id],
                **{key: self.vc[key] for key in self.__maximal_at_send},
            },
            maximal_vc_key_count=len(self.__maximal_at_send),
            operations=list(self.__pending),
            causing_operation=self.__causing,
        )
        for client in self.clients:
            if client.client_id != self.client_id:
                client.message_buffer[self.client_id].append(txn)
        self.__pending = []
        self.__causing = None

    def __apply_message(self, message: CollabsOperation, sender_id: str) -> None:
        """Apply one operation from a delivered message."""
        match message:
            case CollabsCreateOperation():
                self.total_order.apply_create(message, sender_id)
            case CollabsInsertionOperation():
                # An insertion names its waypoint by the counter it carries and the
                # sender of the message, which together give the position to set.
                waypoint = self.total_order.get_waypoint(sender_id, message.waypoint_counter)
                positions = self.total_order.encode_all(waypoint, message.value_index, 1)
                self.list.set_created(positions[0], [message.value])
            case CollabsDeletionOperation():
                # A delete of a position this replica does not hold is a no-op.
                if self.list.has_position(message.position):
                    self.list.delete(message.position)
            case _ as unreachable:
                assert_never(unreachable)

    # ---- remote delivery ---------------------------------------------------

    def receive_from_client(self, sender_client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        buffer = self.message_buffer[sender_client_id]
        if len(buffer) == 0:
            return []
        txn = buffer[0]
        if not self.__is_ready(txn):
            return []
        buffer.pop(0)
        for message in txn.operations:
            self.__apply_message(message, txn.sender_id)
        self.__process_remote_delivery(txn)
        return [txn.causing_operation]

    def __is_ready(self, txn: CollabsMessage) -> bool:
        # Ready when the sender's entry is exactly one more than this replica's
        # and every causally maximal entry it carries is at most this replica's.
        if self.vc.get(txn.sender_id, 0) != txn.sender_counter - 1:
            return False
        i = 0
        for key, value in txn.vc_entries.items():
            if key == txn.sender_id:
                continue
            if i == txn.maximal_vc_key_count:
                break
            if self.vc.get(key, 0) < value:
                return False
            i += 1
        return True

    def __process_remote_delivery(self, txn: CollabsMessage) -> None:
        # A causally maximal key stops being maximal once this replica has seen
        # exactly as much of it as the message did.
        i = 0
        for key, value in txn.vc_entries.items():
            if key == txn.sender_id:
                continue
            if i == txn.maximal_vc_key_count:
                break
            if self.vc.get(key) == value:
                self.maximal_vc_keys.discard(key)
            i += 1
        # The message is remote, so its sender is never this replica.
        self.maximal_vc_keys.add(txn.sender_id)
        self.vc[txn.sender_id] = txn.sender_counter
