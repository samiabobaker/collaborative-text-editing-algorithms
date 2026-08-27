from __future__ import annotations

from automerge.automergeclient import AutomergeClient
from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


def __insert(client: AutomergeClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: AutomergeClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[AutomergeClient]) -> None:
    """Deliver every pending change, until nothing is left.

    A change is only delivered once its deps have been applied, so a change made on top
    of one that has not arrived waits in the buffer and a single pass is not enough.
    """
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[AutomergeClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def concurrent_insert_at_the_same_position_example():
    """A and B both insert at index 1 of "a", at the same time.

    Both ops have "a" as their predecessor and counter 2, so the tie falls to the actor
    index: (2, A) < (2, B). Children of one predecessor are ordered by descending
    (counter, actor), newest first, so B's character comes first and the text is "axb".
    """
    A = AutomergeClient(0)
    B = AutomergeClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __drain([A, B])

    __insert(A, 1, "b")
    __insert(B, 1, "x")

    __drain([A, B])
    __report([A, B])


def concurrent_inserts_at_the_head_example():
    """Three clients insert at position 0 of the empty document at the same time.

    All three ops have HEAD as their predecessor and counter 1, so ordering them by
    descending (counter, actor) gives C, then B, then A: "cba".
    """
    A = AutomergeClient(0)
    B = AutomergeClient(1)
    C = AutomergeClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "a")
    __insert(B, 0, "b")
    __insert(C, 0, "c")

    __drain([A, B, C])
    __report([A, B, C])


def delete_versus_concurrent_insert_example():
    """A deletes "b" while B inserts "c" after it.

    The delete only adds a succ pointer to "b", so "b" stays in the columns as a
    tombstone, and "c" keeps it as its predecessor. The text is "ac", and the tombstone
    is still there to anchor anything else inserted at that spot.
    """
    A = AutomergeClient(0)
    B = AutomergeClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __drain([A, B])

    __delete(A, 1)
    __insert(B, 2, "c")

    __drain([A, B])
    __report([A, B])
    print("0 with tombstones:", *A.read_state_with_tombstones(), sep="")


def interleaving_example():
    """A types "ab" while B types "xy" at the same position.

    B's run lands between "a" and "b", giving "axyb". This is the backward interleaving
    the interleaving checker measures, and it is inherent to the RGA tie break rather
    than anything specific to Automerge.
    """
    A = AutomergeClient(0)
    B = AutomergeClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __drain([A, B])

    __insert(A, 1, "b")
    __insert(B, 1, "x")
    __insert(B, 2, "y")

    __drain([A, B])
    __report([A, B])


if __name__ == "__main__":
    print("--- concurrent insert at the same position")
    concurrent_insert_at_the_same_position_example()
    print("--- concurrent inserts at the head")
    concurrent_inserts_at_the_head_example()
    print("--- delete versus concurrent insert")
    delete_versus_concurrent_insert_example()
    print("--- interleaving")
    interleaving_example()
