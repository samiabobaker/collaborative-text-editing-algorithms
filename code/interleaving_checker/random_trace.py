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
from interleaving_checker.client_trace import Character, ClientTrace, Event
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)


def build_random_trace_clients(
    clients: dict[int, ClientDevice],
    num_of_operations: int = 30,
    print_ops: bool = False,
    with_deletes: bool = False,
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    client_traces: dict[int, ClientTrace] = {}

    characters: dict[int, Character] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()), with_deletes=with_deletes)

        client = clients[operation.client_id]
        if print_ops:
            print(operation)
        operation_seen = client.perform_operation(operation)

        state = list(client.read_state())
        if isinstance(operation, ClientInsertOperation):
            char = operation.character

            left_origin = state[operation.position - 1] if operation.position > 0 else "start"
            right_origin = state[operation.position + 1] if operation.position < len(state) - 1 else "end"

            if left_origin != "start":
                left_origin_character = characters[left_origin.id]
                left_origin_character.add_to_left_origin_of(char)

            if right_origin != "end":
                right_origin_character = characters[right_origin.id]
                right_origin_character.add_to_right_origin_of(char)

            character = Character(char, left_origin, right_origin)

            characters[character.char.id] = character

        if len(operation_seen) != 0:
            performed_locally = isinstance(operation, (ClientInsertOperation, ClientDeleteOperation))
            client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)

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

    return client_traces, characters


def build_random_trace_client_server(
    clients: dict[int, ClientDevice],
    server: ServerDevice,
    num_of_operations: int = 30,
    print_ops: bool = False,
    with_deletes: bool = False,
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    characters: dict[int, Character] = {}

    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()), with_deletes=with_deletes)
        if print_ops:
            print(operation)
        if isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            state = list(client.read_state())

            if isinstance(operation, ClientInsertOperation):
                char = operation.character

                left_origin = state[operation.position - 1] if operation.position > 0 else "start"
                right_origin = state[operation.position + 1] if operation.position < len(state) - 1 else "end"

                if left_origin != "start":
                    left_origin_character = characters[left_origin.id]
                    left_origin_character.add_to_left_origin_of(char)

                if right_origin != "end":
                    right_origin_character = characters[right_origin.id]
                    right_origin_character.add_to_right_origin_of(char)

                character = Character(char, left_origin, right_origin)

                characters[character.char.id] = character

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, (ClientInsertOperation, ClientDeleteOperation))
                client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)
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

    return client_traces, characters


def build_random_trace(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 30,
    print_ops: bool = False,
    with_deletes: bool = False,
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    if server:
        return build_random_trace_client_server(clients, server, num_of_operations, print_ops, with_deletes)
    else:
        return build_random_trace_clients(clients, num_of_operations, print_ops, with_deletes)
