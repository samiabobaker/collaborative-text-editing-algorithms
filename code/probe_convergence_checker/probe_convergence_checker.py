import random
from dataclasses import dataclass
from typing import Literal

from algorithm_setup.algorithm_setup import DeviceSetup
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
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)
from unique_char.uniquechar import UniqueChar

# One instance of an algorithm: its clients by id, and its server if it has one.
World = tuple[ServerDevice | None, dict[int, ClientDevice]]

# What a replica is judged on. The characters it shows, each carried along with the identity
# it was created with, so that two replicas holding different characters that happen to print
# the same are still told apart.
VisibleState = list[tuple[str, int]]

# The character a probing insert carries. No algorithm reads it, it is only there to make the
# probe easy to pick out of a printed state.
PROBE_CHARACTER = "z"


# One operation to try on a converged world: who performs it, whether it inserts or deletes,
# and where in the visible state.
@dataclass(frozen=True)
class Probe:
    client_id: int
    kind: Literal["insert", "delete"]
    position: int

    def __str__(self) -> str:
        return f"client {self.client_id} {self.kind} at position {self.position}"


def run_random_trace(clients: dict[int, ClientDevice], server: ServerDevice | None, num_of_operations: int) -> None:
    # The operation stream the convergence and list spec checkers use: local inserts, local
    # deletes and receives, in whatever order the seeded generator picks.
    if server is None:
        for _ in range(num_of_operations):
            client_operation = generate_random_client_client_operation(list(clients.values()))
            clients[client_operation.client_id].perform_operation(client_operation)
        return

    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()))
        if isinstance(operation, ClientOperation):
            clients[operation.client_id].perform_operation(operation)
        else:
            server.perform_operation(operation)


def deliver_all_clients(clients: dict[int, ClientDevice]) -> None:
    for client_id in clients:
        client = clients[client_id]
        client_can_receive_from = client.can_receive_from()
        while len(client_can_receive_from) != 0:
            receive_from = random.choice(client_can_receive_from)
            client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))
            client_can_receive_from = client.can_receive_from()


def deliver_all_time_stepped(clients: dict[int, ClientDevice], time_stepped_clients: list[TimeSteppedClient]) -> None:
    # A time stepped client only releases what it buffered once its interval has closed, so the
    # clocks are run on far enough for everything held back to come out, and only then are the
    # messages drained, once per interval that was run.
    time_intervals = max([client.clock for client in time_stepped_clients]) + 1

    for _ in range(time_intervals):
        for time_stepped_client in time_stepped_clients:
            time_stepped_client.perform_operation(ClientTimestepOperation(time_stepped_client.client_id))

    for _ in range(time_intervals):
        deliver_all_clients(clients)


def deliver_all_client_server(clients: dict[int, ClientDevice], server: ServerDevice) -> None:
    # Delivering to the server makes new messages for the clients and the other way round, so
    # the three directions are run to a fixpoint rather than once each.
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
                client.perform_operation(ClientReceiveFromServerOperation(client_id))

        for client_id in clients:
            client = clients[client_id]
            client_can_receive_from = client.can_receive_from()
            if len(client_can_receive_from) != 0:
                redo_check = True
                receive_from = random.choice(client_can_receive_from)
                client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))


def deliver_all(clients: dict[int, ClientDevice], server: ServerDevice | None) -> None:
    # Deliver every message still in flight, so that what the replicas show is what they settle on.
    if server is not None:
        deliver_all_client_server(clients, server)
        return

    time_stepped_clients = [client for client in clients.values() if isinstance(client, TimeSteppedClient)]
    if len(time_stepped_clients) != 0:
        deliver_all_time_stepped(clients, time_stepped_clients)
    else:
        deliver_all_clients(clients)


def build_world(seed: int, device_setup: DeviceSetup, num_of_clients: int, num_of_ops: int) -> World:
    # Builds the same converged world every time it is called with the same arguments. There is no
    # deep copy of a running algorithm to be had here, so a probe gets its own world by replaying
    # the trace from the seed rather than by branching off the one already built.
    random.seed(seed)

    server, clients = device_setup(num_of_clients)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    run_random_trace(client_dict, server, num_of_ops)
    deliver_all(client_dict, server)

    return server, client_dict


