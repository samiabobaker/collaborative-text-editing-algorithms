import random

from algorithm_setup.algorithm_setup import fugue_setup, jupiter_setup, make_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from probe_convergence_checker.probe_convergence_checker import (
    build_world,
    probe_convergence_checker,
    read_visible_states,
)
from unique_char.uniquechar import UniqueChar

# A version stamp: how many operations a replica has performed itself, and who it is.
Stamp = tuple[int, int]

# A whole document sent from one replica to another, under the stamp it was made at.
Message = tuple[Stamp, list[UniqueChar]]


# A deliberately broken algorithm, used to show what a probe catches that convergence does not.
# A replica broadcasts its whole document on every local operation, and keeps the document that
# came with the highest stamp, which is a last writer wins register over the whole document. Once
# every message has been delivered every replica holds the document with the highest stamp of all,
# so convergence holds, however far apart the replicas were on the way there.
# What convergence cannot see is that the replicas are left holding different operation counts,
# because a count only counts what its own replica did. The next operation is stamped from that
# count, so an edit made at a replica that has been quiet is stamped below what its peers already
# hold and they throw it away, while the replica that made it keeps it.
class LastWriterWinsClient(ClientDevice):
    client_id: int
    state: list[UniqueChar]
    stamp: Stamp
    local_operations: int
    clients: list[LastWriterWinsClient]
    message_buffer: dict[int, list[Message]]

    def __init__(self, client_id: int) -> None:
        self.client_id = client_id
        self.state = []
        self.stamp = (0, client_id)
        self.local_operations = 0
        self.clients = []
        self.message_buffer = {}

    def set_clients(self, clients: list[LastWriterWinsClient]) -> None:
        self.clients = clients
        for client in clients:
            if client.client_id != self.client_id:
                self.message_buffer[client.client_id] = []

    def perform_local_operation(self, operation: ClientInsertOperation | ClientDeleteOperation) -> None:
        if isinstance(operation, ClientInsertOperation):
            self.state.insert(operation.position, operation.character)
        else:
            del self.state[operation.position]

        self.local_operations += 1
        self.stamp = (self.local_operations, self.client_id)

        for client in self.clients:
            if client.client_id != self.client_id:
                client.message_buffer[self.client_id].append((self.stamp, list(self.state)))

    def receive_message(self, sender_client_id: int) -> None:
        stamp, state = self.message_buffer[sender_client_id].pop(0)
        if stamp > self.stamp:
            self.stamp = stamp
            self.state = list(state)

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation() | ClientDeleteOperation():
                self.perform_local_operation(operation)
                return [operation]
            case ClientReceiveFromClientOperation(_, sender_client_id):
                self.receive_message(sender_client_id)
                return []
            case ClientReceiveFromServerOperation(_) | ClientTimestepOperation(_):
                return []

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        return [client_id for client_id in self.message_buffer if len(self.message_buffer[client_id]) != 0]


# Rebuilding a world replays its trace from the seed, so the two builds hold the same characters
# in the same order. Each build takes fresh identities, so the second build's identities are the
# first build's shifted by however many characters the first build used up.
def test_rebuilding_a_world_is_deterministic():
    first_base = UniqueChar.now
    _, first_clients = build_world(7, fugue_setup, 3, 30)
    second_base = UniqueChar.now
    _, second_clients = build_world(7, fugue_setup, 3, 30)

    shift = second_base - first_base
    first_states = read_visible_states(first_clients)
    second_states = read_visible_states(second_clients)

    assert len(first_states[0]) != 0
    for client_id in first_states:
        assert [(char, id + shift) for char, id in first_states[client_id]] == second_states[client_id]


# Fugue is a CRDT, so no operation performed on a converged document can pull the replicas apart.
def test_peer_to_peer_control_passes():
    assert probe_convergence_checker(7, fugue_setup, 3, 30) is True


# Jupiter puts a server between the clients, which the probe has to deliver through as well.
def test_client_server_control_passes():
    assert probe_convergence_checker(7, jupiter_setup, 3, 30) is True


# The replicas of a document held as a last writer wins register do agree once everything has been
# delivered, so convergence sees nothing wrong. They disagree on the very next operation, which is
# what a probe is for.
def test_hidden_divergence_passes_convergence_and_fails_a_probe():
    last_writer_wins_setup = make_setup(LastWriterWinsClient)

    random.seed(1)
    _, clients = last_writer_wins_setup(3)
    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, None, 30) is True
    assert probe_convergence_checker(1, last_writer_wins_setup, 3, 30) is False


if __name__ == "__main__":
    test_rebuilding_a_world_is_deterministic()
    test_peer_to_peer_control_passes()
    test_client_server_control_passes()
    test_hidden_divergence_passes_convergence_and_fails_a_probe()
    print("OK")
