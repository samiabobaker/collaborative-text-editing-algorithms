from typing import TYPE_CHECKING, assert_never

from cot.cotmessage import COTMessage
from device.operations import ServerOperation, ServerReceiveFromClientOperation
from device.serverdevice import ServerDevice

if TYPE_CHECKING:
    from cot.cotclient import COTClient


class COTServer(ServerDevice):
    timestamp: int
    message_buffer: dict[int, list[COTMessage]]
    clients: list[COTClient]

    def __init__(self, clients: list[COTClient]):
        self.timestamp = 0
        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def receive_message(self, client_id: int):
        if len(self.message_buffer[client_id]) == 0:
            return

        message = self.message_buffer[client_id].pop(0)

        self.timestamp += 1

        new_message = COTMessage(message.client_id, self.timestamp, message.operation, message.causing_operation)

        for client in self.clients:
            client.send_message(new_message)

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) != 0:
                client_ids.append(client_id)
        return client_ids

    def send_message(self, client_id: int, message: COTMessage):
        self.message_buffer[client_id].append(message)