def read_visible_states(clients: dict[int, ClientDevice]) -> dict[int, VisibleState]:
    states: dict[int, VisibleState] = {}
    for client_id in clients:
        states[client_id] = [(character.char, character.id) for character in clients[client_id].read_state()]
    return states


def first_disagreement(states: dict[int, VisibleState]) -> tuple[int, int] | None:
    # The first pair of replicas that do not show the same thing, or None if they all agree.
    client_ids = sorted(states)
    reference = client_ids[0]
    for client_id in client_ids[1:]:
        if states[client_id] != states[reference]:
            return reference, client_id
    return None


def probes_for(client_ids: list[int], length: int) -> list[Probe]:
    # Every single operation a user could perform next on a converged state of the given length:
    # an insert in any of its gaps, and a delete of any of its characters.
    probes: list[Probe] = []
    for client_id in client_ids:
        for position in range(length + 1):
            probes.append(Probe(client_id, "insert", position))
        for position in range(length):
            probes.append(Probe(client_id, "delete", position))
    return probes


def apply_probe(clients: dict[int, ClientDevice], probe: Probe) -> None:
    client = clients[probe.client_id]

    if probe.kind == "insert":
        character = UniqueChar.get_unique_char(PROBE_CHARACTER)
        client.perform_operation(ClientInsertOperation(probe.client_id, probe.position, character))
    else:
        character = client.read_state()[probe.position]
        client.perform_operation(ClientDeleteOperation(probe.client_id, probe.position, character))


def print_states(clients: dict[int, ClientDevice]) -> None:
    for client_id in sorted(clients):
        print(f"{client_id}:", *clients[client_id].read_state(), sep="")


def probe_convergence_checker(
    seed: int, device_setup: DeviceSetup, num_of_clients: int = 3, num_of_ops: int = 30
) -> bool:
    # Convergence only says that the replicas agree on what they show. They can agree on that and
    # still disagree underneath, about where a tombstone sits or what shape the tree has, and that
    # difference stays invisible until the next operation is performed on top of it. So once the
    # world has converged, every operation that could come next is tried in turn, each on its own
    # rebuild of the world, and the replicas are asked to agree again afterwards.
    try:
        _, clients = build_world(seed, device_setup, num_of_clients, num_of_ops)
    # The algorithm produced an operation that cannot be applied, e.g. a transformed delete past the end of the state.
    except (IndexError, ValueError) as e:
        print(f"This algorithm does not satisfy convergence ({type(e).__name__} while applying an operation: {e}).")
        return False

    states = read_visible_states(clients)
    if first_disagreement(states) is not None:
        print("This algorithm does not satisfy convergence, so there is nothing to probe.")
        print_states(clients)
        return False

    for probe in probes_for(sorted(clients), len(states[min(states)])):
        probe_server, probe_clients = build_world(seed, device_setup, num_of_clients, num_of_ops)
        # The rebuilt world hands out fresh characters, so its state is the converged state of the
        # base world up to a constant shift of the identities. It is kept to report against.
        state_before_probe = list(probe_clients[min(probe_clients)].read_state())

        try:
            apply_probe(probe_clients, probe)
            deliver_all(probe_clients, probe_server)
        # The algorithm produced an operation that cannot be applied, e.g. a transformed delete past the end of the state.
        except (IndexError, ValueError) as e:
            print(f"This algorithm does not satisfy probe convergence ({type(e).__name__} on {probe}: {e}).")
            return False

        if first_disagreement(read_visible_states(probe_clients)) is not None:
            print(f"This algorithm does not satisfy probe convergence ({probe}).")
            print("Converged state before the probe:")
            print(*state_before_probe, sep="")
            print("States after the probe:")
            print_states(probe_clients)
            return False

    return True
