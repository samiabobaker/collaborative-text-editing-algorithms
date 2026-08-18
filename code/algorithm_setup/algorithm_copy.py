from collections.abc import Sequence

from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from fugue.fugueclient import FugueClient
from fuguemax.fuguemaxclient import FugueMaxClient
from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer
from tibot.tibotclient import TIBOTClient


def copy_clients(clients: list[ClientDevice]) -> Sequence[ClientDevice]:
    if isinstance(clients[0], FugueClient):
        return fugue_copy(clients)  # type: ignore
    elif isinstance(clients[0], FugueMaxClient):
        return fugue_max_copy(clients)  # type: ignore
    elif isinstance(clients[0], TIBOTClient):
        return tibot_copy(clients)  # type: ignore
    else:
        raise Exception("Copy doesn't exist for this algorithm.")


def copy_client_server(server: ServerDevice, clients: list[ClientDevice]) -> tuple[ServerDevice, list[ClientDevice]]:
    if isinstance(server, JupiterServer) and isinstance(clients[0], JupiterClient):
        return jupiter_copy(server, clients)  # type: ignore
    else:
        raise Exception("Copy doesn't exist for this algorithm.")


def jupiter_copy(server: JupiterServer, clients: list[JupiterClient]) -> tuple[JupiterServer, list[JupiterClient]]:
    clients_copy: list[JupiterClient] = []

    for client in clients:
        client_copy = JupiterClient(client.client_id)

        client_copy.message_buffer = list(client.message_buffer)
        client_copy.client_message_count = client.client_message_count
        client_copy.server_message_count = client.server_message_count
        client_copy.outgoing = list(client.outgoing)
        client_copy.state = list(client.state)

        clients_copy.append(client_copy)

    server_copy = JupiterServer(clients_copy)

    server_copy.state = list(server.state)

    for client in clients:
        client_id = client.client_id

        server_copy.clients[client_id].message_buffer = list(server.clients[client_id].message_buffer)
        server_copy.clients[client_id].outgoing = list(server.clients[client_id].outgoing)
        server_copy.clients[client_id].client_message_count = server.clients[client_id].client_message_count
        server_copy.clients[client_id].server_message_count = server.clients[client_id].server_message_count

    for client in clients_copy:
        client.jupiter_server = server_copy

    return server_copy, clients_copy


def tibot_copy(clients: list[TIBOTClient]) -> list[TIBOTClient]:
    clients_copy: list[TIBOTClient] = []
    for client in clients:
        client_copy = TIBOTClient(client.client_id)

        client_copy.state = list(client.state)
        client_copy.clock = client.clock
        client_copy.sequence_number = client.sequence_number

        client_copy.time_intervals_from_client = {
            client_id: list(time_intervals) for client_id, time_intervals in client.time_intervals_from_client.items()
        }
        client_copy.client_ids_from_time_interval = {
            time_interval: list(client_ids)
            for time_interval, client_ids in client.client_ids_from_time_interval.items()
        }

        client_copy.operation_buffer = {
            time_interval: list(operations) for time_interval, operations in client.operation_buffer.items()
        }
        client_copy.history_buffer = list(client.history_buffer)

        client_copy.message_buffer = {
            client_id: list(messages) for client_id, messages in client.message_buffer.items()
        }

        client_copy.causing_operations = {
            time_interval: list(operations) for time_interval, operations in client.causing_operations.items()
        }

        clients_copy.append(client_copy)

    for client in clients_copy:
        client.clients = list(clients_copy)

    return clients_copy


def fugue_copy(clients: list[FugueClient]) -> list[FugueClient]:
    clients_copy: list[FugueClient] = []

    for client in clients:
        client_copy = FugueClient(client.client_id)

        client_copy.tree = client.tree.copy()
        client_copy.vector_clock = dict(client.vector_clock)
        client_copy.message_buffer = {
            client_id: list(messages) for client_id, messages in client.message_buffer.items()
        }

        clients_copy.append(client_copy)

    for client in clients_copy:
        client.clients = list(clients_copy)

    return clients_copy


def fugue_max_copy(clients: list[FugueMaxClient]) -> list[FugueMaxClient]:
    clients_copy: list[FugueMaxClient] = []

    for client in clients:
        client_copy = FugueMaxClient(client.client_id)

        client_copy.tree = client.tree.copy()
        client_copy.vector_clock = dict(client.vector_clock)
        client_copy.message_buffer = {
            client_id: list(messages) for client_id, messages in client.message_buffer.items()
        }

        clients_copy.append(client_copy)

    for client in clients_copy:
        client.clients = list(clients_copy)

    return clients_copy
