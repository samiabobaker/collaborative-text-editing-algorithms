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
from markandretrace.markandretracemessage import (
    MarkAndRetraceDeletionOperation,
    MarkAndRetraceInsertionOperation,
    MarkAndRetraceMessage,
    MarkAndRetraceOperation,
)
from markandretrace.markandretracestring import MarkAndRetraceCharacter, MarkAndRetraceString
from unique_char.uniquechar import UniqueChar


class MarkAndRetraceClient(ClientDevice):
    client_id: int
    string: MarkAndRetraceString

    clients: list[MarkAndRetraceClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[MarkAndRetraceMessage]]


    def __init__(self, client_id: int):
        self.client_id = client_id
        self.string = MarkAndRetraceString()

    def read_state(self) -> list[UniqueChar]:
        return self.string.read_state()



    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
            client_ids: list[int] = []
            for client in self.clients:
                client_message_buffer = self.message_buffer[client.client_id]
                if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                    client_ids.append(client.client_id)
            
            return client_ids

    def __is_causally_ready(self, message: MarkAndRetraceMessage) -> bool:
            for client in self.clients:
                if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                    return False
            return True

    
    def perform_local_insert(self, causing_operation: ClientInsertOperation) -> None:
            operation_state_vector = self.vector_clock.copy()
            operation_state_vector[self.client_id] += 1
            operation = MarkAndRetraceInsertionOperation(self.client_id, operation_state_vector, causing_operation.character, causing_operation.position)
            message = MarkAndRetraceMessage(self.vector_clock.copy(), operation, causing_operation)

            self.control_algorithm(operation)
            #Send message to all other clients
            self.__send_to_other_clients(message)
    
    def perform_local_delete(self, causing_operation: ClientDeleteOperation) -> None:
        operation_state_vector = self.vector_clock.copy()
        operation_state_vector[self.client_id] += 1
        operation = MarkAndRetraceDeletionOperation(self.client_id, operation_state_vector, causing_operation.position)
        message = MarkAndRetraceMessage(self.vector_clock.copy(), operation, causing_operation)
        self.control_algorithm(operation)
        self.__send_to_other_clients(message)

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
    
    
    def __send_to_other_clients(self, message: MarkAndRetraceMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def send_message(self, client_id: int, message: MarkAndRetraceMessage):
        self.message_buffer[client_id].append(message)
    
 
    def set_clients(self, clients: list[MarkAndRetraceClient]) -> None:
            self.clients = clients
            self.vector_clock = {}
            self.message_buffer = {}
            for client in clients:
                self.vector_clock[client.client_id] = 0
                self.message_buffer[client.client_id] = []

    def __execute_operation(self, O: MarkAndRetraceOperation) -> MarkAndRetraceCharacter:
        match O:
            case MarkAndRetraceDeletionOperation():
                character = self.string.find_visible_character_at(O.position)
                character.visible = False
                character.attach_delete(O)
                return character
            case MarkAndRetraceInsertionOperation():
                start, end = self.string.get_insertion_range(O.position)
                character = MarkAndRetraceCharacter(O.client_id, O.character)
                character.attach_insert(O)
                insertion_position = self.string.range_scan(character, O.state_vector, start, end)
                self.string.insert_at(insertion_position, character)
                return character
            case _ as unreachable:
                assert_never(unreachable)

    def control_algorithm(self, O: MarkAndRetraceOperation):
        self.string.retrace(O.state_vector)
        self.__execute_operation(O)
        self.vector_clock[O.client_id] += 1
        self.string.retrace(self.vector_clock)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
    
            if len(client_message_buffer) == 0:
                return []
            
            if not self.__is_causally_ready(client_message_buffer[0]):
                return []
            
            message = client_message_buffer.pop(0)
    
            self.control_algorithm(message.operation)
    
            return [message.causing_operation]
    
