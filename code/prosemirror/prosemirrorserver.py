from typing import TYPE_CHECKING, assert_never

from device.operations import ServerOperation, ServerReceiveFromClientOperation
from device.serverdevice import ServerDevice
from prosemirror.prosemirrormessage import ProseMirrorMessage
from prosemirror.prosemirrortransform import ProseMirrorStep

if TYPE_CHECKING:
    from prosemirror.prosemirrorclient import ProseMirrorClient


class ProseMirrorServer(ServerDevice):
    steps: list[ProseMirrorStep]
    client_ids: list[int]
    message_buffer: dict[int, list[ProseMirrorMessage]]
    clients: dict[int, ProseMirrorClient]

    def __init__(self, clients: list[ProseMirrorClient]):
        self.clients = {client.client_id: client for client in clients}
        self.message_buffer = {client.client_id: [] for client in clients}
        self.steps = []
        self.client_ids = []

    def receive(self, version: int, steps: list[ProseMirrorStep], client_id: int):
        if version != len(self.steps):
            return
        self.steps += steps
        self.client_ids += [client_id] * len(steps)

    def send_message(self, client_id: int, message: ProseMirrorMessage):
        self.message_buffer[client_id].append(message)

    def can_receive_from(self) -> list[int]:
        return [cid for cid, buffer in self.message_buffer.items() if buffer]

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def receive_message(self, client_id: int) -> None:
        if client_id not in self.clients or len(self.message_buffer[client_id]) == 0:
            return

        message = self.message_buffer[client_id].pop(0)

        if message.version != len(self.steps):
            return

        self.steps += message.steps
        self.client_ids += [message.client_id] * len(message.steps)

        for client in self.clients.values():
            client.send_message(message)
