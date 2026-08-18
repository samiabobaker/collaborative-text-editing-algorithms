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
from tibot.tibotmessage import (
    TIBOTDeletionOperation,
    TIBOTInsertionOperation,
    TIBOTMessage,
    TIBOTNoOperation,
    TIBOTOperation,
)
from tibot.tibottransform import SLOT, undo_TIBOT_operations
from unique_char.uniquechar import UniqueChar


class TIBOTClient(TimeSteppedClient):
    client_id: int
    state: list[UniqueChar]
    clock: int

    sequence_number: int  # Used to order messages from the same client and time_interval, I reset this back to 0 at the end of a time interval so this can be used as an index into an array.

    clients: list[TIBOTClient]
    time_intervals_from_client: dict[
        int, list[int]
    ]  # The latest time interval that we have seen from the other clients.
    client_ids_from_time_interval: dict[int, list[int]]  # The client_ids received from each time interval.

    # A dictionary from time interval to all the operations performed in that time interval
    # Once the client has received all messages from previous time intervals, then those messages can be sent to
    # all the other clients, and that group of messages can be removed from the buffer.
    # Operation Buffer needs to be sorted by sequence number.
    operation_buffer: dict[int, list[TIBOTOperation]]

    # List of executed operations, sorted by the total order
    history_buffer: list[TIBOTOperation]

    # Dictionary from client_id to message.
    message_buffer: dict[int, list[TIBOTMessage]]

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

    def set_clients(self, clients: list[TIBOTClient]):
        for client in clients:
            self.clients.append(client)
            if client.client_id != self.client_id:
                self.time_intervals_from_client[client.client_id] = []
            self.message_buffer[client.client_id] = []

    def perform_local_operation(self, operation: TIBOTOperation):
        self.__execute_operation(operation)
        self.history_buffer.append(operation)
        self.operation_buffer[self.clock].append(operation)

    def perform_local_insert(self, operation: ClientInsertOperation):
        op = TIBOTOperation(
            self.clock,
            self.client_id,
            self.sequence_number,
            TIBOTInsertionOperation(operation.position, operation.character),
        )
        self.sequence_number += 1
        self.perform_local_operation(op)
        self.causing_operations[self.clock].append(operation)

    def perform_local_delete(self, operation: ClientDeleteOperation):
        op = TIBOTOperation(
            self.clock,
            self.client_id,
            self.sequence_number,
            TIBOTDeletionOperation(operation.position, operation.character),
        )
        self.sequence_number += 1
        self.perform_local_operation(op)
        self.causing_operations[self.clock].append(operation)

    # Synchronization rule 2:
    # When I receive a message from an earlier time interval, I need to perform undo/do/redo.
    # I also need to update the operation in the operation_buffer to the new transformed operation.
    # TIBOT Control Algorithm described in the paper

    # Assume all operations in group operation have the same time_interval and client_id
    def perform_remote_group_operation(self, group_operation: list[TIBOTOperation]):
        # First need to find all the operations preceding the group_operation in the total
        # order, i.e., all operations with a greater time interval or greater client_id.

        if len(group_operation) == 0:
            return

        time_interval = group_operation[0].time_interval
        client_id = group_operation[0].client_id

        j = len(self.history_buffer)  # We want to undo self.history_buffer[j:]

        # Set j to be pointing to the first operation in the history buffer that comes after the group_operation in the total order
        for index, operation in enumerate(self.history_buffer):
            if operation.time_interval > time_interval or (
                operation.time_interval == time_interval and operation.client_id > client_id
            ):
                j = index
                break

        L_undo = self.history_buffer[
            j:
        ]  # Undo these operations, as they should include the effects of group_operation, but currently do not.
        self.state = undo_TIBOT_operations(self.state, L_undo)

        L = self.history_buffer[:j]

        i = j  # i is the first operation O_i such that TI(O_i) >= time_interval

        for index, operation in enumerate(L):
            if operation.time_interval >= time_interval:
                i = index
                break

        # All operations in L_concurrent do not include the effect of GO and all operations in GO do not include the effect of L_concurrent
        # GO includes the effect of everything before L_concurrent because of propogation rule 1.
        L_concurrent = L[i:]

        # Transform all operations in GO so that they include the effect of everything in L_concurrent
        transformed_GO = SLOT(group_operation, L_concurrent)

        # Need to make sure before propogating a message that it has not been transformed
        # with respect to messages in the same time interval.

        new_L = list(L)

        self.__execute_operations(transformed_GO)

        new_L += transformed_GO

        if L_undo != []:
            transformed_L_undo = SLOT(L_undo, transformed_GO)
            self.__execute_operations(transformed_L_undo)
            new_L += transformed_L_undo
            # Update operation buffer so that messages now include those transformations.
            self.__update_operation_buffer(group_operation[0].time_interval, transformed_L_undo)

        self.history_buffer = new_L

    def __update_operation_buffer(self, go_time_interval: int, transformed_L_undo: list[TIBOTOperation]):
        # Anything in transformed_L_undo needs to be changed in operation_buffer is time_interval of GO is less than time_interval of operation.
        for operation in transformed_L_undo:
            if go_time_interval < operation.time_interval and operation.client_id == self.client_id:
                # Update the corresponding message in the operation_buffer
                self.operation_buffer[operation.time_interval][operation.sequence_number] = operation

    def __execute_operations(self, operations: list[TIBOTOperation]):
        for operation in operations:
            self.__execute_operation(operation)

    def __execute_operation(self, operation: TIBOTOperation):
        match operation.operation:
            case TIBOTInsertionOperation(position, character):
                self.state.insert(position, character)
            case TIBOTDeletionOperation(position, character):
                del self.state[position]
            case TIBOTNoOperation():
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
            message = TIBOTMessage(
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

    def __send_to_other_clients(self, message: TIBOTMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def send_message(self, client_id: int, message: TIBOTMessage) -> None:
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
                message = TIBOTMessage(
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

    def __pop_first_message_with_time_interval(self, client_id: int, time_interval: int) -> TIBOTMessage:
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
