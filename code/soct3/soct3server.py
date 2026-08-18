from typing import assert_never

from device.operations import ServerOperation, ServerReceiveFromClientOperation
from device.serverdevice import ServerDevice
from soct3.soct3client import SOCT3Client
from soct3.soct3message import SOCT3Message, SOCT3TicketRequestMessage, SOCT3TicketResponseMessage


#Acts as the sequencer.
class SOCT3Server(ServerDevice):
    ticket: int 

    message_buffers: dict[int, list[SOCT3Message]]
    clients: dict[int, SOCT3Client]

    def __init__(self, clients: list[SOCT3Client]):
        self.ticket = 0
        self.clients = {}
        self.message_buffers = {}

        for client in clients:
            self.clients[client.client_id] = client
            self.message_buffers[client.client_id] = []

    def perform_operation(self, operation: ServerOperation):
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_from_client(client_id)
            case _ as unreachable:
                assert_never(unreachable)


    def receive_from_client(self, client_id: int):
        if client_id not in self.message_buffers or len(self.message_buffers[client_id]) == 0:
            return
        message = self.message_buffers[client_id].pop(0)
        self.__apply_message(message)



    def __apply_message(self, message: SOCT3Message):
        assert isinstance(message, SOCT3TicketRequestMessage)
        ticket = self.next_ticket()
        client = self.clients[message.client_id]
        client.send_server_message(SOCT3TicketResponseMessage(message.client_id, message.n, ticket, message.operation, message.causing_operation))



    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.message_buffers:
            if len(self.message_buffers[client_id]) != 0:
                client_ids.append(client_id)
        return client_ids

    def next_ticket(self) -> int:
        self.ticket += 1
        return self.ticket

    def send_message(self, client_id: int, message: SOCT3TicketRequestMessage):
        self.message_buffers[client_id].append(message)

    