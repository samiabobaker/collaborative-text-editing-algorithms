from typing import assert_never

from adopted.adoptedmessage import (
    AdOPTedDeletionOperation,
    AdOPTedInsertionOperation,
    AdOPTedMessage,
    AdOPTedNoOperation,
    AdOPTedOperation,
)
from adopted.adoptedtransform import AdOPTedTransform
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


class AdOPTedClient(ClientDevice):
    client_id: int

    clients: list[AdOPTedClient]

    message_buffer: dict[int, list[AdOPTedMessage]]

    state: list[UniqueChar]
    local_request_count: int

    vector_clock: dict[int, int]

    interaction_model: dict[tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]], AdOPTedOperation]

    request_log: dict[int, list[AdOPTedMessage]]

    transformations: AdOPTedTransform

    def __init__(self, client_id: int, transform: AdOPTedTransform):
        self.client_id = client_id
        self.state = []
        self.local_request_count = 0
        self.interaction_model = {}
        self.transformations = transform

    def set_clients(self, clients: list[AdOPTedClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        self.request_log = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []
            self.request_log[client.client_id] = []

    def __insert_character(self, position: int, character: UniqueChar) -> None:
        self.state = self.state[:position] + [character] + self.state[position:]

    def __delete_character(self, position: int) -> None:
        del self.state[position]

    def __apply_operation(self, operation: AdOPTedOperation) -> None:
        match operation:
            case AdOPTedInsertionOperation(position, character):
                self.__insert_character(position, character)
            case AdOPTedDeletionOperation(position):
                self.__delete_character(position)
            case AdOPTedNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def __perform_local_operation(
        self, operation: AdOPTedOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        self.__apply_operation(operation)

        message = AdOPTedMessage(self.client_id, dict(self.vector_clock), operation, causing_operation)

        self.__send_to_other_clients(message)

        self.request_log[self.client_id].append(message)
        self.vector_clock[self.client_id] += 1

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.__perform_local_operation(
            self.transformations.get_insert_with_priority(
                operation.position, operation.character, self.client_id, dict(self.vector_clock)
            ),
            operation,
        )
        # self.__perform_local_operation(AdOPTedInsertionOperation(operation.position, operation.character), operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.__perform_local_operation(
            self.transformations.get_delete_with_priority(operation.position, self.client_id, dict(self.vector_clock)),
            operation,
        )
        # self.__perform_local_operation(AdOPTedDeletionOperation(operation.position), operation)

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

    def __transform_operation(
        self, client_id: int, operation: AdOPTedOperation, source_clock: dict[int, int], dest_clock: dict[int, int]
    ) -> AdOPTedOperation:
        if source_clock == dest_clock:
            self.interaction_model[
                (self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))
            ] = operation
            return operation

        if (
            self.to_dict_key(dest_clock),
            self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)),
        ) in self.interaction_model:
            return self.interaction_model[
                (self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))
            ]

        # Find a predecessor state.

        predecessor: dict[int, int] | None = None
        user: int | None = None

        for client in self.clients:
            # Check that I can decrement from this user.
            if source_clock[client.client_id] > dest_clock[client.client_id] - 1:
                continue

            # Check this is in the interaction model
            predecessor_clock = dict(dest_clock)
            predecessor_clock[client.client_id] -= 1

            if self.__clock_is_reachable(predecessor_clock):
                predecessor = predecessor_clock
                user = client.client_id
                break

        assert predecessor is not None
        assert user is not None

        r_i = self.request_log[user][dest_clock[user] - 1]

        transformed_r_i = self.__transform_operation(r_i.client_id, r_i.operation, r_i.vector_clock, predecessor)

        transformed_r = self.__transform_operation(client_id, operation, source_clock, predecessor)

        final_r, final_r_i = self.transformations.apply_transform(transformed_r, transformed_r_i)

        self.interaction_model[
            (self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))
        ] = final_r
        self.interaction_model[
            (
                self.to_dict_key(self.__get_resulting_clock(predecessor, client_id)),
                self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)),
            )
        ] = final_r_i

        return final_r

    def to_dict_key(self, clock: dict[int, int]):
        return tuple(sorted(clock.items()))

    def __get_resulting_clock(self, clock: dict[int, int], client_id: int) -> dict[int, int]:
        result = dict(clock)
        result[client_id] += 1
        return result

    def __clock_is_reachable(self, clock: dict[int, int]) -> bool:
        for client_id in clock:
            if clock[client_id] == 0:
                continue

            request = self.request_log[client_id][clock[client_id] - 1]

            request_clock = dict(request.vector_clock)
            request_clock[client_id] += 1

            for client_id2 in request_clock:
                if request_clock[client_id2] > clock[client_id2]:
                    return False
        return True

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        transformed_operation = self.__transform_operation(
            client_id, message.operation, message.vector_clock, self.vector_clock
        )

        self.__apply_operation(transformed_operation)

        self.request_log[client_id].append(message)
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

    def send_message(self, client_id: int, message: AdOPTedMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: AdOPTedMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        # self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: AdOPTedMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
