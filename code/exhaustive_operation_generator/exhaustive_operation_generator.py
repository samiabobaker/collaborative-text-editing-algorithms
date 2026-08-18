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


def generate_all_server_operations(server: ServerDevice) -> list[ServerOperation]:
    client_ids = server.can_receive_from()

    return [ServerReceiveFromClientOperation(client_id) for client_id in client_ids]


def generate_all_inserts(client: ClientDevice) -> list[ClientInsertOperation]:
    state = client.read_state()

    character = UniqueChar.get_unique_char("a")

    return [ClientInsertOperation(client.client_id, position, character) for position in range(len(state) + 1)]


def generate_all_deletes(client: ClientDevice) -> list[ClientDeleteOperation]:
    state = client.read_state()

    return [ClientDeleteOperation(client.client_id, position, state[position]) for position in range(len(state))]


# Choices: client insert, client delete, server receive from client (if possible), client_receive (if possible)
def generate_all_client_server_operations(
    server: ServerDevice, clients: Sequence[ClientDevice], with_deletes: bool = True
) -> tuple[list[ServerOperation], list[ClientOperation]]:
    server_operations = generate_all_server_operations(server)

    client_operations: list[ClientOperation] = []

    for client in clients:
        operations = ["insert"]

        if len(client.read_state()) > 0 and with_deletes:
            operations.append("delete")
        if client.can_receive_from_server():
            operations.append("receive")

        for operation in operations:
            if operation == "insert":
                client_operations += generate_all_inserts(client)
            elif operation == "delete":
                client_operations += generate_all_deletes(client)
            elif operation == "receive":
                client_operations.append(ClientReceiveFromServerOperation(client.client_id))

    return server_operations, client_operations


# Choices: client insert, client delete, server receive from client (if possible), client_receive (if possible)
def generate_all_client_client_operations(
    clients: Sequence[ClientDevice], with_deletes: bool = True
) -> list[ClientOperation]:
    client_operations: list[ClientOperation] = []

    for client in clients:
        with_timesteps = isinstance(client, TimeSteppedClient)

        operations = ["insert"]

        client_can_receive_from = client.can_receive_from()

        if len(client.read_state()) > 0 and with_deletes:
            operations.append("delete")
        if len(client_can_receive_from) != 0:
            operations.append("receive")
        if with_timesteps:
            operations.append("timestep")

        for operation in operations:
            if operation == "insert":
                client_operations += generate_all_inserts(client)
            elif operation == "delete":
                client_operations += generate_all_deletes(client)
            elif operation == "timestep":
                client_operations.append(ClientTimestepOperation(client.client_id))
            else:
                for receive_from in client_can_receive_from:
                    client_operations.append(ClientReceiveFromClientOperation(client.client_id, receive_from))
    return client_operations
