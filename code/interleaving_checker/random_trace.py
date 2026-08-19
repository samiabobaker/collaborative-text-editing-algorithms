from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientOperation
from device.serverdevice import ServerDevice
from interleaving_checker.client_trace import Character, ClientTrace, Event
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)


def build_random_trace_clients(
    clients: dict[int, ClientDevice], num_of_operations: int = 30, print_ops: bool = False
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    client_traces: dict[int, ClientTrace] = {}

    characters: dict[int, Character] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()), with_deletes=False)

        client = clients[operation.client_id]
        if print_ops:
            print(operation)
        operation_seen = client.perform_operation(operation)

        assert not isinstance(operation_seen, ClientDeleteOperation)

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
            performed_locally = isinstance(operation, ClientInsertOperation)
            client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)

    return client_traces, characters


def build_random_trace_client_server(
    clients: dict[int, ClientDevice], server: ServerDevice, num_of_operations: int = 30, print_ops: bool = False
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    characters: dict[int, Character] = {}

    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()), with_deletes=False)
        if print_ops:
            print(operation)
        if isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            assert not isinstance(operation_seen, ClientDeleteOperation)

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
                performed_locally = isinstance(operation, ClientInsertOperation)
                client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)
        else:
            server.perform_operation(operation)

    return client_traces, characters


def build_random_trace(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 30,
    print_ops: bool = False,
) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    if server:
        return build_random_trace_client_server(clients, server, num_of_operations, print_ops)
    else:
        return build_random_trace_clients(clients, num_of_operations, print_ops)
