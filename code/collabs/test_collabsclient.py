import random

from algorithm_setup.algorithm_setup import collabs_setup
from collabs.collabsclient import CollabsClient
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


def _build(num_of_clients: int) -> list[CollabsClient]:
    clients = [CollabsClient(n) for n in range(num_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def _insert(client: CollabsClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def _delete(client: CollabsClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def _drain(clients: list[CollabsClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def _text(client: CollabsClient) -> str:
    return "".join(character.char for character in client.read_state())


# Concurrent insertions at the same position are separated by the sender rather
# than by which was created first, so the lower client id wins whichever order
# they were typed in.
def test_concurrent_insertions_are_ordered_by_sender():
    A, B = _build(2)

    _insert(B, 0, "b")
    _insert(A, 0, "a")
    _drain([A, B])

    assert _text(A) == "ab"
    assert _text(B) == "ab"


# The same two operations the other way round give the same answer, which is what
# distinguishes a sender key from a creation order key.
def test_sender_order_does_not_depend_on_typing_order():
    A, B = _build(2)

    _insert(A, 0, "a")
    _insert(B, 0, "b")
    _drain([A, B])

    assert _text(A) == "ab"


# A run stays contiguous against a concurrent run because the second character
# extends its author's own waypoint instead of competing at the same anchor.
def test_a_clients_own_run_stays_contiguous():
    A, B = _build(2)

    _insert(A, 0, "a")
    _drain([A, B])

    _insert(B, 0, "x")
    _insert(A, 1, "b")
    _drain([A, B])

    assert _text(A) == "xab"
    assert _text(B) == "xab"


# Client 1 extends its own run while client 0 concurrently inserts at the same
# anchor. A sibling tie by ascending sender would put client 0's character first,
# which is how sync9 settles this same schedule; sharing the waypoint is what
# keeps the run together whoever its author is.
def test_own_run_beats_a_concurrent_sibling_regardless_of_sender():
    A, B = _build(2)

    _insert(B, 0, "a")
    _drain([A, B])

    _insert(B, 1, "b")
    _insert(A, 1, "x")
    _drain([A, B])

    assert _text(A) == "abx"
    assert _text(B) == "abx"


# A deleted position keeps its place as a tombstone, which is what holds a
# concurrent insertion and a later local one in the gap it left.
def test_insert_into_a_concurrently_deleted_gap():
    A, B = _build(2)

    for index, char in enumerate("abc"):
        _insert(A, index, char)
    _drain([A, B])

    _delete(A, 1)
    _insert(B, 1, "x")
    _drain([A, B])

    _insert(A, 1, "d")
    _drain([A, B])

    assert _text(A) == "adxc"
    assert _text(B) == "adxc"


# The two lines that register the algorithm, exercised the way the checker will reach it.
def test_registered_algorithm_converges():
    random.seed(0)
    server, clients = collabs_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_concurrent_insertions_are_ordered_by_sender()
    test_sender_order_does_not_depend_on_typing_order()
    test_a_clients_own_run_stays_contiguous()
    test_own_run_beats_a_concurrent_sibling_regardless_of_sender()
    test_insert_into_a_concurrently_deleted_gap()
    test_registered_algorithm_converges()
    print("OK")
