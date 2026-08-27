import random

from algorithm_setup.algorithm_setup import twc_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientReceiveFromServerOperation,
    ServerReceiveFromClientOperation,
)
from twc.twcclient import TWCClient
from twc.twcserver import TWCServer
from unique_char.uniquechar import UniqueChar


def _build(num_of_clients: int) -> tuple[TWCServer, list[TWCClient]]:
    clients = [TWCClient(n) for n in range(num_of_clients)]
    server = TWCServer(clients)
    for client in clients:
        client.set_server(server)
    return server, clients


def _drain(server: TWCServer, clients: list[TWCClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client_id in server.can_receive_from():
            server.perform_operation(ServerReceiveFromClientOperation(client_id))
            progressed = True
        for client in clients:
            if client.can_receive_from_server():
                client.perform_operation(ClientReceiveFromServerOperation(client.client_id))
                progressed = True


# Inserts after the same element end up in the reverse of the order the server took them,
# so the update the server committed second sorts first.
def test_concurrent_inserts_reverse_the_order_the_server_took_them():
    server, clients = _build(2)
    A, B = clients

    A.perform_local_insert(ClientInsertOperation(A.client_id, 0, UniqueChar.get_unique_char("a")))
    B.perform_local_insert(ClientInsertOperation(B.client_id, 0, UniqueChar.get_unique_char("b")))

    server.perform_operation(ServerReceiveFromClientOperation(A.client_id))
    server.perform_operation(ServerReceiveFromClientOperation(B.client_id))
    _drain(server, clients)

    assert [character.char for character in server.read_state()] == ["b", "a"]
    assert [character.char for character in A.read_state()] == ["b", "a"]


# A deleted element keeps its place as a tombstone, so an insert after it still lands
# even when the server commits the delete first.
def test_insert_after_a_concurrently_deleted_character():
    server, clients = _build(2)
    A, B = clients

    x = UniqueChar.get_unique_char("x")
    A.perform_local_insert(ClientInsertOperation(A.client_id, 0, x))
    _drain(server, clients)

    A.perform_local_delete(ClientDeleteOperation(A.client_id, 0, x))
    B.perform_local_insert(ClientInsertOperation(B.client_id, 1, UniqueChar.get_unique_char("y")))

    server.perform_operation(ServerReceiveFromClientOperation(A.client_id))
    server.perform_operation(ServerReceiveFromClientOperation(B.client_id))
    _drain(server, clients)

    assert [character.char for character in A.read_state()] == ["y"]


# A client keeps showing its pending updates until the committed ones arrive, and then
# rebuilds its view from the committed state plus those pending updates.
def test_pending_updates_survive_a_commit_from_another_client():
    server, clients = _build(2)
    A, B = clients

    A.perform_local_insert(ClientInsertOperation(A.client_id, 0, UniqueChar.get_unique_char("a")))
    A.perform_local_insert(ClientInsertOperation(A.client_id, 1, UniqueChar.get_unique_char("b")))
    B.perform_local_insert(ClientInsertOperation(B.client_id, 0, UniqueChar.get_unique_char("z")))

    assert [character.char for character in A.read_state()] == ["a", "b"]

    server.perform_operation(ServerReceiveFromClientOperation(B.client_id))
    A.perform_operation(ClientReceiveFromServerOperation(A.client_id))

    assert [character.char for character in A.read_state()] == ["a", "b", "z"]
    assert len(A.pending) == 2

    _drain(server, clients)

    assert [character.char for character in A.read_state()] == ["a", "b", "z"]


# The two lines that register the algorithm, exercised the way the checker will reach it.
def test_registered_algorithm_converges():
    random.seed(0)
    server, clients = twc_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_concurrent_inserts_reverse_the_order_the_server_took_them()
    test_insert_after_a_concurrently_deleted_character()
    test_pending_updates_survive_a_commit_from_another_client()
    test_registered_algorithm_converges()
    print("OK")
