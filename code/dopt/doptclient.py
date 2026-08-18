from dataclasses import dataclass
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
from dopt.doptmessage import (
    dOPTDeletionOperation,
    dOPTInsertionOperation,
    dOPTMessage,
    dOPTNoOperation,
    dOPTOperation,
)
from dopt.dopttransform import dOPTTransform
from unique_char.uniquechar import UniqueChar


@dataclass
class dOPTRequestLogEntry:
    client_id: int
    vector_clock: dict[int, int]  # The state vector before the operation was executed.
    operation: dOPTOperation
    priority: int


class dOPTClient(ClientDevice):
    client_id: int
    clients: list[dOPTClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[dOPTMessage]]
    request_log: list[dOPTRequestLogEntry]

    state: list[UniqueChar]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.request_log = []

    def set_clients(self, clients: list[dOPTClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return False

    def __is_causally_ready(self, message: dOPTMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def __insert_character(self, position: int, character: UniqueChar) -> None:
        self.state = self.state[:position] + [character] + self.state[position:]

    def __delete_character(self, position: int) -> None:
        del self.state[position]

    def __apply_operation(self, operation: dOPTOperation) -> None:
        match operation:
            case dOPTInsertionOperation(_, position, character):
                self.__insert_character(position, character)
            case dOPTDeletionOperation(_, position):
                self.__delete_character(position)
            case dOPTNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def send_message(self, client_id: int, message: dOPTMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: dOPTMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def __perform_local_operation(
        self, operation: dOPTOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        self.request_log.append(
            dOPTRequestLogEntry(self.client_id, self.vector_clock.copy(), operation, operation.priority)
        )

        self.__apply_operation(operation)

        message = dOPTMessage(self.client_id, dict(self.vector_clock), operation, causing_operation)

        self.__send_to_other_clients(message)

        self.vector_clock[self.client_id] += 1

    def __get_most_recent_entry_leq(self, vector_clock: dict[int, int]) -> int:
        index = -1

        for i in range(len(self.request_log) - 1, -1, -1):
            if self.__vector_clock_leq(self.request_log[i].vector_clock, vector_clock):
                index = i
                break

        return index

    def __vector_clock_leq(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return all(v1[client_id] <= v2[client_id] for client_id in v1)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        log_index = self.__get_most_recent_entry_leq(message.vector_clock)

        transformed_operation = message.operation

        while log_index != -1 and log_index < len(self.request_log):
            log_entry = self.request_log[log_index]

            if message.vector_clock[log_entry.client_id] <= log_entry.vector_clock[log_entry.client_id]:
                transformed_operation = dOPTTransform.transform_dOPT_operation(
                    transformed_operation, log_entry.operation
                )
                if isinstance(transformed_operation, dOPTNoOperation):
                    break
            log_index += 1

        self.__apply_operation(transformed_operation)

        self.request_log.append(
            dOPTRequestLogEntry(
                message.client_id, self.vector_clock.copy(), transformed_operation, transformed_operation.priority
            )
        )
        self.vector_clock[message.client_id] += 1

        return [message.causing_operation]

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.__perform_local_operation(
            dOPTInsertionOperation(self.client_id, operation.position, operation.character), operation
        )

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.__perform_local_operation(dOPTDeletionOperation(self.client_id, operation.position), operation)

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
