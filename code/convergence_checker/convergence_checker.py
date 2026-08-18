import random

from device.clientdevice import ClientDevice
from device.operations import (
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
    ServerOperation,
    ServerReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)
from tibot.tibotclient import TIBOTClient


def check_for_convergence_client_server(
    server: ServerDevice, clients: dict[int, ClientDevice], num_of_operations: int = 10
) -> bool:
    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()))
        # print(operation)
        if isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            client.perform_operation(operation)
        if isinstance(operation, ServerOperation):
            server.perform_operation(operation)

    redo_check = True
    while redo_check:
        redo_check = False

        client_ids = server.can_receive_from()
        if client_ids != []:
            redo_check = True
            client_id = random.choice(client_ids)
            server.perform_operation(ServerReceiveFromClientOperation(client_id))
            client_ids = server.can_receive_from()

        for client_id in clients:
            client = clients[client_id]
            if client.can_receive_from_server():
                redo_check = True
                client.perform_operation(ClientReceiveFromServerOperation(client_id))

        for client_id in clients:
            client = clients[client_id]
            client_can_receive_from = client.can_receive_from()
            if len(client_can_receive_from) != 0:
                redo_check = True
                receive_from = random.choice(client_can_receive_from)
                client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))
                # print(ClientReceiveFromClientOperation(client.client_id, receive_from))
                # print(client.client_id,":",*client.read_state(), sep="")
                client_can_receive_from = client.can_receive_from()

    # Check for convergence
    # server_state = server.read_state()
    for client_id in clients:
        client = clients[client_id]
        if client.read_state() != clients[0].read_state():
            print("This algorithm does not satisfy convergence.")
            return False

    return True


def check_for_convergence_client_client(clients: dict[int, ClientDevice], num_of_operations: int = 10) -> bool:
    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()))
        client = clients[operation.client_id]
        client.perform_operation(operation)
        # print(operation)
        # print(operation.client_id,":",*client.read_state(), sep="")

    # Receive all messages into clients
    for client_id in clients:
        client = clients[client_id]
        client_can_receive_from = client.can_receive_from()
        while len(client_can_receive_from) != 0:
            receive_from = random.choice(client_can_receive_from)
            client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))
            # print(ClientReceiveFromClientOperation(client.client_id, receive_from))
            # print(client.client_id,":",*client.read_state(), sep="")
            client_can_receive_from = client.can_receive_from()

    # Check for convergence
    state = clients[0].read_state()
    for client_id in clients:
        client = clients[client_id]
        if client.read_state() != state:
            print("This algorithm does not satisfy convergence.")
            return False

    return True


def check_for_convergence_client_client_with_time_steps(
    clients: dict[int, TIBOTClient], num_of_operations: int = 10
) -> bool:
    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()))

        client = clients[operation.client_id]
        client.perform_operation(operation)
        # print(operation)

    # Run time intervals

    time_intervals = max([client.clock for client in clients.values()]) + 1

    for _ in range(time_intervals):
        for client_id in clients:
            client = clients[client_id]
            client.perform_operation(ClientTimestepOperation(client.client_id))

    # Receive all messages into clients
    for _ in range(time_intervals):
        for client_id in clients:
            client = clients[client_id]
            client_can_receive_from = client.can_receive_from()
            while len(client_can_receive_from) != 0:
                receive_from = random.choice(client_can_receive_from)
                client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))
                client_can_receive_from = client.can_receive_from()

    # Check for convergence
    state = clients[0].read_state()
    for client_id in clients:
        client = clients[client_id]
        if client.read_state() != state:
            print("This algorithm does not satisfy convergence.")
            return False

    return True


def convergence_checker(
    clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_ops: int = 10
) -> bool:
    if server:
        return check_for_convergence_client_server(server, clients, num_of_ops)
    else:
        return check_for_convergence_client_client(clients, num_of_ops)
