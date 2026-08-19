import random

from device.clientdevice import ClientDevice, TimeSteppedClient
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
    ServerReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
from list_spec_checker.client_trace import ClientTrace, Event
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)


def build_random_trace_clients(clients: dict[int, ClientDevice], num_of_operations: int = 30, print_ops: bool = False):
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()))
        client = clients[operation.client_id]
        operation_seen = client.perform_operation(operation)

        if len(operation_seen) != 0:
            performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
            client_traces[operation.client_id].add_event(
                Event(operation_seen, performed_locally), list(client.read_state())
            )
        if print_ops:
            print(operation)

    # Deliver the messages still in flight, so the checkers see the settled states.
    time_stepped_clients = [client for client in clients.values() if isinstance(client, TimeSteppedClient)]
    if len(time_stepped_clients) != 0:
        # Run time intervals
        time_intervals = max([client.clock for client in time_stepped_clients]) + 1

        for _ in range(time_intervals):
            for time_stepped_client in time_stepped_clients:
                time_stepped_client.perform_operation(ClientTimestepOperation(time_stepped_client.client_id))

        for _ in range(time_intervals):
            for client_id in clients:
                client = clients[client_id]
                client_can_receive_from = client.can_receive_from()
                while len(client_can_receive_from) != 0:
                    receive_from = random.choice(client_can_receive_from)
                    operation_seen = client.perform_operation(
                        ClientReceiveFromClientOperation(client.client_id, receive_from)
                    )
                    if len(operation_seen) != 0:
                        client_traces[client_id].add_event(Event(operation_seen, False), list(client.read_state()))
                    client_can_receive_from = client.can_receive_from()
    else:
        for client_id in clients:
            client = clients[client_id]
            client_can_receive_from = client.can_receive_from()
            while len(client_can_receive_from) != 0:
                receive_from = random.choice(client_can_receive_from)
                operation_seen = client.perform_operation(
                    ClientReceiveFromClientOperation(client.client_id, receive_from)
                )
                if len(operation_seen) != 0:
                    client_traces[client_id].add_event(Event(operation_seen, False), list(client.read_state()))
                client_can_receive_from = client.can_receive_from()

    return client_traces


def build_random_trace_client_server(
    clients: dict[int, ClientDevice], server: ServerDevice, num_of_operations: int = 30, print_ops: bool = False
):
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()))
        if print_ops:
            print(operation)
        if isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
                client_traces[operation.client_id].add_event(
                    Event(operation_seen, performed_locally), list(client.read_state())
                )
        else:
            server.perform_operation(operation)

    # Deliver the messages still in flight, so the checkers see the settled states.
    redo_check = True
    while redo_check:
        redo_check = False

        client_ids = server.can_receive_from()
        if client_ids != []:
            redo_check = True
            server.perform_operation(ServerReceiveFromClientOperation(random.choice(client_ids)))

        for client_id in clients:
            client = clients[client_id]
            if client.can_receive_from_server():
                redo_check = True
                operation_seen = client.perform_operation(ClientReceiveFromServerOperation(client_id))
                if len(operation_seen) != 0:
                    client_traces[client_id].add_event(Event(operation_seen, False), list(client.read_state()))

        for client_id in clients:
            client = clients[client_id]
            client_can_receive_from = client.can_receive_from()
            if len(client_can_receive_from) != 0:
                redo_check = True
                receive_from = random.choice(client_can_receive_from)
                operation_seen = client.perform_operation(
                    ClientReceiveFromClientOperation(client.client_id, receive_from)
                )
                if len(operation_seen) != 0:
                    client_traces[client_id].add_event(Event(operation_seen, False), list(client.read_state()))

    return client_traces


def build_random_trace(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 30,
    print_ops: bool = False,
) -> dict[int, ClientTrace]:
    if server:
        return build_random_trace_client_server(clients, server, num_of_operations, print_ops)
    else:
        return build_random_trace_clients(clients, num_of_operations, print_ops)
