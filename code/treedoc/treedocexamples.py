from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from treedoc.treedocclient import TreedocClient
from treedoc.treedoctree import TreedocMajorNode, TreedocMiniNode
from unique_char.uniquechar import UniqueChar


def __insert(client: TreedocClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: TreedocClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[TreedocClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[TreedocClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def __nodes(node: TreedocMajorNode) -> list[TreedocMiniNode]:
    """Every mini-node of a subtree, tombstones included, in the order of the walk."""
    result: list[TreedocMiniNode] = []

    if node.left_child is not None:
        result += __nodes(node.left_child)

    for mini_node in node.mini_nodes:
        if mini_node.left_child is not None:
            result += __nodes(mini_node.left_child)
        result.append(mini_node)
        if mini_node.right_child is not None:
            result += __nodes(mini_node.right_child)

    if node.right_child is not None:
        result += __nodes(node.right_child)

    return result


def __report_pos_ids(client: TreedocClient) -> None:
    for node in __nodes(client.tree.root):
        tombstone = " (tombstone)" if node.deleted else ""
        print(f"  {node.value.char} {node.pos_id}{tombstone}")


def mini_siblings_example():
    """Figures 3 and 4: concurrent inserts between the same two atoms.

    A types "cd". B and C then both insert between them, concurrently, and both
    allocate the left child of the major node holding d - the same major node,
    but different mini-nodes of it, because the disambiguators differ. That is
    the only way mini-siblings ever arise. W and Y are ordered by disambiguator,
    so by site id here, matching the paper's assumption that dW < dY.

    Inserting X between the two mini-siblings is the case of line 6 of Algorithm
    1: there is no room in the major node between them, so X becomes a child of
    the mini-node W itself, exactly as in the paper's id(X) = [10(0:dW)(1:dX)].
    """
    A = TreedocClient(0)
    B = TreedocClient(1)
    C = TreedocClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "c")
    __insert(A, 1, "d")
    __drain([A, B, C])

    __insert(B, 1, "W")
    __insert(C, 1, "Y")
    __drain([A, B, C])

    __report([A, B, C])
    __report_pos_ids(A)

    __insert(A, 2, "X")
    __drain([A, B, C])

    __report([A, B, C])
    __report_pos_ids(A)


def tombstone_example():
    """A delete concurrent with an insert on either side of the deleted atom.

    A types x and everyone sees it. A then deletes x while B inserts c after it
    and C inserts a before it. The PosIDs of a and c were allocated relative to
    x, so discarding x would lose the two ends of the document; keeping it as a
    tombstone (section 3.3.2) keeps a before c at every replica.
    """
    A = TreedocClient(0)
    B = TreedocClient(1)
    C = TreedocClient(2)

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
    __report_pos_ids(A)


def interleaving_example():
    """Two clients each type a run at the same position at the same time.

    Every character of a run is allocated a PosID relative to the one before it,
    and both clients walk the identifier tree the same way, so the two runs
    allocate the same major nodes level by level and only ever differ in their
    disambiguators. The runs therefore comb together into "axbycz" rather than
    staying contiguous: Treedoc converges, but it interleaves concurrent runs.
    """
    A = TreedocClient(0)
    B = TreedocClient(1)

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


def convergence_example():
    """The same set of atoms delivered in two different orders.

    A replica's document is the set of PosIDs it holds, walked in order, and the
    order of PosIDs does not depend on the order they arrived in. B and C receive
    the same two concurrent insertions the opposite way round and still agree.
    """
    A = TreedocClient(0)
    B = TreedocClient(1)
    C = TreedocClient(2)

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


def pos_id_order_example():
    """The walk of the tree and the order on PosIDs of section 3.1 agree.

    The implementation never compares two PosIDs - it stores them in a tree and
    walks it - so this checks the two definitions against each other on a
    document built out of every case of Algorithm 1.
    """
    A = TreedocClient(0)
    B = TreedocClient(1)
    C = TreedocClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    for position, char in enumerate("cd"):
        __insert(A, position, char)
    __drain([A, B, C])

    # Mini-siblings, then a child of a mini-node, then a run at the front and one
    # at the end of the document.
    __insert(B, 1, "W")
    __insert(C, 1, "Y")
    __drain([A, B, C])
    __insert(A, 2, "X")
    __insert(B, 0, "p")
    __insert(C, 4, "f")
    __drain([A, B, C])
    __delete(A, 3)
    __insert(B, 0, "q")
    __insert(C, 5, "g")
    __drain([A, B, C])

    pos_ids = [node.pos_id for node in __nodes(A.tree.root)]

    for earlier, later in zip(pos_ids, pos_ids[1:], strict=True):
        assert earlier.less_than(later), f"{earlier} should be before {later}"
        assert not later.less_than(earlier), f"{later} should be after {earlier}"

    print(f"{len(pos_ids)} PosIDs in the same order both ways")
    __report_pos_ids(A)


if __name__ == "__main__":
    print("--- mini-siblings")
    mini_siblings_example()
    print("--- tombstones")
    tombstone_example()
    print("--- interleaving")
    interleaving_example()
    print("--- convergence")
    convergence_example()
    print("--- order on PosIDs")
    pos_id_order_example()
