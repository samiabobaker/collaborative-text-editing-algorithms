from typing import Literal, assert_never

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
from wooto.wootomessage import (
    WOOTODeletionOperation,
    WOOTOIdentifier,
    WOOTOInsertionOperation,
    WOOTOMessage,
)
from wooto.wootostring import (
    WOOTOCharacter,
    WOOTOString,
    WOOTOStringEntry,
    get_string_entry_id,
)


class WOOTOClient(ClientDevice):
    client_id: int
    string: WOOTOString
    clock: int

    message_buffer: dict[int, list[WOOTOMessage]]
    clients: list[WOOTOClient]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.string = WOOTOString()
        self.clock = 0

    def send_message(self, client_id: int, message: WOOTOMessage):
            self.message_buffer[client_id].append(message)

    def set_clients(self, clients: list[WOOTOClient]) -> None:
            self.clients = clients
            self.message_buffer = {}
            for client in clients:
                self.message_buffer[client.client_id] = []

    def __get_degree(self, c: WOOTOStringEntry) -> int:
        if c == 'start' or c == 'end':
            return 0
        else:
            return c.degree

    def perform_local_insert(self, operation: ClientInsertOperation):
        self.clock += 1
        prev = self.string.ith_visible(operation.position)
        next = self.string.ith_visible(operation.position + 1)

        degree = max(self.__get_degree(prev), self.__get_degree(next)) + 1

        character = WOOTOCharacter(WOOTOIdentifier(self.client_id, self.clock), operation.character, True, get_string_entry_id(prev), get_string_entry_id(next), degree)
        self.integrate_insertion(character, get_string_entry_id(prev), get_string_entry_id(next))
        self.__send_to_other_clients(WOOTOMessage(WOOTOInsertionOperation(character.id, character.character, character.prev_id, character.next_id, character.degree), operation))

    def perform_local_delete(self, operation: ClientDeleteOperation):
        character = self.string.ith_visible(operation.position + 1)
        assert character != 'start' and character != 'end'
        self.integrate_deletion(character)
        self.__send_to_other_clients(WOOTOMessage(WOOTODeletionOperation(character.id), operation))

    def __send_to_other_clients(self, message: WOOTOMessage) -> None:
            for client in self.clients:
                if client.client_id == self.client_id:
                    continue
                client.send_message(self.client_id, message)
    
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
        return self.string.read_state()

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)
        
        return client_ids

    def __is_ready(self, message: WOOTOMessage) -> bool:
        match message.operation:
            case WOOTOInsertionOperation(_, character, prev_id, next_id):
                return self.string.contains(prev_id) and self.string.contains(next_id)                
            case WOOTODeletionOperation(character):
                return self.string.contains(character)
            case _ as unreachable:
                assert_never(unreachable)


    def lt_id(self, a: WOOTOCharacter | Literal['start'] | Literal['end'], b: WOOTOCharacter | Literal['start'] | Literal['end']) -> bool:
        a_id = get_string_entry_id(a)
        b_id = get_string_entry_id(b)
        return (a_id.client_id < b_id.client_id) or (a_id.client_id == b_id.client_id and a_id.number < b_id.number)

    def integrate_deletion(self, c: WOOTOCharacter):
        c.visible = False

    def integrate_insertion(self, c: WOOTOCharacter, prev_id: WOOTOIdentifier, next_id: WOOTOIdentifier):
        prev_index = self.string.get_index_of(prev_id)
        next_index = self.string.get_index_of(next_id)

        substring = self.string.get_substring_between(prev_index, next_index)

        if len(substring) == 0:
            self.string.insert_char(next_index, c)
        else:
            i = 1 

            d_min = min([self.__get_degree(s) for s in substring])
            F : list[WOOTOStringEntry] = [self.string.string[prev_index]]

            for s in substring:
                if self.__get_degree(s) == d_min:
                    F.append(s)

            F.append(self.string.string[next_index])

            while (i < len(F) - 1) and self.lt_id(F[i], c):
                i += 1
            self.integrate_insertion(c, get_string_entry_id(F[i-1]), get_string_entry_id(F[i]))


    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
    
            if len(client_message_buffer) == 0:
                return []
            
            if not self.__is_ready(client_message_buffer[0]):
                return []
            
            message = client_message_buffer.pop(0)
    
            match message.operation:
                case WOOTODeletionOperation(character):
                    index = self.string.get_index_of(character)
                    character = self.string.string[index]
                    assert character != 'start' and character != 'end'
                    self.integrate_deletion(character)
                case WOOTOInsertionOperation(id, character, prev_id, next_id, degree):
                    self.integrate_insertion(WOOTOCharacter(id, character, True, prev_id, next_id, degree), prev_id, next_id)
                case _ as unreachable:
                    assert_never(unreachable)
            return [message.causing_operation]
