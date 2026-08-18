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
from woot.wootmessage import WOOTDeletionOperation, WOOTInsertionOperation, WOOTMessage
from woot.wootstring import (
    WOOTCharacter,
    WOOTIdentifier,
    WOOTString,
    WOOTStringEntry,
    get_string_entry_id,
)


class WOOTClient(ClientDevice):
    client_id: int
    string: WOOTString
    clock: int

    message_buffer: dict[int, list[WOOTMessage]]
    clients: list[WOOTClient]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.string = WOOTString()
        self.clock = 0

    def send_message(self, client_id: int, message: WOOTMessage):
        self.message_buffer[client_id].append(message)

    def set_clients(self, clients: list[WOOTClient]) -> None:
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation: ClientInsertOperation):
        self.clock += 1
        prev = self.string.ith_visible(operation.position)
        next = self.string.ith_visible(operation.position + 1)
        character = WOOTCharacter(
            WOOTIdentifier(self.client_id, self.clock),
            operation.character,
            True,
            get_string_entry_id(prev),
            get_string_entry_id(next),
        )
        self.integrate_insertion(character, get_string_entry_id(prev), get_string_entry_id(next))
        self.__send_to_other_clients(
            WOOTMessage(
                WOOTInsertionOperation(character.id, character.character, character.prev_id, character.next_id),
                operation,
            )
        )

    def perform_local_delete(self, operation: ClientDeleteOperation):
        character = self.string.ith_visible(operation.position + 1)
        assert character != "start" and character != "end"
        self.integrate_deletion(character)
        self.__send_to_other_clients(WOOTMessage(WOOTDeletionOperation(character.id), operation))

    def __send_to_other_clients(self, message: WOOTMessage) -> None:
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

    def __is_ready(self, message: WOOTMessage) -> bool:
        match message.operation:
            case WOOTInsertionOperation(_, character, prev_id, next_id):
                return self.string.contains(prev_id) and self.string.contains(next_id)
            case WOOTDeletionOperation(character):
                return self.string.contains(character)
            case _ as unreachable:
                assert_never(unreachable)

    def lt_id(
        self, a: WOOTCharacter | Literal["start"] | Literal["end"], b: WOOTCharacter | Literal["start"] | Literal["end"]
    ) -> bool:
        a_id = get_string_entry_id(a)
        b_id = get_string_entry_id(b)
        return (a_id.client_id < b_id.client_id) or (a_id.client_id == b_id.client_id and a_id.number < b_id.number)

    def integrate_deletion(self, c: WOOTCharacter):
        c.visible = False

    def integrate_insertion(self, c: WOOTCharacter, prev_id: WOOTIdentifier, next_id: WOOTIdentifier):
        prev_index = self.string.get_index_of(prev_id)
        next_index = self.string.get_index_of(next_id)

        substring = self.string.get_substring_between(prev_index, next_index)

        if len(substring) == 0:
            self.string.insert_char(next_index, c)
        else:
            # Construct L
            L: list[WOOTStringEntry] = [self.string.string[prev_index]]
            for character in substring:
                assert character != "start" and character != "end"
                if self.string.less_than_or_equal_to(character.prev_id, prev_id) and self.string.less_than_or_equal_to(
                    next_id, character.next_id
                ):
                    L.append(character)
            L.append(self.string.string[next_index])

            i = 1
            while (i < len(L) - 1) and self.lt_id(L[i], c):
                i = i + 1
            self.integrate_insertion(c, get_string_entry_id(L[i - 1]), get_string_entry_id(L[i]))

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        match message.operation:
            case WOOTDeletionOperation(character):
                index = self.string.get_index_of(character)
                character = self.string.string[index]
                assert character != "start" and character != "end"
                self.integrate_deletion(character)
            case WOOTInsertionOperation(id, character, prev_id, next_id):
                self.integrate_insertion(WOOTCharacter(id, character, True, prev_id, next_id), prev_id, next_id)
            case _ as unreachable:
                assert_never(unreachable)
        return [message.causing_operation]
