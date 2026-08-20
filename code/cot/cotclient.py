from dataclasses import replace
from typing import assert_never

from cot.cotmessage import COTDeleteOperation, COTInsertOperation, COTMessage, COTNoOperation, COTOperation
from cot.cotserver import COTServer
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


class COTClient(ClientDevice):
    client_id: int
    message_buffer: list[COTMessage]
    server: COTServer
    context_vector: dict[
        int, int
    ]  # COT uses the term context vector, but this is the same as state vectors and vector clocks

    state: list[UniqueChar]
    document_state: list[
        COTOperation
    ]  # Operations ordered by the server timestamp, with local operations that have unknown timestamp at the end.
    versions: dict[tuple[tuple[int, int], tuple[int, ...]], COTOperation]
    client_ids: list[int]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.message_buffer = []
        self.state = []
        self.document_state = []
        self.versions = {}

    def set_server(self, server: COTServer):
        self.server = server

    def set_clients(self, clients: list[COTClient]):
        self.context_vector = {}
        for client in clients:
            self.context_vector[client.client_id] = 0
        self.client_ids = sorted(self.context_vector)

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def happened_before(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return all(v1[client_id] <= v2[client_id] for client_id in v1)

    def concurrent(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return not self.happened_before(v1, v2) and not self.happened_before(v2, v1)

    def in_context(self, context_vector: dict[int, int], O: COTOperation) -> bool:
        return context_vector[O.client_id] > O.context_vector[O.client_id]

    def difference(self, target: dict[int, int], source: dict[int, int]) -> list[COTOperation]:
        return [O for O in self.document_state if self.in_context(target, O) and not self.in_context(source, O)]

    def version_key(self, O: COTOperation, target: dict[int, int]) -> tuple[tuple[int, int], tuple[int, ...]]:
        return ((O.client_id, O.context_vector[O.client_id]), tuple(target[client_id] for client_id in self.client_ids))

    # In Sun's paper, contextualise(O, target) = transform(O, target - C(O)).
    def contextualise(self, O: COTOperation, target: dict[int, int]) -> COTOperation:
        key = self.version_key(O, target)
        cached = self.versions.get(key)
        if cached is not None:
            return cached
        transformed_O = O
        context_vector = O.context_vector.copy()
        for O_x in self.difference(target, O.context_vector):
            contextualised_O_x = self.contextualise(O_x, context_vector)
            transformed_O = self.IT(transformed_O, contextualised_O_x)
            context_vector[O_x.client_id] += 1
        self.versions[key] = transformed_O
        return transformed_O

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.local_integrate(
                    COTOperation(
                        self.client_id,
                        self.context_vector.copy(),
                        None,
                        COTInsertOperation(operation.position, operation.character),
                    ),
                    operation,
                )
                return [operation]
            case ClientDeleteOperation():
                self.local_integrate(
                    COTOperation(
                        self.client_id, self.context_vector.copy(), None, COTDeleteOperation(operation.position)
                    ),
                    operation,
                )
                return [operation]
            case ClientReceiveFromServerOperation():
                return self.receive_from_server()
            case ClientReceiveFromClientOperation():
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def can_receive_from(self) -> list[int]:
        return []

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def execute(self, O: COTOperation):
        match O.operation:
            case COTInsertOperation(position, character):
                self.state.insert(position, character)
            case COTDeleteOperation(position):
                del self.state[position]
            case COTNoOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def remote_integrate(self, O: COTOperation):
        transformed_O = O
        context_vector = O.context_vector.copy()
        for O_x in self.difference(self.context_vector, O.context_vector):
            contextualised_O_x = self.contextualise(O_x, context_vector)
            transformed_O = self.IT(transformed_O, contextualised_O_x)
            context_vector[O_x.client_id] += 1
        self.execute(transformed_O)
        self.add_to_document_state(O)
        self.context_vector[O.client_id] += 1

    def local_integrate(self, O: COTOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation):
        self.execute(O)
        self.document_state.append(O)
        self.server.send_message(self.client_id, COTMessage(self.client_id, None, O, causing_operation))
        self.context_vector[self.client_id] += 1

    def update_timestamp(self, timestamp: int):
        for operation in self.document_state:
            if operation.timestamp is None:
                operation.timestamp = timestamp
                break

    def receive_from_server(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if len(self.message_buffer) == 0:
            return []

        message = self.message_buffer.pop(0)

        assert message.timestamp is not None

        if message.client_id == self.client_id:
            self.update_timestamp(message.timestamp)
        else:
            self.remote_integrate(replace(message.operation, timestamp=message.timestamp))

        return [message.causing_operation]

    def add_to_document_state(self, O: COTOperation):
        index = 0
        while index < len(self.document_state):
            timestamp = self.document_state[index].timestamp
            if timestamp is None or (O.timestamp is not None and timestamp > O.timestamp):
                break
            index += 1
        self.document_state.insert(index, O)

    def send_message(self, message: COTMessage):
        self.message_buffer.append(message)

    def LT(self, O: COTOperation, L: list[COTOperation]) -> COTOperation:
        transformed_O = O
        for operation in L:
            transformed_O = self.IT(transformed_O, operation)
        return transformed_O

    def IT(self, O1: COTOperation, O2: COTOperation) -> COTOperation:
        match O1.operation, O2.operation:
            case COTInsertOperation(i, x), COTInsertOperation(j, _):
                if i < j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i, x))
                elif i > j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i + 1, x))
                elif O1.client_id < O2.client_id:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i, x))
                else:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i + 1, x))
            case COTInsertOperation(i, x), COTDeleteOperation(j):
                if i <= j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i, x))
                else:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTInsertOperation(i - 1, x))
            case COTDeleteOperation(i), COTInsertOperation(j, _):
                if i < j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTDeleteOperation(i))
                else:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTDeleteOperation(i + 1))
            case COTDeleteOperation(i), COTDeleteOperation(j):
                if i > j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTDeleteOperation(i - 1))
                elif i < j:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTDeleteOperation(i))
                else:
                    return COTOperation(O1.client_id, O1.context_vector, O1.timestamp, COTNoOperation())
            case COTNoOperation(), _:
                return O1
            case _, COTNoOperation():
                return O1
            case _ as unreachable:
                assert_never(unreachable)
