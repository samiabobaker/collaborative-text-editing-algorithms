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
from soct3.soct3message import (
    SOCT3DeleteOperation,
    SOCT3InsertOperation,
    SOCT3Operation,
    SOCT3OperationMessage,
    SOCT3TicketRequestMessage,
    SOCT3TicketResponseMessage,
)
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from soct3.soct3server import SOCT3Server

class SOCT3Client(ClientDevice):

    client_id: int

    server: SOCT3Server
    server_message_buffer: list[SOCT3TicketResponseMessage]
    message_buffer: dict[int, list[SOCT3OperationMessage]]
    vector_clock: dict[int, int]
    history_buffer: list[SOCT3Operation]
    state: list[tuple[UniqueChar, bool]]
    timestamp: int

    clients: list[SOCT3Client]


    def __init__(self, client_id: int):
        self.client_id = client_id
        self.timestamp = 0
        self.state = []
        self.server_message_buffer = []
        self.history_buffer = []

    def set_clients(self, clients: list[SOCT3Client]) -> None:
            self.clients = clients
            self.message_buffer = {}
            self.vector_clock = {}
            for client in clients:
                self.message_buffer[client.client_id] = []
                self.vector_clock[client.client_id] = 0

    def set_server(self, server: SOCT3Server):
        self.server = server

    def read_state(self):
        return [c for c, v in self.state if v]

    

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation(client_id, position, character):
                self.execute_local(SOCT3InsertOperation(self.vector_clock.copy(), -1, self.client_id, character, self.view_to_model(position), operation), operation)
                return [operation]
            case ClientDeleteOperation(client_id, position):
                self.execute_local(SOCT3DeleteOperation(self.vector_clock.copy(), -1, self.client_id, self.view_to_model(position), operation), operation)
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

    def send_server_message(self, message: SOCT3TicketResponseMessage):
        self.server_message_buffer.append(message)

    def receive_from_server(self):
        if len(self.server_message_buffer) == 0:
            return

        message = self.server_message_buffer.pop(0)

        self.receive_ticket(message)

    def can_receive_from_server(self):
        return len(self.server_message_buffer) != 0

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
            
            if len(client_message_buffer) == 0:
                return []

            if not self.__is_ready(client_message_buffer[0]):
                return []
            
            message = client_message_buffer.pop(0)
    
            self.integrate(message.operation)

            return [message.causing_operation]

    def __advance(self):
        while len(self.history_buffer) > self.timestamp and self.history_buffer[self.timestamp].timestamp == self.timestamp + 1:
            self.timestamp += 1

    def __is_ready(self, message: SOCT3OperationMessage) -> bool:
        return self.timestamp + 1 == message.operation.timestamp

    def can_receive_from(self) -> list[int]:
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) == 0:
                continue
            message = self.message_buffer[client_id][0]
            if message.operation.timestamp == self.timestamp + 1:
                return [client_id]
        return []

    def view_to_model(self, position_in_view: int) -> int:
            position_in_model = 0
            visible = 0
            while position_in_model < len(self.state) and (visible < position_in_view or not self.state[position_in_model][1]):
                if self.state[position_in_model][1]:
                    visible += 1
                position_in_model += 1
            return position_in_model
    

    def execute_operation(self, op: SOCT3Operation):
        match op:
            case SOCT3InsertOperation(_, _, _, character, position):
                self.state.insert(position, (character, True))
            case SOCT3DeleteOperation(_, _, _, position):
                self.state[position] = (self.state[position][0], False)
            case _ as unreachable:
                assert_never(unreachable)


    def execute_local(self, op: SOCT3Operation, causing_operation: ClientInsertOperation | ClientDeleteOperation):
        n = len(self.history_buffer)
        self.execute_operation(op)
        self.vector_clock[self.client_id] += 1
        self.history_buffer.append(op)
        self.server.send_message(self.client_id, SOCT3TicketRequestMessage(self.client_id, n, op, causing_operation))

    def receive_ticket(self, message: SOCT3TicketResponseMessage):
        for j in range(self.timestamp, len(self.history_buffer)):
            if self.history_buffer[j].timestamp == -1:
                self.history_buffer[j].timestamp = message.ticket
                message.operation.timestamp = message.ticket
                self.__send_to_other_clients(SOCT3OperationMessage(self.client_id, message.operation, message.causing_operation))
                break
        self.__advance()
    def __send_to_other_clients(self, message: SOCT3OperationMessage):
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def send_message(self, client_id: int, message: SOCT3OperationMessage):
        self.message_buffer[client_id].append(message)

    def __transpose_bk(self, O1: SOCT3Operation, O2:SOCT3Operation) -> tuple[SOCT3Operation, SOCT3Operation]:
            match O1, O2:
                case SOCT3InsertOperation(_, _, _, _, p1), SOCT3InsertOperation(vc2, t2, id2, c2, p2, co2):
                    O2p = SOCT3InsertOperation(vc2, t2, id2, c2, p2 if p2 <= p1 else p2 - 1, co2)
                case SOCT3InsertOperation(_, _, _, _, p1), SOCT3DeleteOperation(vc2, t2, id2, p2, co2):
                    O2p = SOCT3DeleteOperation(vc2, t2, id2, p2 if p2 < p1 else p2 - 1, co2)
                case _:
                    O2p = O2
            return O2p, self.__transpose_fd(O2p, O1)
    
    def __transpose_fd(self, O1: SOCT3Operation, O2:SOCT3Operation) -> SOCT3Operation:
            match O1, O2:
                case SOCT3InsertOperation(_, _, id1, _, p1), SOCT3InsertOperation(vc2, t2, id2, c2, p2, co2):
                    if p1 < p2 or (p1 == p2 and id1 < id2):
                        return SOCT3InsertOperation(vc2, t2, id2, c2, p2 + 1, co2)
                    return SOCT3InsertOperation(vc2, t2, id2, c2, p2, co2)
                case SOCT3InsertOperation(_, _, id1, _, p1, _), SOCT3DeleteOperation(vc2, t2, id2, p2, co2):
                    return SOCT3DeleteOperation(vc2, t2, id2, p2 + 1 if p1 <= p2 else p2, co2)
                case SOCT3DeleteOperation(), _:
                    return O2
                case _ as unreachable:
                    assert_never(unreachable)

    def __transpose_backward(self, hb: list[SOCT3Operation], j: int):
        O1 = hb[j]
        O2 = hb[j-1]

        transformed_O1, transformed_O2 = self.__transpose_bk(O2, O1)

        hb[j] = transformed_O2
        hb[j-1] = transformed_O1


    def __separate(self, hb: list[SOCT3Operation], vector_clock: dict[int, int]) -> int:
        n1 = 0
        for i, log_entry in enumerate(hb):
            if log_entry.vector_clock[log_entry.client_id] < vector_clock[log_entry.client_id]:
                for j in range(i, n1, - 1):
                    self.__transpose_backward(hb, j)
                n1 = n1 + 1
        return n1

    def integrate(self, op: SOCT3Operation):
        if self.timestamp != op.timestamp:
            hb_copy = list(self.history_buffer)
            n1 = self.__separate(hb_copy, op.vector_clock)
            for i in range(n1, len(self.history_buffer)):
                op = self.__transpose_fd(hb_copy[i], op)

            self.execute_operation(op)
            self.vector_clock[op.client_id] += 1
            self.history_buffer.append(op)
            for j in range(len(self.history_buffer) - 1, op.timestamp - 1, -1):
                self.__transpose_backward(self.history_buffer, j)
        self.__advance()


