# An implementation of Roh2011's description of the RGA algorithm. Unlike later implementations, this one
# uses S4 vectors as timestamps, and uses a list instead of a tree.

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
from rgas4.rgas4message import (
    RGAS4DeletionOperation,
    RGAS4InsertionOperation,
    RGAS4Message,
    RGAS4Node,
    S4Vector,
)
from unique_char.uniquechar import UniqueChar


class RGAS4Client(ClientDevice):
    head: RGAS4Node | None
    rga: dict[S4Vector, RGAS4Node | None]
    vector_clock: dict[int, int]
    client_id: int
    clients: list[RGAS4Client]
    message_buffer: dict[int, list[RGAS4Message]]

    def __init__(self, client_id: int):
        self.head = None
        self.rga = {}
        self.client_id = client_id

    def set_clients(self, clients: list[RGAS4Client]):
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local(operation)
                return [operation]
            case ClientReceiveFromServerOperation():
                return []
            case ClientReceiveFromClientOperation(_, sender_client_id):
                return self.receive_from_client(sender_client_id)
            case ClientTimestepOperation():
                return []
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

        match message.operation:
            case RGAS4InsertionOperation(position, character):
                self.remote_insert(message.client_id, message.vector_clock, position, character)
            case RGAS4DeletionOperation(position):
                self.remote_delete(message.client_id, message.vector_clock, position)
            case _ as unreachable:
                assert_never(unreachable)

        self.vector_clock[client_id] += 1

        return [message.causing_operation]

    def derive_s4_vector(self, client_id: int, vector_clock: dict[int, int]) -> S4Vector:
        ssn = 1  # In this case, there is no sessions, so this number is not useful.
        sid = client_id
        su = sum(vector_clock.values())
        seq = vector_clock[client_id]
        return S4Vector(ssn, sid, su, seq)

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def __is_causally_ready(self, message: RGAS4Message) -> bool:
        sender = message.client_id
        if message.vector_clock[sender] != self.vector_clock[sender] + 1:
            return False
        for k in self.vector_clock:
            if k == sender:
                continue
            if message.vector_clock[k] > self.vector_clock[k]:
                return False
        return True

    def find_list(self, i: int) -> RGAS4Node | None:
        n = self.head
        k = 0
        while n is not None:
            if n.obj is not None:
                k += 1
                if i == k:
                    return n
            n = n.link
        return None

    def find_link(self, n: RGAS4Node) -> RGAS4Node | None:
        if n.obj is None:
            return None
        return n

    def perform_local(self, operation: ClientInsertOperation | ClientDeleteOperation):
        self.vector_clock[self.client_id] += 1
        match operation:
            case ClientInsertOperation(_, position, character):
                rga_operation = self.local_insert(position, character)
            case ClientDeleteOperation(_, position):
                rga_operation = self.local_delete(position)
            case _ as unreachable:
                assert_never(unreachable)
        self.__send_to_other_clients(RGAS4Message(self.client_id, self.vector_clock.copy(), rga_operation, operation))

    def __send_to_other_clients(self, message: RGAS4Message) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def local_insert(self, position: int, obj: UniqueChar) -> RGAS4InsertionOperation:
        s_o = self.derive_s4_vector(self.client_id, self.vector_clock)
        new_n = RGAS4Node(obj, s_o, s_o, None)
        if position == 0:
            new_n.link = self.head
            self.head = new_n
            index = None
        else:
            refer_n = self.find_list(position)
            if refer_n is None:
                raise ValueError("Insertion position does not exist")
            new_n.link = refer_n.link
            refer_n.link = new_n
            index = refer_n.s_k

        self.rga[s_o] = new_n

        return RGAS4InsertionOperation(index, obj)

    def local_delete(self, position: int) -> RGAS4DeletionOperation:
        target_n = self.find_list(position + 1)
        if target_n is None:
            raise ValueError("Target not found.")
        target_n.obj = None
        target_n.s_p = self.derive_s4_vector(self.client_id, self.vector_clock)
        return RGAS4DeletionOperation(target_n.s_k)

    def read(self, position: int):
        target_n = self.find_list(position)
        if target_n is None:
            return None
        return target_n.obj

    def remote_insert(self, client_id: int, vector_clock: dict[int, int], i: S4Vector | None, obj: UniqueChar):
        s_o = self.derive_s4_vector(client_id, vector_clock)
        ins = RGAS4Node(obj, s_o, s_o, None)
        self.rga[s_o] = ins

        if i is None:
            if self.head is None or self.head.s_k.less_than(s_o):
                if self.head is not None:
                    ins.link = self.head
                self.head = ins
                return True
            else:
                ref = self.head
        else:
            ref = self.rga.get(i)
            if ref is None:
                raise ValueError("Index out of bounds.")

        while ref.link is not None and ins.s_k.less_than(ref.link.s_k):
            ref = ref.link
        ins.link = ref.link
        ref.link = ins
        return True

    def remote_delete(self, client_id: int, vector_clock: dict[int, int], i: S4Vector):
        n = self.rga.get(i)
        if n is None:
            raise ValueError("Deleted item not found.")
        if n.obj is not None:
            n.obj = None
            n.s_p = self.derive_s4_vector(client_id, vector_clock)
        return True

    def send_message(self, client_id: int, message: RGAS4Message):
        self.message_buffer[client_id].append(message)

    def read_state(self) -> list[UniqueChar]:
        state: list[UniqueChar] = []
        n = self.head
        while n is not None:
            if n.obj is not None:
                state.append(n.obj)
            n = n.link
        return state

    def can_receive_from_server(self) -> bool:
        return False
