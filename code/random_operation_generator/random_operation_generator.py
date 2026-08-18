import random
from collections.abc import Sequence

from device.clientdevice import ClientDevice, TimeSteppedClient
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
    ServerOperation,
    ServerReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
from unique_char.uniquechar import UniqueChar


def generate_random_server_operation(server: ServerDevice) -> ServerOperation:
    client_ids = server.can_receive_from()

    client_id = random.choice(client_ids)

    return ServerReceiveFromClientOperation(client_id)

def generate_random_insert(client: ClientDevice) -> ClientInsertOperation:
    state = client.read_state()

    position = random.randint(0, len(state))
    character = UniqueChar.get_unique_char(random.choice("abcdefghijklmnopqrstuvwxyz"))

    return ClientInsertOperation(client.client_id, position, character)

def generate_random_delete(client: ClientDevice) -> ClientDeleteOperation:
    state = client.read_state()

    position = random.randint(0, len(state) - 1)

    character = state[position]

    return ClientDeleteOperation(client.client_id, position, character)

#Choices: client insert, client delete, server receive from client (if possible), client_receive (if possible) 
def generate_random_client_server_operation(server: ServerDevice, clients: Sequence[ClientDevice], with_deletes:bool = True) -> ClientOperation | ServerOperation:  
    if len(server.can_receive_from()) != 0:
        num_devices = len(clients) + 1
        if random.random() < (1/num_devices):
            return generate_random_server_operation(server)
    
    client = random.choice(clients)

    operations = ["insert"]

    client_can_receive_from = client.can_receive_from()

    if len(client.read_state()) > 0 and with_deletes:
        operations.append("delete")
    if client.can_receive_from_server():
        operations.append("receiveserver")
    if len(client_can_receive_from) != 0:
        operations.append("receiveclient")

    operation = random.choice(operations)

    if operation == "insert":
        return generate_random_insert(client)
    elif operation == "delete":
        return generate_random_delete(client)
    elif operation == "receiveserver":
        return ClientReceiveFromServerOperation(client.client_id)
    else:
        receive_from = random.choice(client_can_receive_from)
        return ClientReceiveFromClientOperation(client.client_id, receive_from)
    
#Choices: client insert, client delete, server receive from client (if possible), client_receive (if possible) 
def generate_random_client_client_operation(clients: Sequence[ClientDevice], with_deletes:bool=True) -> ClientOperation:  
    client = random.choice(clients)

    with_timesteps = isinstance(client, TimeSteppedClient)

    operations = ["insert"]

    client_can_receive_from = client.can_receive_from()

    if len(client.read_state()) > 0 and with_deletes:
        operations.append("delete")
    if len(client_can_receive_from) != 0:
        operations.append("receive")
    if with_timesteps:
        operations.append("timestep")

    operation = random.choice(operations)

    if operation == "insert":
        return generate_random_insert(client)
    elif operation == "delete":
        return generate_random_delete(client)
    elif operation == "timestep":
        return ClientTimestepOperation(client.client_id)
    else:
        receive_from = random.choice(client_can_receive_from)
        return ClientReceiveFromClientOperation(client.client_id, receive_from)