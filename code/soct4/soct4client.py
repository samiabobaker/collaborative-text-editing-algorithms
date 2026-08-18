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
from soct4.soct4message import (
    SOCT4DeleteOperation,
    SOCT4InsertOperation,
    SOCT4NoOperation,
    SOCT4Operation,
    SOCT4OperationMessage,
    SOCT4TicketRequestMessage,
    SOCT4TicketResponseMessage,
)
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from soct4.soct4server import SOCT4Server


class SOCT4Client(ClientDevice):
    client_id: int

    server: SOCT4Server
    server_message_buffer: list[SOCT4TicketResponseMessage]
    message_buffer: dict[int, list[SOCT4OperationMessage]]
    history_buffer: list[SOCT4Operation]
    state: list[UniqueChar]
    timestamp: int

    clients: list[SOCT4Client]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.timestamp = 0
        self.state = []
        self.server_message_buffer = []
        self.history_buffer = []

    def set_clients(self, clients: list[SOCT4Client]) -> None:
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []

    def set_server(self, server: SOCT4Server):
        self.server = server

    def read_state(self):
        return self.state

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation(client_id, position, character):
                self.execute_local(SOCT4InsertOperation(-1, self.client_id, character, position, operation), operation)
                return [operation]
            case ClientDeleteOperation(client_id, position):
                self.execute_local(SOCT4DeleteOperation(-1, self.client_id, position, operation), operation)
                return [operation]
            case ClientReceiveFromServerOperation(client_id):
                self.receive_from_server()
                return []
            case ClientReceiveFromClientOperation(_, client_id):
                return self.receive_from_client(client_id)
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def send_server_message(self, message: SOCT4TicketResponseMessage):
        self.server_message_buffer.append(message)

    def receive_from_server(self):
        if len(self.server_message_buffer) == 0:
            return

        message = self.server_message_buffer.pop(0)

        self.receive_ticket(message)

    def can_receive_from_server(self):
        return len(self.server_message_buffer) != 0

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        self.integrate(message.operation)

        return [message.causing_operation]

    def __is_ready(self, message: SOCT4OperationMessage) -> bool:
        return self.timestamp + 1 == message.operation.timestamp

    def can_receive_from(self) -> list[int]:
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) == 0:
                continue
            message = self.message_buffer[client_id][0]
            if message.operation.timestamp == self.timestamp + 1:
                return [client_id]
        return []

    def execute_operation(self, op: SOCT4Operation):
        match op:
            case SOCT4InsertOperation(_, _, character, position):
                self.state.insert(position, character)
            case SOCT4DeleteOperation(_, _, position):
                del self.state[position]
            case SOCT4NoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def execute_local(self, op: SOCT4Operation, causing_operation: ClientInsertOperation | ClientDeleteOperation):
        n = len(self.history_buffer)
        self.execute_operation(op)
        self.history_buffer.append(op)
        self.server.send_message(self.client_id, SOCT4TicketRequestMessage(self.client_id, n, op, causing_operation))

    def receive_ticket(self, message: SOCT4TicketResponseMessage):
        for j in range(self.timestamp, len(self.history_buffer)):
            if self.history_buffer[j].timestamp == -1:
                self.history_buffer[j].timestamp = message.ticket
                break
        self.deferred_broadcast()

    def __send_to_other_clients(self, message: SOCT4OperationMessage):
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def send_message(self, client_id: int, message: SOCT4OperationMessage):
        self.message_buffer[client_id].append(message)

    def integrate(self, op: SOCT4Operation):
        if self.timestamp != op.timestamp:
            self.history_buffer.insert(self.timestamp, op)
            for j in range(self.timestamp + 1, len(self.history_buffer)):
                op_L = self.history_buffer[j]

                self.history_buffer[j] = self.transpose_forward(op_L, op)

                op = self.transpose_forward(op, op_L)
            self.execute_operation(op)
            self.timestamp += 1
        self.deferred_broadcast()

    def deferred_broadcast(self):
        while len(self.history_buffer) > self.timestamp:
            op = self.history_buffer[self.timestamp]
            if op.timestamp != self.timestamp + 1:
                return
            self.__send_to_other_clients(SOCT4OperationMessage(self.client_id, op, op.causing_operation))
            self.timestamp += 1

    def transpose_forward(self, O1: SOCT4Operation, O2: SOCT4Operation) -> SOCT4Operation:
        match O1, O2:
            case SOCT4InsertOperation(t1, id1, x, i, co1), SOCT4InsertOperation(_, id2, _, j):
                if i < j:
                    return SOCT4InsertOperation(t1, id1, x, i, co1)
                elif i > j or id1 < id2:
                    return SOCT4InsertOperation(t1, id1, x, i + 1, co1)
                else:
                    return SOCT4InsertOperation(t1, id1, x, i, co1)
            case SOCT4InsertOperation(t1, id1, x, i, co1), SOCT4DeleteOperation(_, _, j):
                if i <= j:
                    return SOCT4InsertOperation(t1, id1, x, i, co1)
                else:
                    return SOCT4InsertOperation(t1, id1, x, i - 1, co1)
            case SOCT4DeleteOperation(t1, id1, i, co1), SOCT4InsertOperation(_, _, _, j):
                if i < j:
                    return SOCT4DeleteOperation(t1, id1, i, co1)
                else:
                    return SOCT4DeleteOperation(t1, id1, i + 1, co1)
            case SOCT4DeleteOperation(t1, id1, i, co1), SOCT4DeleteOperation(_, _, j):
                if i > j:
                    return SOCT4DeleteOperation(t1, id1, i - 1, co1)
                elif i < j:
                    return SOCT4DeleteOperation(t1, id1, i, co1)
                else:
                    return SOCT4NoOperation(t1, id1, co1)
            case SOCT4NoOperation(t1, id1, co1), oper:
                return SOCT4NoOperation(t1, id1, co1)
            case oper, SOCT4NoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)
