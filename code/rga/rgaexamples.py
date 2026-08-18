from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from rga.rgaclient import RGAClient
from unique_char.uniquechar import UniqueChar


def __insert(client: RGAClient, position: int, char: str) -> None:
    client.perform_local_insert(
        ClientInsertOperation(
            client.client_id, position, UniqueChar.get_unique_char(char)
        )
    )


def __delete(client: RGAClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(
        ClientDeleteOperation(client.client_id, position, character)
    )


def __drain(clients: list[RGAClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[RGAClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")





def figure_2_example():
    """The TI tree of Figure 2, built by one replica.

    Nodes are read parent first, children youngest first. So inserting a at the
    front makes it a second child of the root and it is read before x, even
    though x is older; then inserting b after x makes it x's youngest child, so
    it is read before c. The tree ends up as the paper's N2, denoting "axbc".
    """
    A = RGAClient(0)

    A.set_clients([A])

    __insert(A, 0, "x")  # x under the root
    __insert(A, 1, "c")  # c under x
    __insert(A, 0, "a")  # a under the root, younger than x
    print("s(N1):", "".join(str(c) for c in A.read_state()))

    __insert(A, 2, "b")  # b under x, younger than c
    print("s(N2):", "".join(str(c) for c in A.read_state()))


def strong_list_specification_example():
    """The execution of Figure 3: a delete concurrent with inserts either side.

    R1 types x and everyone sees it. Then R1 deletes x while R2 inserts c after
    it and R3 inserts a before it, all concurrently. The tombstone for x keeps
    both insertions anchored, so every replica agrees a comes before c - which
    is what the strong list specification demands, and what the same execution
    fails to give under some other protocols.
    """
    A = RGAClient(0)
    B = RGAClient(1)
    C = RGAClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "x")
    __drain([A, B, C])

    __delete(A, 0)
    __insert(B, 1, "c")
    __insert(C, 0, "a")

    __drain([A, B, C])
    __report([A, B, C])


def forward_typing_example():
    """Two clients each type a run left to right at the same position at once.

    Each character is inserted after the one before it, so a run is a chain of
    parents and children and therefore a whole subtree. Subtrees are read
    without a break, so the two runs come out contiguous: whichever of the two
    first characters wins at the root takes its entire run with it.
    """
    A = RGAClient(0)
    B = RGAClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")

    __insert(B, 0, "x")
    __insert(B, 1, "y")
    __insert(B, 2, "z")

    __drain([A, B])
    __report([A, B])


def backward_typing_interleaving_example():
    """The same two runs, typed right to left instead - and RGA interleaves.

    Typing backwards means every character is inserted at position 0, so they
    all become children of the root rather than a chain. The six characters are
    now siblings competing in one list, ordered by timestamp alone, and since
    the two clients issued their timestamps with the same counters the runs
    comb together into "xaybzc".
    """
    A = RGAClient(0)
    B = RGAClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "c")
    __insert(A, 0, "b")
    __insert(A, 0, "a")

    __insert(B, 0, "z")
    __insert(B, 0, "y")
    __insert(B, 0, "x")

    __drain([A, B])
    __report([A, B])


def convergence_example():
    """The same set of nodes delivered in two different orders.

    A replica's tree depends on the set of nodes it holds and nothing else, so
    the delivery order cannot matter. B and C receive the same two concurrent
    insertions the opposite way round and still agree.
    """
    A = RGAClient(0)
    B = RGAClient(1)
    C = RGAClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "-")
    __drain([A, B, C])

    __insert(B, 1, "b")
    __insert(C, 1, "c")

    B.receive_from_client(C.client_id)
    C.receive_from_client(B.client_id)
    __drain([A, B, C])
    __report([A, B, C])


if __name__ == "__main__":
    print("--- figure 2 tree")
    figure_2_example()
    print("--- strong list specification")
    strong_list_specification_example()
    print("--- forward typing")
    forward_typing_example()
    print("--- backward typing")
    backward_typing_interleaving_example()
    print("--- convergence")
    convergence_example()
