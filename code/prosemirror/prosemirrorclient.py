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
from prosemirror.prosemirrormessage import ProseMirrorMessage
from prosemirror.prosemirrorserver import ProseMirrorServer
from prosemirror.prosemirrortransform import ProseMirrorRebaseable, ProseMirrorStep, ProseMirrorTransform
from unique_char.uniquechar import UniqueChar


class ProseMirrorClient(ClientDevice):
    version: int
    unconfirmed: list[ProseMirrorRebaseable]
    client_id: int

    state: list[UniqueChar]

    server: ProseMirrorServer

    message_buffer: list[ProseMirrorMessage]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.version = 0
        self.unconfirmed = []
        self.message_buffer = []

    def set_server(self, server: ProseMirrorServer):
        self.server = server

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return len(self.message_buffer) != 0

    def can_receive_from(self) -> list[int]:
        return []

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation(_):
                return self.receive_message()
            case ClientReceiveFromClientOperation(_, _):
                return []
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def perform_local_insert(self, operation: ClientInsertOperation):
        self.perform_local_operation(
            ProseMirrorStep(operation.position, operation.position, [operation.character]), operation
        )

    def perform_local_delete(self, operation: ClientDeleteOperation):
        self.perform_local_operation(ProseMirrorStep(operation.position, operation.position + 1, []), operation)

    def receive_message(self) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if len(self.message_buffer) == 0:
            return []

        message = self.message_buffer.pop(0)

        self.receive_transaction(message.steps, [message.client_id] * len(message.steps))

        self.send_to_server()

        if message.client_id == self.client_id:
            return []
        return message.causing_operations

    def rebase_steps(
        self, steps: list[ProseMirrorRebaseable], over: list[ProseMirrorStep], transform: ProseMirrorTransform
    ) -> list[ProseMirrorRebaseable]:
        for i in range(len(steps) - 1, -1, -1):
            transform.step(steps[i].inverted)
        for i in range(len(over)):
            transform.step(over[i])
        result: list[ProseMirrorRebaseable] = []
        map_from = len(steps)
        for i in range(len(steps)):
            mapped = steps[i].step.map(transform.mapping.slice(map_from))
            map_from -= 1
            if mapped is not None and not transform.maybe_step(mapped).failed:
                transform.mapping.set_mirror(map_from, len(transform.steps) - 1)
                result.append(
                    ProseMirrorRebaseable(
                        mapped,
                        mapped.invert(transform.docs[len(transform.docs) - 1]),
                        steps[i].origin,
                        steps[i].causing_operation,
                    )
                )
        return result

    def receive_transaction(self, steps: list[ProseMirrorStep], client_ids: list[int]):
        self.version += len(steps)

        ours = 0
        while ours < len(client_ids) and client_ids[ours] == self.client_id:
            ours += 1
        self.unconfirmed = self.unconfirmed[ours:]
        steps = steps[ours:]

        if len(steps) == 0:
            return

        n_unconfirmed = len(self.unconfirmed)
        tr = ProseMirrorTransform(self.state)
        if n_unconfirmed != 0:
            self.unconfirmed = self.rebase_steps(self.unconfirmed, steps, tr)
        else:
            for i in range(len(steps)):
                tr.step(steps[i])
            self.unconfirmed = []

        self.state = tr.doc

    def unconfirmed_from(
        self, transform: ProseMirrorTransform, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ) -> list[ProseMirrorRebaseable]:
        result: list[ProseMirrorRebaseable] = []
        for i, step in enumerate(transform.steps):
            result.append(ProseMirrorRebaseable(step, step.invert(transform.docs[i]), transform, causing_operation))
        return result

    def perform_local_operation(
        self, step: ProseMirrorStep, causing_operation: ClientInsertOperation | ClientDeleteOperation
    ):
        transform = ProseMirrorTransform(self.state)
        transform.step(step)

        self.unconfirmed += self.unconfirmed_from(transform, causing_operation)
        self.state = transform.doc

        self.send_to_server()

    def send_to_server(self):
        if not self.unconfirmed:
            return

        steps = [rebaseable.step for rebaseable in self.unconfirmed]

        causing_operations = [rebaseable.causing_operation for rebaseable in self.unconfirmed]

        self.server.send_message(
            self.client_id, ProseMirrorMessage(self.client_id, self.version, steps, causing_operations)
        )

    def send_message(self, message: ProseMirrorMessage) -> None:
        self.message_buffer.append(message)
