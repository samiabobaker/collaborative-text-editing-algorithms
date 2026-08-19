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
from pot.potmessage import (
    POTDeletionOperation,
    POTInsertionOperation,
    POTMessage,
    POTNoOperation,
    POTOperation,
)
from pot.potserver import POTServer
from unique_char.uniquechar import UniqueChar


@dataclass
class TransformationPathEntry:
    operation: POTOperation
    to: int | None


class POTClient(ClientDevice):
    client_id: int
    state: list[UniqueChar]
    rto: int
    transformation_map: dict[int, list[TransformationPathEntry]]

    server: POTServer

    message_buffer: list[POTMessage]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.rto = 0
        self.state = []
        self.message_buffer = []
        self.transformation_map = {}

    def set_clients(self, clients: list[POTClient]):
        for client in clients:
            self.transformation_map[client.client_id] = []

    def set_server(self, server: POTServer):
        self.server = server

    def __execute(self, operation: POTOperation):
        match operation:
            case POTInsertionOperation(position, character):
                self.state.insert(position, character)
            case POTDeletionOperation(position):
                del self.state[position]
            case POTNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def perform_local_operation(
        self, operation: POTOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ):
        # Step 1
        self.__execute(operation)

        # Step 2
        message = POTMessage(
            self.client_id, self.rto, -1, operation, causing_operation
        )  # TO will be assigned by the server

        # step 3
        for client_id in self.transformation_map:
            self.transformation_map[client_id].append(TransformationPathEntry(operation, None))

        # step 4
        self.server.send_message(self.client_id, message)

    def send_message(self, message: POTMessage):
        self.message_buffer.append(message)

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_operation(
                    POTInsertionOperation(operation.position, operation.character, self.client_id), operation
                )
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_operation(POTDeletionOperation(operation.position), operation)
                return [operation]
            case ClientReceiveFromServerOperation():
                return self.receive_from_server()
            case ClientReceiveFromClientOperation(_, _):
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def can_receive_from(self) -> list[int]:
        return []

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def set_timestamp_in_transformation_path(self, to: int):
        for client_id in self.transformation_map:
            for operation in self.transformation_map[client_id]:
                if operation.to is None:
                    operation.to = to
                    break

    def receive_from_server(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if not self.can_receive_from_server():
            return []

        message = self.message_buffer.pop(0)

        # The message is just a notification of the value of TO
        if message.client_id == self.client_id:
            self.set_timestamp_in_transformation_path(message.to)

            return []

        transformation_path = self.transformation_map[message.client_id]

        L1: list[TransformationPathEntry] = []
        L2: list[TransformationPathEntry] = []

        for operation in transformation_path:
            if operation.to is not None and operation.to <= message.rto:
                continue

            if operation.to is not None and message.rto < operation.to and operation.to < message.to:
                L1.append(operation)
            else:
                L2.append(operation)

        transformed_operation1, transformed_L1 = self.SLT(message.operation, [i.operation for i in L1])
        transformed_operation2, transformed_L2 = self.SLT(transformed_operation1, [i.operation for i in L2])

        self.__execute(transformed_operation2)

        self.rto = max(self.rto, message.to)

        for entry, transformed_operation in zip(L1, transformed_L1, strict=True):
            entry.operation = transformed_operation

        for entry, transformed_operation in zip(L2, transformed_L2, strict=True):
            entry.operation = transformed_operation

        for k in self.transformation_map:
            if k == message.client_id:
                continue

            transformation_path = self.transformation_map[k]

            index = 0

            while index < len(transformation_path):
                entry_to = transformation_path[index].to
                if entry_to is None or entry_to >= message.to:
                    break
                index += 1

            transformation_path[index:] = [TransformationPathEntry(operation, None) for operation in transformed_L2]

            transformation_path.insert(index, TransformationPathEntry(transformed_operation1, message.to))

        return [message.causing_operation]

    def SLT(self, operation: POTOperation, sequence: list[POTOperation]) -> tuple[POTOperation, list[POTOperation]]:
        transformed_op = operation
        transformed_sequence: list[POTOperation] = []
        for sequence_op in sequence:
            transformed_sequence.append(self.T(sequence_op, transformed_op))
            transformed_op = self.T(transformed_op, sequence_op)
        return transformed_op, transformed_sequence

    def T(self, O1: POTOperation, O2: POTOperation) -> POTOperation:
        match O1, O2:
            case POTInsertionOperation(i, x, id1), POTInsertionOperation(j, _, id2):
                if i < j:
                    return POTInsertionOperation(i, x, id1)
                elif i > j:
                    return POTInsertionOperation(i + 1, x, id1)
                elif id1 < id2:
                    return POTInsertionOperation(i, x, id1)
                else:
                    return POTInsertionOperation(i + 1, x, id1)
            case POTInsertionOperation(i, x, id1), POTDeletionOperation(j):
                if i <= j:
                    return POTInsertionOperation(i, x, id1)
                else:
                    return POTInsertionOperation(i - 1, x, id1)
            case POTDeletionOperation(i), POTInsertionOperation(j, _):
                if i < j:
                    return POTDeletionOperation(i)
                else:
                    return POTDeletionOperation(i + 1)
            case POTDeletionOperation(i), POTDeletionOperation(j):
                if i > j:
                    return POTDeletionOperation(i - 1)
                elif i < j:
                    return POTDeletionOperation(i)
                else:
                    return POTNoOperation()
            case POTNoOperation(), _:
                return O1
            case _, POTNoOperation():
                return O1
            case _ as unreachable:
                assert_never(unreachable)
