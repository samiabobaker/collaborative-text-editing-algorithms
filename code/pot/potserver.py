from device.serverdevice import ServerDevice

from pot.potmessage import POTMessage
from device.operations import ServerReceiveFromClientOperation, ServerOperation
from typing import assert_never, TYPE_CHECKING

if TYPE_CHECKING:
    from pot.potclient import POTClient

class POTServer(ServerDevice):

    to: int

    message_buffer: dict[int, list[POTMessage]]
    clients: list[POTClient]


    def __init__(self, clients: list[POTClient]):
        self.to = 0

        self.clients = clients
        self.message_buffer = {}
        for client in clients:
            self.message_buffer[client.client_id] = []


    def send_message(self, client_id: int, message: POTMessage):
        self.message_buffer[client_id].append(message)

    def receive_message(self, client_id: int):
        if len(self.message_buffer[client_id]) == 0:
            return

        message = self.message_buffer[client_id].pop(0)

        self.to += 1

        new_message = POTMessage(message.client_id, message.rto, self.to, message.operation, message.causing_operation)

        for client in self.clients:
            client.send_message(new_message)

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.message_buffer:
            if len(self.message_buffer[client_id]) != 0:
                client_ids.append(client_id)
        return client_ids
    

    def perform_operation(self, operation: ServerOperation) -> None:
            match operation:
                case ServerReceiveFromClientOperation(client_id):
                    self.receive_message(client_id)
                case _ as unreachable:
                    assert_never(unreachable)
    

        