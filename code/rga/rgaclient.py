from device.clientdevice import ClientDevice
from device.operations import (
    ClientOperation,
    ClientInsertOperation,
    ClientDeleteOperation,
    ClientReceiveFromServerOperation,
    ClientReceiveFromClientOperation,
    ClientTimestepOperation,
)
from rga.rgatree import RGATree
from rga.rgamessage import RGAOperation, RGADeletionOperation, RGAInsertionOperation, RGAMessage
from unique_char.uniquechar import UniqueChar

class RGAClient(ClientDevice):
    client_id : int

    clients: list[RGAClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[RGAMessage]]
    tree : RGATree


    def __init__(self, client_id: int):
        self.client_id = client_id
        self.tree = RGATree(self.client_id)

    def set_clients(self, clients: list[RGAClient]) -> None:
            self.clients = clients
            self.vector_clock = {}
            self.message_buffer = {}
            for client in clients:
                self.vector_clock[client.client_id] = 0
                self.message_buffer[client.client_id] = []

    def perform_local_insert(self, operation : ClientInsertOperation):
        node = self.tree.insert_char(operation.character, operation.position)
        self.__send_to_other_clients(RGAMessage(self.vector_clock.copy(), RGAInsertionOperation(node.timestamp, node.parent, operation.character), operation))

    def perform_local_delete(self, operation : ClientDeleteOperation):
        node = self.tree.delete_char_at_position(operation.position)   
        self.__send_to_other_clients(RGAMessage(self.vector_clock.copy(), RGADeletionOperation(node.timestamp), operation))

    def __apply_operation(self, operation: RGAOperation):
            match operation:
                case RGAInsertionOperation(timestamp, parent, char):
                    self.tree.insert_node(timestamp, parent, char)
                case RGADeletionOperation(timestamp):
                    self.tree.delete_node_with_timestamp(timestamp)
                case _ as unreachable:
                    assert_never(unreachable)
     

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
    
            if len(client_message_buffer) == 0:
                return []
            
            if not self.__is_causally_ready(client_message_buffer[0]):
                return []
            
            message = client_message_buffer.pop(0)
    
            self.__apply_operation(message.operation)
    
            self.vector_clock[client_id] += 1
    
            return [message.causing_operation]  


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


    def read_state(self) -> list[UniqueChar]:
        return [node.value for node in self.tree.traverse()]

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
            client_ids: list[int] = []
            for client in self.clients:
                client_message_buffer = self.message_buffer[client.client_id]
                if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                    client_ids.append(client.client_id)
            
            return client_ids

    def __is_causally_ready(self, message: RGAMessage) -> bool:
            for client in self.clients:
                if message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                    return False
            return True    

    def send_message(self, client_id: int, message: RGAMessage):
            self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: RGAMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
        self.vector_clock[self.client_id] += 1

    