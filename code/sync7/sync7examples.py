from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from sync7.sync7client import Sync7Client
from unique_char.uniquechar import UniqueChar


def __setup(number_of_clients: int) -> list[Sync7Client]:
    clients = [Sync7Client(n) for n in range(number_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def __insert(client: Sync7Client, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: Sync7Client, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[Sync7Client]) -> None:
    """Deliver every message there is, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[Sync7Client]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def interleaving_example():
    """Two clients type a run of characters at the same position at once."""
    A, B = __setup(2)

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")

    __insert(B, 0, "x")
    __insert(B, 1, "y")
    __insert(B, 2, "z")

    __drain([A, B])
    __report([A, B])


def concurrent_insert_and_delete_example():
    """A deletes the only character while B and C insert around it."""
    A, B, C = __setup(3)

    __insert(A, 0, "b")
    __drain([A, B, C])

    __delete(A, 0)
    __insert(B, 1, "c")
    __insert(C, 0, "a")

    __drain([A, B, C])
    __report([A, B, C])


def deleted_character_comes_back_example():
    """Two clients, four characters, and one of the two that were deleted is back.

    A merge is decided by which stretches of text each side left alone since the last
    point both sides had in common. A stretch one side changed and the other did not is
    the changed side's to decide, and a delete of a neighbouring character is a change
    that takes in the whole region it falls in. So a delete that has already been merged
    once can be undone by a later merge that reads the region around it from the side
    that never made the delete. Nothing in the algorithm records that a character was
    deleted, only what each version's text is, so there is nothing left to say it should
    not come back.
    """
    A, B = __setup(2)

    __insert(B, 0, "a")
    __delete(B, 0)
    __insert(A, 0, "b")
    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    __insert(B, 0, "c")
    __delete(A, 1)
    __delete(B, 1)
    A.receive_from_client(B.client_id)
    A.receive_from_client(B.client_id)
    __insert(A, 0, "d")

    __drain([A, B])
    __report([A, B])
    print('typed "a", "b", "c" and "d", deleted "a" and "b"')


def three_clients_do_not_converge_example():
    """Six characters typed by three clients, nothing deleted, and two of them lose two.

    All three end up with the same version graph, fold its leaves in the same order, and
    read each leaf as the same text. What differs is the order each client learned a
    version's children in, which is the order it walks them in when it works out which
    stretches of text a merge may cut at. Here the last merge is over the same two texts
    on all three, and the one client that learned two of the children the other way round
    merges them differently. Sorting the children by version id before every merge makes
    all three agree on this trace.
    """
    A, B, C = __setup(3)

    __insert(B, 0, "a")
    __insert(C, 0, "b")
    B.receive_from_client(C.client_id)
    __insert(C, 0, "c")
    A.receive_from_client(C.client_id)
    __insert(A, 0, "d")
    A.receive_from_client(B.client_id)
    __insert(A, 0, "e")
    __insert(B, 1, "f")

    __drain([A, B, C])
    __report([A, B, C])


if __name__ == "__main__":
    print("--- interleaving")
    interleaving_example()
    print("--- concurrent insert and delete")
    concurrent_insert_and_delete_example()
    print("--- a deleted character comes back")
    deleted_character_comes_back_example()
    print("--- three clients")
    three_clients_do_not_converge_example()
