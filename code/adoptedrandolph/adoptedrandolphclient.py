from typing import assert_never

from adoptedrandolph.adoptedrandolphmessage import (
    AdOPTedRandolphCharacter,
    AdOPTedRandolphDeletionOperation,
    AdOPTedRandolphInsertionOperation,
    AdOPTedRandolphMessage,
    AdOPTedRandolphNoOperation,
    AdOPTedRandolphOperation,
)
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


class AdOPTedRandolphClient(ClientDevice):
    client_id: int

    clients: list[AdOPTedRandolphClient]

    message_buffer: dict[int, list[AdOPTedRandolphMessage]]

    state: list[AdOPTedRandolphCharacter]
    local_request_count: int

    vector_clock: dict[int, int]

    interaction_model: dict[tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]], AdOPTedRandolphOperation]

    request_log: dict[int, list[AdOPTedRandolphMessage]]

    operations_performed_on_document: list[AdOPTedRandolphInsertionOperation | AdOPTedRandolphDeletionOperation]

    counter: int

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.local_request_count = 0
        self.interaction_model = {}
        self.operations_performed_on_document = []
        self.counter = 0

    def set_clients(self, clients: list[AdOPTedRandolphClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        self.request_log = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []
            self.request_log[client.client_id] = []

    def __insert_character(self, position: int, character: AdOPTedRandolphCharacter) -> None:
        self.state = self.state[:position] + [character] + self.state[position:]

    def __delete_character(self, position: int) -> None:
        del self.state[position]

    def __apply_operation(self, operation: AdOPTedRandolphOperation) -> None:
        match operation:
            case AdOPTedRandolphInsertionOperation(position, character):
                self.__insert_character(position, character)
            case AdOPTedRandolphDeletionOperation(position):
                self.__delete_character(position)
            case AdOPTedRandolphNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)
        if not isinstance(operation, AdOPTedRandolphNoOperation):
            self.operations_performed_on_document.append(operation)

    def __perform_local_operation(
        self, operation: AdOPTedRandolphOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> None:
        self.__apply_operation(operation)

        message = AdOPTedRandolphMessage(self.client_id, dict(self.vector_clock), operation, causing_operation)

        self.__send_to_other_clients(message)

        self.request_log[self.client_id].append(message)
        self.vector_clock[self.client_id] += 1

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.counter += 1
        character = AdOPTedRandolphCharacter(operation.character, self.client_id, self.counter)
        self.__perform_local_operation(
            AdOPTedRandolphInsertionOperation(
                operation.position,
                character,
                self.compute_ND(self.operations_performed_on_document, operation.position),
                self.vector_clock.copy(),
            ),
            operation,
        )
        # self.__perform_local_operation(AdOPTedInsertionOperation(operation.position, operation.character), operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.__perform_local_operation(
            AdOPTedRandolphDeletionOperation(operation.position, self.vector_clock.copy()),
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
        self,
        client_id: int,
        operation: AdOPTedRandolphOperation,
        source_clock: dict[int, int],
        dest_clock: dict[int, int],
    ) -> AdOPTedRandolphOperation:
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

        final_r, final_r_i = self.apply_transform(transformed_r, transformed_r_i)

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
        return [c.character for c in self.state]

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

    def send_message(self, client_id: int, message: AdOPTedRandolphMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: AdOPTedRandolphMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        # self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: AdOPTedRandolphMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True

    def compute_ND(
        self, S: list[AdOPTedRandolphInsertionOperation | AdOPTedRandolphDeletionOperation], inserting_position: int
    ) -> int:
        if len(S) == 0:
            return 0

        S2 = list(S)
        last = S2.pop()

        match last:
            case AdOPTedRandolphInsertionOperation(position, _, num_deletions):
                if inserting_position < position:
                    return self.compute_ND(S2, inserting_position)
                elif inserting_position == position:
                    return num_deletions
                else:
                    return self.compute_ND(S2, inserting_position - 1)
            case AdOPTedRandolphDeletionOperation(position):
                if inserting_position < position:
                    return self.compute_ND(S2, inserting_position)
                else:
                    return self.compute_ND(S2, inserting_position + 1) + 1

    def apply_transform(
        self, O1: AdOPTedRandolphOperation, O2: AdOPTedRandolphOperation
    ) -> tuple[AdOPTedRandolphOperation, AdOPTedRandolphOperation]:
        return self.IT(O1, O2), self.IT(O2, O1)

    def IT(self, O1: AdOPTedRandolphOperation, O2: AdOPTedRandolphOperation) -> AdOPTedRandolphOperation:
        match O1, O2:
            case AdOPTedRandolphInsertionOperation(p1, c1, nd1, v1), AdOPTedRandolphInsertionOperation(p2, c2, nd2):
                if p1 < p2 or (p1 == p2 and nd1 < nd2) or (p1 == p2 and nd1 == nd2 and c1.less_than(c2)):
                    return AdOPTedRandolphInsertionOperation(p1, c1, nd1, v1)
                else:
                    return AdOPTedRandolphInsertionOperation(p1 + 1, c1, nd1, v1)
            case AdOPTedRandolphInsertionOperation(p1, c1, nd1, v1), AdOPTedRandolphDeletionOperation(p2):
                if p1 <= p2:
                    return AdOPTedRandolphInsertionOperation(p1, c1, nd1, v1)
                else:
                    return AdOPTedRandolphInsertionOperation(p1 - 1, c1, nd1 + 1, v1)
            case AdOPTedRandolphDeletionOperation(p1, v1), AdOPTedRandolphInsertionOperation(p2, c2, nd2):
                if p1 < p2:
                    return AdOPTedRandolphDeletionOperation(p1, v1)
                else:
                    return AdOPTedRandolphDeletionOperation(p1 + 1, v1)
            case AdOPTedRandolphDeletionOperation(p1, v1), AdOPTedRandolphDeletionOperation(p2):
                if p1 < p2:
                    return AdOPTedRandolphDeletionOperation(p1, v1)
                elif p1 > p2:
                    return AdOPTedRandolphDeletionOperation(p1 - 1, v1)
                else:
                    return AdOPTedRandolphNoOperation()
            case _, AdOPTedRandolphNoOperation():
                return O1
            case AdOPTedRandolphNoOperation(), _:
                return O1
            case _ as unreachable:
                assert_never(unreachable)
