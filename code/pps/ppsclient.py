import math
from fractions import Fraction
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
from pps.ppsmessage import PPSDeletionOperation, PPSInsertionOperation, PPSMessage, PPSOperation
from unique_char.uniquechar import UniqueChar


class PPSClient(ClientDevice):
    client_id: int

    position_stamps: list[Fraction]
    characters: dict[Fraction, UniqueChar | None]

    clients: list[PPSClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[PPSMessage]]

    def __init__(self, client_id: int):
        self.position_stamps = [Fraction(0), Fraction(1)]
        self.characters = {}
        self.characters[Fraction(0)] = None
        self.characters[Fraction(1)] = None
        self.client_id = client_id

    def set_clients(self, clients: list[PPSClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def __get_stamp_index_at_position(self, position: int) -> int:
        seen = 0
        n = 0
        while seen < position:
            n += 1
            stamp = self.position_stamps[n]
            character = self.characters[stamp]
            if character is not None:
                seen += 1
        return n

    def __new_stamp_by_subranges(self, before: Fraction, after: Fraction) -> Fraction:  # pyright: ignore[reportUnusedFunction]
        n = len(self.clients)
        return before + (after - before) * (2 * self.client_id + 1) / (2 * n)

    def __new_stamp_by_extra_digits(self, before: Fraction, after: Fraction) -> Fraction:
        midpoint = (before + after) / 2

        k1 = 0
        now = before
        while not now.is_integer():
            now *= 10
            k1 += 1

        k2 = 0
        now = after
        while not now.is_integer():
            now *= 10
            k2 += 1

        k = max(k1, k2)

        n = len(self.clients)

        extra_digits = math.ceil(math.log10(n)) + 1

        addition = Fraction(self.client_id + 1, 10 ** (k + extra_digits))

        value = midpoint + addition

        return value

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        # Find stamp at position
        stamp_before_index = self.__get_stamp_index_at_position(operation.position)

        stamp_before = self.position_stamps[stamp_before_index]
        stamp_after = self.position_stamps[stamp_before_index + 1]

        new_stamp = self.__new_stamp_by_extra_digits(stamp_before, stamp_after)

        self.position_stamps.insert(stamp_before_index + 1, new_stamp)
        self.characters[new_stamp] = operation.character

        # Send message to all other clients
        self.__send_to_other_clients(
            PPSMessage(
                self.vector_clock.copy(),
                PPSInsertionOperation(new_stamp, operation.character),
                operation,
            )
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        # Perform change to local tree
        stamp_index = self.__get_stamp_index_at_position(operation.position + 1)
        stamp = self.position_stamps[stamp_index]

        self.characters[stamp] = None

        # Send message to all other clients
        self.__send_to_other_clients(PPSMessage(self.vector_clock.copy(), PPSDeletionOperation(stamp), operation))

    def perform_remote_insert(self, stamp: Fraction, character: UniqueChar) -> None:
        # Insert into local tree, at the right index to keep ids in order
        index = 0
        while index < len(self.position_stamps) and self.position_stamps[index] < stamp:
            index += 1

        self.position_stamps.insert(index, stamp)
        self.characters[stamp] = character

    def perform_remote_delete(self, stamp: Fraction) -> None:
        self.characters[stamp] = None

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
        state: list[UniqueChar] = []
        for stamp in self.position_stamps:
            character = self.characters[stamp]
            if character is not None:
                state.append(character)
        return state

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        self.__apply_operation(message.operation)

        self.vector_clock[client_id] += 1

        return [message.causing_operation]

    def __apply_operation(self, operation: PPSOperation):
        match operation:
            case PPSInsertionOperation(stamp, char):
                self.perform_remote_insert(stamp, char)
            case PPSDeletionOperation(stamp):
                self.perform_remote_delete(stamp)
            case _ as unreachable:
                assert_never(unreachable)

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def can_receive_from_server(self) -> bool:
        return False

    def send_message(self, client_id: int, message: PPSMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: PPSMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: PPSMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
