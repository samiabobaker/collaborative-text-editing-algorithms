import random
from collections.abc import Generator
from dataclasses import dataclass

from algorithm_setup.algorithm_copy import copy_client_server, copy_clients
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from device.serverdevice import ServerDevice
from exhaustive_operation_generator.exhaustive_operation_generator import (
    generate_all_client_client_operations,
    generate_all_client_server_operations,
)
from interleaving_checker.client_trace import Character, ClientTrace, Event


@dataclass
class ClientsQueueItem:
    clients: dict[int, ClientDevice]
    depth: int
    clients_trace: dict[int, ClientTrace]
    characters: dict[int, Character]

    def copy(self) -> ClientsQueueItem:
        clients_copy = copy_clients(list(self.clients.values()))

        clients_copy_dict = {client.client_id: client for client in clients_copy}

        client_trace_copy = {client_id: client_trace.copy() for client_id, client_trace in self.clients_trace.items()}

        characters_copy = {id: character.copy() for id, character in self.characters.items()}

        return ClientsQueueItem(clients_copy_dict, self.depth, client_trace_copy, characters_copy)


@dataclass
class ClientServerQueueItem:
    clients: dict[int, ClientDevice]
    server: ServerDevice
    depth: int
    clients_trace: dict[int, ClientTrace]
    characters: dict[int, Character]

    def copy(self) -> ClientServerQueueItem:
        server_copy, clients_copy = copy_client_server(self.server, list(self.clients.values()))

        clients_copy_dict = {client.client_id: client for client in clients_copy}

        client_trace_copy = {client_id: client_trace.copy() for client_id, client_trace in self.clients_trace.items()}

        characters_copy = {id: character.copy() for id, character in self.characters.items()}

        return ClientServerQueueItem(clients_copy_dict, server_copy, self.depth, client_trace_copy, characters_copy)


def build_exhaustive_trace_clients(
    clients: dict[int, ClientDevice], num_of_operations: int = 4, randomised: bool = False
) -> Generator[tuple[dict[int, ClientTrace], dict[int, Character]]]:
    initial_clients_trace: dict[int, ClientTrace] = {}

    for client_id in clients:
        initial_clients_trace[client_id] = ClientTrace()

    initial_queue_items = ClientsQueueItem(clients, 0, initial_clients_trace, {})

    queue: list[ClientsQueueItem] = []

    queue.append(initial_queue_items)

    while queue != []:
        queue_item = queue.pop(-1)

        all_operations = generate_all_client_client_operations(list(queue_item.clients.values()), with_deletes=False)

        for operation in all_operations:
            queue_item_copy = queue_item.copy()

            client = queue_item_copy.clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            assert not isinstance(operation_seen, ClientDeleteOperation)

            state = list(client.read_state())
            if isinstance(operation, ClientInsertOperation):
                char = operation.character

                left_origin = state[operation.position - 1] if operation.position > 0 else "start"
                right_origin = state[operation.position + 1] if operation.position < len(state) - 1 else "end"

                if left_origin != "start":
                    left_origin_character = queue_item_copy.characters[left_origin.id]
                    left_origin_character.add_to_left_origin_of(char)

                if right_origin != "end":
                    right_origin_character = queue_item_copy.characters[right_origin.id]
                    right_origin_character.add_to_right_origin_of(char)

                character = Character(char, left_origin, right_origin)

                queue_item_copy.characters[character.char.id] = character

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
                queue_item_copy.clients_trace[operation.client_id].add_event(
                    Event(operation_seen, performed_locally), list(client.read_state())
                )

            queue_item_copy.depth += 1

            yield queue_item_copy.clients_trace, queue_item_copy.characters

            if queue_item_copy.depth != num_of_operations:
                queue.append(queue_item_copy)


def build_exhaustive_trace_client_server(
    clients: dict[int, ClientDevice], server: ServerDevice, num_of_operations: int = 4, randomised: bool = False
) -> Generator[tuple[dict[int, ClientTrace], dict[int, Character]]]:

    initial_clients_trace: dict[int, ClientTrace] = {}

    for client_id in clients:
        initial_clients_trace[client_id] = ClientTrace()

    initial_queue_items = ClientServerQueueItem(clients, server, 0, initial_clients_trace, {})

    queue: list[ClientServerQueueItem] = []

    queue.append(initial_queue_items)

    while queue != []:
        queue_item = queue.pop(-1)

        all_server_operations, all_client_operations = generate_all_client_server_operations(
            queue_item.server, list(queue_item.clients.values()), with_deletes=False
        )

        if randomised:
            # print("RANDOMISED")
            random.shuffle(all_client_operations)
            random.shuffle(all_server_operations)

        for operation in all_client_operations:
            queue_item_copy = queue_item.copy()

            client = queue_item_copy.clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            assert not isinstance(operation_seen, ClientDeleteOperation)

            state = list(client.read_state())
            if isinstance(operation, ClientInsertOperation):
                char = operation.character

                left_origin = state[operation.position - 1] if operation.position > 0 else "start"
                right_origin = state[operation.position + 1] if operation.position < len(state) - 1 else "end"

                if left_origin != "start":
                    left_origin_character = queue_item_copy.characters[left_origin.id]
                    left_origin_character.add_to_left_origin_of(char)

                if right_origin != "end":
                    right_origin_character = queue_item_copy.characters[right_origin.id]
                    right_origin_character.add_to_right_origin_of(char)

                character = Character(char, left_origin, right_origin)

                queue_item_copy.characters[character.char.id] = character

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
                queue_item_copy.clients_trace[operation.client_id].add_event(
                    Event(operation_seen, performed_locally), list(client.read_state())
                )

            queue_item_copy.depth += 1

            if queue_item_copy.depth == num_of_operations:
                yield queue_item_copy.clients_trace, queue_item_copy.characters
            else:
                yield queue_item_copy.clients_trace, queue_item_copy.characters
                queue.append(queue_item_copy)

        for operation in all_server_operations:
            queue_item_copy = queue_item.copy()

            queue_item_copy.server.perform_operation(operation)

            queue_item_copy.depth += 1

            yield queue_item_copy.clients_trace, queue_item_copy.characters

            if queue_item_copy.depth != num_of_operations:
                queue.append(queue_item_copy)


def build_exhaustive_interleaving_trace(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 30,
    randomised: bool = False,
) -> Generator[tuple[dict[int, ClientTrace], dict[int, Character]]]:
    if server:
        return build_exhaustive_trace_client_server(clients, server, num_of_operations, randomised)
    else:
        return build_exhaustive_trace_clients(clients, num_of_operations, randomised)
