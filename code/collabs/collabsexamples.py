from __future__ import annotations

from collabs.collabsclient import CollabsClient
from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


def __setup(number_of_clients: int) -> list[CollabsClient]:
    clients = [CollabsClient(n) for n in range(number_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def __insert(client: CollabsClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: CollabsClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[CollabsClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[CollabsClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def interleaving_example():
    """B types at the front of what A typed, while A carries on typing.

    B's character becomes a left child of a, and A's second character extends A's
    own waypoint instead of competing with it, so A's run stays together.
    """
    A, B = __setup(2)

    __insert(A, 0, "a")
    __drain([A, B])

    __insert(B, 0, "x")
    __insert(A, 1, "b")

    __drain([A, B])
    __report([A, B])


def same_author_contiguity_example():
    """Two other clients type around a run that a third client is still typing.

    A's own run stays contiguous against B's character, which lands in front of it,
    but C types between A's two characters and does land in the middle: the run is
    protected against a competing run, not against a deliberate insertion into it.
    """
    A, B, C = __setup(3)

    __insert(A, 0, "a")
    __drain([A, B, C])

    __insert(A, 1, "b")
    __insert(B, 0, "x")

    C.receive_from_client(A.client_id)
    __insert(C, 1, "y")

    __drain([A, B, C])
    __report([A, B, C])


def sender_id_order_example():
    """Two clients type one character each at the same position, at once.

    Both characters are right children of the root, so nothing about the tree
    separates them and the sender decides: they come out in ascending sender order,
    which puts client 0's character first even though client 1 typed first.
    """
    A, B = __setup(2)

    __insert(B, 0, "b")
    __insert(A, 0, "a")

    __drain([A, B])
    __report([A, B])


def tombstone_reinsert_example():
    """A types into a gap it has already deleted from.

    A deletes b while B types x where b was. A's d then goes to the leftmost
    descendant of x, landing between a and x in the gap b left; the deleted b
    keeps its place as a tombstone, which is what holds x and d where b was.
    """
    A, B = __setup(2)

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")
    __drain([A, B])

    __delete(A, 1)
    __insert(B, 1, "x")
    __drain([A, B])

    __insert(A, 1, "d")

    __drain([A, B])
    __report([A, B])


if __name__ == "__main__":
    print("--- interleaving")
    interleaving_example()
    print("--- same author contiguity")
    same_author_contiguity_example()
    print("--- sender id order")
    sender_id_order_example()
    print("--- tombstone reinsert")
    tombstone_reinsert_example()
