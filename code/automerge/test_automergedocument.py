import random

from algorithm_setup.algorithm_setup import automerge_setup
from automerge.automergeclient import AutomergeClient
from automerge.automergedocument import AutomergeDocument
from automerge.automergemessage import HEAD
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


def insert(client: AutomergeClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def delete(client: AutomergeClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def drain(clients: list[AutomergeClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def text(chars: list[UniqueChar]) -> str:
    return "".join(char.char for char in chars)


# Concurrent inserts after the same element are ordered newest first, by descending
# (counter, actor), which is the RGA rule the Untangler implements.
def test_children_of_one_predecessor_are_ordered_by_descending_id():
    document = AutomergeDocument(0)

    document.integrate_insert(HEAD, (1, 0), UniqueChar.get_unique_char("a"))
    document.integrate_insert(HEAD, (1, 1), UniqueChar.get_unique_char("b"))
    document.integrate_insert(HEAD, (1, 2), UniqueChar.get_unique_char("c"))

    assert text(document.traverse()) == "cba"


# A delete is a succ pointer, so the deleted element stays in the columns and still
# anchors a concurrent insert that named it (the third example in automergeexamples.py).
def test_a_deleted_element_still_anchors_a_concurrent_insert():
    A = AutomergeClient(0)
    B = AutomergeClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    insert(A, 0, "a")
    insert(A, 1, "b")
    drain([A, B])

    delete(A, 1)
    insert(B, 2, "c")

    drain([A, B])

    assert text(A.read_state()) == "ac"
    assert text(B.read_state()) == "ac"
    assert text(A.read_state_with_tombstones()) == "abc"


# A random trace, delivered to quiescence by the checker, leaves every client with the
# same state.
def test_random_trace_converges():
    random.seed(7)
    server, clients = automerge_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_children_of_one_predecessor_are_ordered_by_descending_id()
    test_a_deleted_element_still_anchors_a_concurrent_insert()
    test_random_trace_converges()
    print("OK")
