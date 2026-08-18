from typing import assert_never

from device.clientdevice import TimeSteppedClient
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from tibot2.tibot2message import (
    TIBOT2DeletionOperation,
    TIBOT2InsertionOperation,
    TIBOT2Message,
    TIBOT2NoOperation,
    TIBOT2Operation,
)
from tibot2.tibot2transform import SLOT
from unique_char.uniquechar import UniqueChar


class TIBOT2Client(TimeSteppedClient):
    client_id: int
    state: list[UniqueChar]
    clock: int

    sequence_number: int  # Used to order messages from the same client and time_interval, I reset this back to 0 at the end of a time interval so this can be used as an index into an array.

    clients: list[TIBOT2Client]
    time_intervals_from_client: dict[
        int, list[int]
    ]  # The latest time interval that we have seen from the other clients.
    client_ids_from_time_interval: dict[int, list[int]]  # The client_ids received from each time interval.

    # A dictionary from time interval to all the operations performed in that time interval
    # Once the client has received all messages from previous time intervals, then those messages can be sent to
    # all the other clients, and that group of messages can be removed from the buffer.
    # Operation Buffer needs to be sorted by sequence number.
    operation_buffer: dict[int, list[TIBOT2Operation]]

    # List of executed operations, sorted by the total order
    history_buffer: list[TIBOT2Operation]

    # Dictionary from client_id to message.
    message_buffer: dict[int, list[TIBOT2Message]]

    causing_operations: dict[
        int, list[ClientInsertOperation | ClientDeleteOperation]
    ]  # The lcoal operation that caused this

    def __init__(self, client_id: int) -> None:
        self.client_id = client_id
        self.state = []
        self.clients = []
        self.message_buffer = {}
        self.history_buffer = []

        self.time_intervals_from_client = {}
        self.clock = 0
        self.sequence_number = 0

        self.operation_buffer = {}
        self.operation_buffer[self.clock] = []

        self.causing_operations = {}
        self.causing_operations[self.clock] = []

        self.client_ids_from_time_interval = {}
        self.client_ids_from_time_interval[self.clock] = []

    def set_clients(self, clients: list[TIBOT2Client]):
        for client in clients:
            self.clients.append(client)
            if client.client_id != self.client_id:
                self.time_intervals_from_client[client.client_id] = []
            self.message_buffer[client.client_id] = []

    def perform_local_operation(self, operation: TIBOT2Operation):
        self.__execute_operation(operation)
        self.history_buffer.append(operation)
        self.operation_buffer[self.clock].append(operation)

    def perform_local_insert(self, operation: ClientInsertOperation):
        op = TIBOT2Operation(
            self.clock,
            self.client_id,
            self.sequence_number,
            TIBOT2InsertionOperation(operation.position, operation.character),
        )
        self.sequence_number += 1
        self.perform_local_operation(op)
        self.causing_operations[self.clock].append(operation)

    def perform_local_delete(self, operation: ClientDeleteOperation):
        op = TIBOT2Operation(
            self.clock,
            self.client_id,
            self.sequence_number,
            TIBOT2DeletionOperation(operation.position, operation.character),
        )
        self.sequence_number += 1
        self.perform_local_operation(op)
        self.causing_operations[self.clock].append(operation)

    # Synchronization rule 2:
    # When I receive a message from an earlier time interval, I need to perform undo/do/redo.
    # I also need to update the operation in the operation_buffer to the new transformed operation.
    # TIBOT Control Algorithm described in the paper

    # Assume all operations in group operation have the same time_interval and client_id
    def perform_remote_group_operation(self, group_operation: list[TIBOT2Operation]):
        # First need to find all the operations preceding the group_operation in the total
        # order, i.e., all operations with a greater time interval or greater client_id.

        if len(group_operation) == 0:
            return

        L1: list[TIBOT2Operation] = []
        L2: list[TIBOT2Operation] = []
        L3: list[TIBOT2Operation] = []

        for operation in self.history_buffer:
            if operation.time_interval < group_operation[0].time_interval:
                L1.append(operation)
            elif (
                operation.time_interval == group_operation[0].time_interval
                and operation.client_id < group_operation[0].client_id
            ):
                L2.append(operation)
            else:
                L3.append(operation)

        transformed_group_operation1, _ = SLOT(group_operation, L2)
        transformed_L3, transformed_group_operation2 = SLOT(L3, transformed_group_operation1)

        self.__execute_operations(transformed_group_operation2)

        self.history_buffer = L1 + L2 + transformed_group_operation1 + transformed_L3
        self.__update_operation_buffer(group_operation[0].time_interval, transformed_L3)

    def __update_operation_buffer(self, go_time_interval: int, transformed_L3: list[TIBOT2Operation]):
        for operation in transformed_L3:
            if go_time_interval < operation.time_interval and operation.client_id == self.client_id:
                self.operation_buffer[operation.time_interval][operation.sequence_number] = operation

    def __execute_operations(self, operations: list[TIBOT2Operation]):
        for operation in operations:
            self.__execute_operation(operation)

    def __execute_operation(self, operation: TIBOT2Operation):
        match operation.operation:
            case TIBOT2InsertionOperation(position, character):
                self.state.insert(position, character)
            case TIBOT2DeletionOperation(position, character):
                del self.state[position]
            case TIBOT2NoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

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
                self.at_end_of_time_interval()
                return []
            case _ as unreachable:
                assert_never(unreachable)

    # To be called at the end of a time interval, called at a constant rate
    def at_end_of_time_interval(self) -> None:
        self.clock += 1
        self.sequence_number = 0

        self.operation_buffer[self.clock] = []
        self.causing_operations[self.clock] = []
        self.client_ids_from_time_interval[self.clock] = []
        # Check if there are messages to be sent.

        # Can we send new messages at the end of this time interval?
        # We propogate new messages, either when we receive remote messages, or at the end of the current time interval.
        # Only send messages at the end of the current time interval, if it is ready.
        # Messages from earlier time intervals will have been sent as soon as they become ready.
        time_interval = self.clock - 1

        # Propogation rule 1 says time intervals where nothing happened should be sent regardless.
        if len(self.operation_buffer[time_interval]) == 0 or self.can_send_message_from_time_interval(time_interval):
            message = TIBOT2Message(
                self.client_id,
                time_interval,
                self.operation_buffer[time_interval],
                self.causing_operations[time_interval],
            )
            self.__send_to_other_clients(message)
            del self.operation_buffer[time_interval]

    # Checks whether seen all the messages from previous time intervals
    def can_send_message_from_time_interval(self, time_interval: int) -> bool:
        for client in self.time_intervals_from_client:
            for i in range(time_interval):
                if i not in self.time_intervals_from_client[client]:
                    return False
        return True

    def __send_to_other_clients(self, message: TIBOT2Message) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def send_message(self, client_id: int, message: TIBOT2Message) -> None:
        self.message_buffer[client_id].append(message)

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return False

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if client_id not in self.can_receive_from():
            return []

        time_interval = self.__get_earliest_time_interval_sent_from(client_id)
        message = self.__pop_first_message_with_time_interval(client_id, time_interval)

        self.client_ids_from_time_interval[message.time_interval].append(message.client_id)
        self.time_intervals_from_client[message.client_id].append(message.time_interval)

        self.perform_remote_group_operation(message.group_operation)

        self.__send_buffered_operations()

        return message.causing_operations

    def __send_buffered_operations(self):
        new_operation_buffer = dict(self.operation_buffer)
        for time_interval in self.operation_buffer:
            if time_interval >= self.clock:
                continue
            if self.can_send_message_from_time_interval(time_interval):
                message = TIBOT2Message(
                    self.client_id,
                    time_interval,
                    self.operation_buffer[time_interval],
                    self.causing_operations[time_interval],
                )
                self.__send_to_other_clients(message)
                del new_operation_buffer[time_interval]
        self.operation_buffer = new_operation_buffer

    def __seen_all_messages_preceding(self, sender_client_id: int, time_interval: int) -> bool:
        # Every client has seen everything in a lower time interval.
        for client_id in self.time_intervals_from_client:
            if client_id == self.client_id:
                continue
            time_intervals = self.time_intervals_from_client[client_id]
            for i in range(time_interval):
                if i not in time_intervals:
                    return False
        # In the current time interval, every client with a lower client_id has seen it.
        clients = self.client_ids_from_time_interval[time_interval]
        return all(not (i not in clients and i != self.client_id) for i in range(sender_client_id))

    def __get_earliest_time_interval_sent_from(self, client_id: int) -> int:
        messages = self.message_buffer[client_id]
        earliest_time_interval = -1

        for message in messages:
            if earliest_time_interval == -1 or message.time_interval < earliest_time_interval:
                earliest_time_interval = message.time_interval
        return earliest_time_interval

    def __pop_first_message_with_time_interval(self, client_id: int, time_interval: int) -> TIBOT2Message:
        messages = self.message_buffer[client_id]

        first_with_time_interval = -1
        for index, message in enumerate(messages):
            if message.time_interval == time_interval:
                first_with_time_interval = index
                break
        if first_with_time_interval == -1:
            raise Exception("No message with that time interval.")

        message = messages[first_with_time_interval]
        messages.remove(message)
        return message

    # Synchronization rule 1
    def can_receive_from(self) -> list[int]:
        clients: list[int] = []
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) == 0:
                continue
            earliest_time_interval = self.__get_earliest_time_interval_sent_from(client_id)

            if self.clock > earliest_time_interval and self.__seen_all_messages_preceding(
                client_id, earliest_time_interval
            ):
                clients.append(client_id)
        return clients
