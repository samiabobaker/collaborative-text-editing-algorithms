"""Enumerates every execution up to a depth, yielding the devices themselves.

The list specification and interleaving searches yield a trace, because their conditions
are statements about the states a client passed through. Convergence is not: it is a
statement about where the clients end up once everything in flight has been delivered,
so what the checker needs at each node is the devices, not a record of them.

The devices yielded are the search's own, still mid-flight and still to be extended, so a
caller that wants to deliver into them must do that against a copy.
"""

import random
from collections.abc import Generator
from dataclasses import dataclass

from algorithm_setup.algorithm_copy import copy_client_server, copy_clients
from device.clientdevice import ClientDevice
from device.operations import ClientOperation, ServerOperation
from device.serverdevice import ServerDevice
from exhaustive_operation_generator.exhaustive_operation_generator import (
    generate_all_client_client_operations,
    generate_all_client_server_operations,
)

Devices = tuple[ServerDevice | None, dict[int, ClientDevice]]


@dataclass
class ClientsQueueItem:
    clients: dict[int, ClientDevice]
    depth: int

    def copy(self) -> ClientsQueueItem:
        clients_copy = copy_clients(list(self.clients.values()))

        return ClientsQueueItem({client.client_id: client for client in clients_copy}, self.depth)


@dataclass
class ClientServerQueueItem:
    clients: dict[int, ClientDevice]
    server: ServerDevice
    depth: int

    def copy(self) -> ClientServerQueueItem:
        server_copy, clients_copy = copy_client_server(self.server, list(self.clients.values()))

        return ClientServerQueueItem({client.client_id: client for client in clients_copy}, server_copy, self.depth)


def build_exhaustive_states_clients(
    clients: dict[int, ClientDevice], num_of_operations: int = 4, randomised: bool = False, depth_first: bool = False
) -> Generator[Devices]:
    queue: list[ClientsQueueItem] = [ClientsQueueItem(clients, 0)]

    while queue != []:
        queue_item = queue.pop(-1) if depth_first else queue.pop(0)

        all_client_operations = generate_all_client_client_operations(list(queue_item.clients.values()))

        if randomised:
            random.shuffle(all_client_operations)

        for operation in all_client_operations:
            queue_item_copy = queue_item.copy()

            client = queue_item_copy.clients[operation.client_id]
            client.perform_operation(operation)

            queue_item_copy.depth += 1

            # Every node is yielded, not just the leaves, so a violation can be caught at a
            # prefix instead of only in the full-depth traces that extend it. The search is
            # depth first, so that prefix is not necessarily the shortest one.
            yield None, queue_item_copy.clients

            if queue_item_copy.depth != num_of_operations:
                queue.append(queue_item_copy)


def build_exhaustive_states_client_server(
    clients: dict[int, ClientDevice],
    server: ServerDevice,
    num_of_operations: int = 4,
    randomised: bool = False,
    depth_first: bool = False,
) -> Generator[Devices]:
    queue: list[ClientServerQueueItem] = [ClientServerQueueItem(clients, server, 0)]

    while queue != []:
        queue_item = queue.pop(-1) if depth_first else queue.pop(0)

        all_server_operations, all_client_operations = generate_all_client_server_operations(
            queue_item.server, list(queue_item.clients.values())
        )

        all_operations: list[ClientOperation | ServerOperation] = all_client_operations + all_server_operations

        if randomised:
            random.shuffle(all_operations)

        for operation in all_operations:
            if isinstance(operation, ClientOperation):
                queue_item_copy = queue_item.copy()

                client = queue_item_copy.clients[operation.client_id]
                client.perform_operation(operation)

                queue_item_copy.depth += 1

                yield queue_item_copy.server, queue_item_copy.clients

                if queue_item_copy.depth != num_of_operations:
                    queue.append(queue_item_copy)
            else:
                queue_item_copy = queue_item.copy()

                queue_item_copy.server.perform_operation(operation)

                queue_item_copy.depth += 1

                yield queue_item_copy.server, queue_item_copy.clients

                if queue_item_copy.depth != num_of_operations:
                    queue.append(queue_item_copy)


def build_exhaustive_states(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 4,
    randomised: bool = False,
    depth_first: bool = False,
) -> Generator[Devices]:
    if server:
        return build_exhaustive_states_client_server(clients, server, num_of_operations, randomised, depth_first)
    else:
        return build_exhaustive_states_clients(clients, num_of_operations, randomised, depth_first)
