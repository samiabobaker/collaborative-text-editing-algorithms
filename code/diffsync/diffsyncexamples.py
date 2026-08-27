from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from diffsync.diffsyncclient import DiffsyncClient
from unique_char.uniquechar import UniqueChar


def __setup(number_of_clients: int) -> list[DiffsyncClient]:
    clients = [DiffsyncClient(n) for n in range(number_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def __insert(client: DiffsyncClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: DiffsyncClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __receive_all(client: DiffsyncClient, sender_id: int) -> None:
    """Take in everything queued from one peer."""
    while len(client.message_buffer[sender_id]) != 0:
        client.receive_from_client(sender_id)


def __drain(clients: list[DiffsyncClient]) -> None:
    """Deliver commits until every client holds the same set of them."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[DiffsyncClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def disjoint_edits_example():
    """Concurrent edits to different regions of the text.

    Each client commits its edit over the head it last saw, so the two commits
    are siblings. Merging them diffs each against their common parent, and
    because the two patches touch different positions neither has to give way.
    """
    A, B = __setup(2)

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __drain([A, B])

    __insert(A, 0, "x")
    __insert(B, 2, "y")

    __drain([A, B])
    __report([A, B])


def both_sides_win_example():
    """Two clients insert at the same position at once.

    The two patches land at the same position, so the tie-break decides which
    one is consumed first and both are emitted; applying them in turn places
    the two characters side by side. There is no winner and no conflict
    marker, which is the property the algorithm is built for.
    """
    A, B = __setup(2)

    __insert(A, 0, "-")
    __drain([A, B])

    __insert(A, 0, "x")
    __insert(B, 0, "y")

    __drain([A, B])
    __report([A, B])


def union_of_deletes_example():
    """Two clients each delete a different one of two neighbouring characters.

    The text is aa followed by b. A deletes the second a and B deletes the
    first, so every a has a delete covering it; the two hunks sit side by side
    and both apply, and only b remains. Nothing is lost here, both deletions
    were asked for; what the fusing of genuinely overlapping edits can cost is
    shown by the resurrection example.
    """
    A, B = __setup(2)

    __insert(A, 0, "a")
    __insert(A, 1, "a")
    __insert(A, 2, "b")
    __drain([A, B])
    print("both hold:", *A.read_state(), sep="")

    __delete(A, 1)
    __delete(B, 0)
    print("each deleted one a:")
    __report([A, B])

    __drain([A, B])
    print("after merging:")
    __report([A, B])


def resurrection_example():
    """A deleted character comes back through a later merge.

    C0's last two receives take in C1's branch and then C2's, which carries
    the delete of x. The base for that last merge is rebuilt over the common
    ancestors and predates the delete, so the diff renders C0's side as
    deleting x at the front and re-inserting it further along; C2's delete of
    x fuses into that leading delete and becomes redundant, and the trailing
    re-insertion puts x back. So x is in C0's document even though C0 has
    merged its delete and nobody typed it again, and every replica settles on
    the text that contains it. The schedule is minimised
    from fuzz seed 23; the two spare characters keep the id spacing of the
    trace it came from.
    """
    C0, C1, C2 = __setup(3)

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
    __receive_all(C0, 2)
    C1.perform_local_insert(ClientInsertOperation(1, 0, z))
    __receive_all(C0, 1)
    C2.perform_local_insert(ClientInsertOperation(2, 0, x))
    __receive_all(C1, 2)
    C0.perform_local_insert(ClientInsertOperation(0, 4, k))
    __receive_all(C2, 0)
    C2.perform_local_insert(ClientInsertOperation(2, 0, d))
    C1.perform_local_insert(ClientInsertOperation(1, 2, s))
    C0.perform_local_delete(ClientDeleteOperation(0, 2, n))
    __receive_all(C0, 1)
    C2.perform_local_delete(ClientDeleteOperation(2, 1, x))
    print("C2 deleted x;  C2:", *C2.read_state(), sep="")

    __receive_all(C0, 2)
    print("C0 after merging C2's branch, x included:")
    __report([C0])

    __drain([C0, C1, C2])
    print("fully delivered, x still present:")
    __report([C0, C1, C2])


def learning_order_example():
    """The same commits learned in two orders still merge to the same text.

    Three clients insert after a at once. B learns A's commit and then C's,
    while C learns A's and then B's. The reference folds the heads in the
    order the client happened to learn them, and C would read d before c
    here; with the ids sorted before the fold, the fix proposed upstream,
    all three read the same text.
    """
    A, B, C = __setup(3)

    __insert(A, 0, "a")
    __drain([A, B, C])

    __insert(A, 1, "b")
    __insert(B, 1, "c")
    __insert(C, 1, "d")

    B.receive_from_client(A.client_id)
    B.receive_from_client(C.client_id)
    C.receive_from_client(A.client_id)
    C.receive_from_client(B.client_id)

    __drain([A, B, C])
    __report([A, B, C])


if __name__ == "__main__":
    print("--- disjoint edits")
    disjoint_edits_example()
    print("--- both sides win")
    both_sides_win_example()
    print("--- a union of deletes")
    union_of_deletes_example()
    print("--- a deleted character comes back")
    resurrection_example()
    print("--- learning order")
    learning_order_example()
