from dataclasses import dataclass
from typing import assert_never
from device.clientdevice import ClientDevice
from soct2.soct2message import SOCT2Message, SOCT2Operation, SOCT2DeletionOperation, SOCT2InsertionOperation
from unique_char.uniquechar import UniqueChar
from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientOperation, ClientReceiveFromClientOperation, ClientReceiveFromServerOperation, ClientTimestepOperation

@dataclass
class SOCT2LogEntry:
    operation : SOCT2Operation
    client_id: int
    vector_clock: dict[int, int]

#Implementation with the TTF functions.
class SOCT2Client(ClientDevice):
    client_id: int

    clients: list[SOCT2Client]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[SOCT2Message]]

    state: list[tuple[UniqueChar, bool]]
    history_buffer: list[SOCT2LogEntry]


    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.history_buffer = []


    def set_clients(self, clients: list[SOCT2Client]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        op = SOCT2InsertionOperation(self.client_id, self.view_to_model(operation.position), operation.character)
        self.integrate(op, self.client_id, self.vector_clock.copy())
        self.__send_to_other_clients(SOCT2Message(self.client_id, self.vector_clock.copy(), op, operation))

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        op = SOCT2DeletionOperation(self.client_id, self.view_to_model(operation.position))
        self.integrate(op, self.client_id, self.vector_clock.copy())
        self.__send_to_other_clients(SOCT2Message(self.client_id, self.vector_clock.copy(), op, operation))

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
        return [c for c, visible in self.state if visible]

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        #Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []
        
        if not self.__is_causally_ready(client_message_buffer[0]):
            return []
        
        message = client_message_buffer.pop(0)

        self.integrate(message.operation, message.client_id, message.vector_clock)

        self.vector_clock[client_id] += 1

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
    
    def send_message(self, client_id: int, message: SOCT2Message):
        self.message_buffer[client_id].append(message)
    
    def __send_to_other_clients(self, message: SOCT2Message) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: SOCT2Message) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True


    def __transpose_bk(self, O1: SOCT2Operation, O2:SOCT2Operation) -> tuple[SOCT2Operation, SOCT2Operation]:
        match O1, O2:
            case SOCT2InsertionOperation(_, p1, _), SOCT2InsertionOperation(r2, p2, c2):
                O2p = SOCT2InsertionOperation(r2, p2 if p2 <= p1 else p2 - 1, c2)
            case SOCT2InsertionOperation(_, p1, _), SOCT2DeletionOperation(r2, p2):
                O2p = SOCT2DeletionOperation(r2, p2 if p2 < p1 else p2 - 1)
            case _:
                O2p = O2
        return O2p, self.__transpose_fd(O2p, O1)

    def __transpose_fd(self, O1: SOCT2Operation, O2:SOCT2Operation) -> SOCT2Operation:
            match O1, O2:
                case SOCT2InsertionOperation(r1, p1, _), SOCT2InsertionOperation(r2, p2, c2):
                    if p1 < p2 or (p1 == p2 and r1 < r2):
                        return SOCT2InsertionOperation(r2, p2 + 1, c2)
                    return SOCT2InsertionOperation(r2, p2, c2)
                case SOCT2InsertionOperation(r1, p1, _), SOCT2DeletionOperation(r2, p2):
                    return SOCT2DeletionOperation(r2, p2 + 1 if p1 <= p2 else p2)
                case SOCT2DeletionOperation(), _:
                    return O2
                case _ as unreachable:
                    assert_never(unreachable)

    def __transpose_backward(self, j: int):
        O1 = self.history_buffer[j]
        O2 = self.history_buffer[j-1]

        transformed_O1, transformed_O2 = self.__transpose_bk(O2.operation, O1.operation)

        self.history_buffer[j] = SOCT2LogEntry(transformed_O2, O2.client_id, O2.vector_clock)
        self.history_buffer[j-1] = SOCT2LogEntry(transformed_O1, O1.client_id, O1.vector_clock)

    def __separate(self, vector_clock: dict[int, int]):
        n1 = 0
        for i, log_entry in enumerate(self.history_buffer):
            if log_entry.vector_clock[log_entry.client_id] < vector_clock[log_entry.client_id]:
                for j in range(i, n1, - 1):
                    self.__transpose_backward(j)
                n1 = n1 + 1
        return n1

    def integrate(self, operation: SOCT2Operation, client_id: int, vector_clock: dict[int, int]):
        n1 = self.__separate(vector_clock)
        for i in range(n1, len(self.history_buffer)):
            operation = self.__transpose_fd(self.history_buffer[i].operation, operation)
        self.__apply_operation(operation)
        self.history_buffer.append(SOCT2LogEntry(operation, client_id, vector_clock))


    def __insert_character(self, position: int, character: UniqueChar) -> None:
            self.state.insert(position, (character, True))
    
    def __delete_character(self, position:int) -> None:
        self.state[position] = (self.state[position][0], False)

    def view_to_model(self, position_in_view: int) -> int:
        position_in_model = 0
        visible = 0
        while position_in_model < len(self.state) and (visible < position_in_view or not self.state[position_in_model][1]):
            if self.state[position_in_model][1]:
                visible += 1
            position_in_model += 1
        return position_in_model

    def __apply_operation(self, operation: SOCT2Operation) -> None:
            match operation:
                case SOCT2InsertionOperation(_, position, character):
                    self.__insert_character(position, character)
                case SOCT2DeletionOperation(_, position):
                    self.__delete_character(position)
                case _ as unreachable:
                    assert_never(unreachable)


