from typing import assert_never

from adoptedtombstone.adoptedtombstonemessage import (
    AdOPTedMessage,
    AdOPTedTombstoneDeletionOperation,
    AdOPTedTombstoneInsertionOperation,
    AdOPTedTombstoneNoOperation,
    AdOPTedTombstoneOperation,
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


class AdOPTedTombstoneClient(ClientDevice):
    client_id: int

    clients: list[AdOPTedTombstoneClient]

    message_buffer: dict[int, list[AdOPTedMessage]]

    state: list[tuple[UniqueChar, bool]]
    local_request_count: int

    vector_clock: dict[int, int]

    interaction_model: dict[tuple[dict[int,int], dict[int,int]], AdOPTedTombstoneOperation]
    
    request_log: dict[int, list[AdOPTedMessage]]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.local_request_count = 0
        self.interaction_model = {}


    def set_clients(self, clients: list[AdOPTedTombstoneClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        self.request_log = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []
            self.request_log[client.client_id] = []

    def __insert_character(self, position: int, character: UniqueChar) -> None:
        self.state = self.state[:position] + [(character, True)] + self.state[position:]

    def __delete_character(self, position:int) -> None:
        self.state[position] = (self.state[position][0], False)

    def __apply_operation(self, operation: AdOPTedTombstoneOperation) -> None:
        match operation:
            case AdOPTedTombstoneInsertionOperation(position, character):
                self.__insert_character(position, character)
            case AdOPTedTombstoneDeletionOperation(position):
                self.__delete_character(position)
            case AdOPTedTombstoneNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)


    def __perform_local_operation(self, operation: AdOPTedTombstoneOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation) -> None:
        self.__apply_operation(operation)

        message = AdOPTedMessage(self.client_id, dict(self.vector_clock), operation, causing_operation)

        self.__send_to_other_clients(message)
        self.request_log[self.client_id].append(message)
        self.vector_clock[self.client_id] += 1


    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        model_position = self.view_to_model(operation.position)
        self.__perform_local_operation(AdOPTedTombstoneInsertionOperation(model_position, operation.character, self.client_id), operation)

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        model_position = self.view_to_model(operation.position)
        self.__perform_local_operation(AdOPTedTombstoneDeletionOperation(model_position, self.client_id), operation)

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

    def __transform_operation(self, client_id: int, operation: AdOPTedTombstoneOperation, source_clock: dict[int, int], dest_clock: dict[int, int]) -> AdOPTedTombstoneOperation:
        if source_clock == dest_clock:
            self.interaction_model[(self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))] = operation
            return operation
        
        if (self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id))) in self.interaction_model:
            return self.interaction_model[(self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))]
        
        #Find a predecessor state.

        predecessor: dict[int, int] | None = None
        user: int | None = None

        for client in self.clients:
            #Check that I can decrement from this user.
            if source_clock[client.client_id] > dest_clock[client.client_id] - 1:
                continue

            #Check this is in the interaction model
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

        final_r, final_r_i = self.__apply_transform(transformed_r, transformed_r_i)

        self.interaction_model[(self.to_dict_key(dest_clock), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))] = final_r
        self.interaction_model[(self.to_dict_key(self.__get_resulting_clock(predecessor, client_id)), self.to_dict_key(self.__get_resulting_clock(dest_clock, client_id)))] = final_r_i

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
        return [character for character,visible in self.state if visible]

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        #Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []
        
        if not self.__is_causally_ready(client_message_buffer[0]):
            return []
        
        message = client_message_buffer.pop(0)

        transformed_operation = self.__transform_operation(client_id, message.operation, message.vector_clock, self.vector_clock)

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
        #self.vector_clock[self.client_id] += 1

    def __is_causally_ready(self, message: AdOPTedMessage) -> bool:
        for client in self.clients:
            if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True
    
    def __apply_transform(self, O1: AdOPTedTombstoneOperation, O2: AdOPTedTombstoneOperation) -> tuple[AdOPTedTombstoneOperation, AdOPTedTombstoneOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def __transform(self, O1: AdOPTedTombstoneOperation, O2: AdOPTedTombstoneOperation) -> AdOPTedTombstoneOperation:
        match O1, O2:
            case AdOPTedTombstoneInsertionOperation(i, x, pr1), AdOPTedTombstoneInsertionOperation(j, y, pr2):
                if i < j or i == j and pr1 < pr2:
                    return AdOPTedTombstoneInsertionOperation(i, x, pr1)
                else:
                    return AdOPTedTombstoneInsertionOperation(i+1,x,pr1)
            case AdOPTedTombstoneDeletionOperation(i, pr1), AdOPTedTombstoneInsertionOperation(j, y):
                 if i < j:
                     return AdOPTedTombstoneDeletionOperation(i, pr1)
                 else:
                     return AdOPTedTombstoneDeletionOperation(i + 1, pr1)
            case AdOPTedTombstoneInsertionOperation(i, x, pr1), AdOPTedTombstoneDeletionOperation(j, pr2):
                return AdOPTedTombstoneInsertionOperation(i, x, pr1)
            case AdOPTedTombstoneDeletionOperation(i, pr1), AdOPTedTombstoneDeletionOperation(j, pr2):
                return AdOPTedTombstoneDeletionOperation(i, pr1)
            case AdOPTedTombstoneNoOperation(), _:
                return AdOPTedTombstoneNoOperation()
            case oper, AdOPTedTombstoneNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)

    def view_to_model(self, pview: int) -> int:
        n = 0
        j = 0
        while j < len(self.state) and (n<pview or not self.state[j][1]):
            if self.state[j][1]:
                n += 1
            j += 1
        return j



