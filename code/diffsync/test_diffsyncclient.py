import random

from algorithm_setup.algorithm_setup import diffsync_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from diffsync.diffsyncclient import DiffsyncClient
from unique_char.uniquechar import UniqueChar


def _build(num_of_clients: int) -> list[DiffsyncClient]:
    clients = [DiffsyncClient(n) for n in range(num_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def _insert(client: DiffsyncClient, position: int, char: str) -> UniqueChar:
    character = UniqueChar.get_unique_char(char)
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, character))
    return character


def _delete(client: DiffsyncClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def _receive_all(client: DiffsyncClient, sender_id: int) -> None:
    while len(client.message_buffer[sender_id]) != 0:
        client.receive_from_client(sender_id)


def _drain(clients: list[DiffsyncClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def _text(client: DiffsyncClient) -> str:
    return "".join(character.char for character in client.read_state())


# Edits to different regions have no reason to interfere, so they merge cleanly.
def test_disjoint_edits_merge():
    A, B = _build(2)

    _insert(A, 0, "a")
    _insert(A, 1, "b")
    _drain([A, B])

    _insert(A, 0, "x")
    _insert(B, 2, "y")
    _drain([A, B])

    assert _text(A) == _text(B)
    assert _text(A) == "xaby"


# Overlapping insertions are fused rather than decided, so both survive.
def test_concurrent_inserts_both_survive():
    A, B = _build(2)

    _insert(A, 0, "-")
    _drain([A, B])

    x = _insert(A, 0, "x")
    y = _insert(B, 0, "y")
    _drain([A, B])

    assert _text(A) == _text(B)
    assert x in A.read_state()
    assert y in A.read_state()


# Concurrent deletes in the same region are unioned. Each client deleted a
# different one of the two characters, so both deletions apply and only b is
# left; nothing is lost here, the union is exactly what the two edits said.
def test_concurrent_deletes_in_the_same_region_are_unioned():
    A, B = _build(2)

    _insert(A, 0, "a")
    _insert(A, 1, "a")
    _insert(A, 2, "b")
    _drain([A, B])

    _delete(A, 1)
    _delete(B, 0)
    _drain([A, B])

    assert _text(A) == _text(B)
    assert _text(A) == "b"


# A deleted character comes back through a later merge. C0's last two receives
# take in C1's branch and then C2's, which carries the delete of x; the merge
# base is rebuilt over the common ancestors and predates the delete, so the
# diff renders C0's side as deleting x at the front and re-inserting it further
# along, C2's delete fuses into that leading delete, and the re-insertion puts
# x back; every replica settles on the text that contains it. The schedule is
# minimised from fuzz seed 23; the two spare characters keep the id spacing of
# the trace it was minimised from.
def test_a_merged_delete_can_be_undone_by_a_later_merge():
    C0, C1, C2 = _build(3)

    UniqueChar.get_unique_char("s")
    o = UniqueChar.get_unique_char("o")
    a = UniqueChar.get_unique_char("a")
    n = UniqueChar.get_unique_char("n")
    z = UniqueChar.get_unique_char("z")
    x = UniqueChar.get_unique_char("x")
    UniqueChar.get_unique_char("f")
    k = UniqueChar.get_unique_char("k")
    d = UniqueChar.get_unique_char("d")
    s = UniqueChar.get_unique_char("s")

    C2.perform_local_insert(ClientInsertOperation(2, 0, o))
    C0.perform_local_insert(ClientInsertOperation(0, 0, a))
    C0.perform_local_insert(ClientInsertOperation(0, 1, n))
    _receive_all(C0, 2)
    C1.perform_local_insert(ClientInsertOperation(1, 0, z))
    _receive_all(C0, 1)
    C2.perform_local_insert(ClientInsertOperation(2, 0, x))
    _receive_all(C1, 2)
    C0.perform_local_insert(ClientInsertOperation(0, 4, k))
    _receive_all(C2, 0)
    C2.perform_local_insert(ClientInsertOperation(2, 0, d))
    C1.perform_local_insert(ClientInsertOperation(1, 2, s))
    C0.perform_local_delete(ClientDeleteOperation(0, 2, n))
    _receive_all(C0, 1)
    C2.perform_local_delete(ClientDeleteOperation(2, 1, x))
    _receive_all(C0, 2)

    assert x in C0.read_state()

    _drain([C0, C1, C2])
    assert x in C0.read_state()
    assert _text(C0) == _text(C1) == _text(C2)


# The reference folds the heads in the order the replica learned them, and on
# this schedule the replica that learned two of the commits the other way round
# would read a different text. Sorting the ids before the fold, the fix
# proposed upstream, makes every replica fold alike; the pairwise merge never
# depended on the order, so two replicas agreed either way.
def test_learning_order_does_not_change_the_merged_text():
    A, B, C = _build(3)

    _insert(A, 0, "a")
    _drain([A, B, C])

    _insert(A, 1, "b")
    _insert(B, 1, "c")
    _insert(C, 1, "d")

    B.receive_from_client(A.client_id)
    B.receive_from_client(C.client_id)
    C.receive_from_client(A.client_id)
    C.receive_from_client(B.client_id)
    _drain([A, B, C])

    assert A.minigit.commits.keys() == C.minigit.commits.keys()
    assert _text(A) == _text(B) == _text(C)


# The two lines that register the algorithm, exercised the way the checker will reach it.
def test_registered_algorithm_converges():
    random.seed(1)
    server, clients = diffsync_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_disjoint_edits_merge()
    test_concurrent_inserts_both_survive()
    test_concurrent_deletes_in_the_same_region_are_unioned()
    test_a_merged_delete_can_be_undone_by_a_later_merge()
    test_learning_order_does_not_change_the_merged_text()
    test_registered_algorithm_converges()
    print("OK")
