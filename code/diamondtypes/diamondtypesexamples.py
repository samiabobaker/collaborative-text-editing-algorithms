from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from diamondtypes.diamondtypesclient import DiamondTypesClient
from unique_char.uniquechar import UniqueChar


def __insert(client: DiamondTypesClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: DiamondTypesClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[DiamondTypesClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __position_of(client: DiamondTypesClient, char: str) -> int:
    return [c.char for c in client.read_state()].index(char)


def __report(clients: list[DiamondTypesClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def concurrent_runs_example():
    """Two clients type a run into an empty document at the same time.

    Neither has seen the other, so "a" and "x" are both anchored between the start
    and the end of the document and their ids decide, putting "a" first. "b" is
    anchored after "a" and "y" after "x", so each run stays whole behind the
    character that opened it: "abxy".
    """
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")

    __insert(B, 0, "x")
    __insert(B, 1, "y")

    __drain([A, B])
    __report([A, B])


def concurrent_insert_and_delete_example():
    """A deletes a character that B never saw, while B inserts one A never saw.

    A types "ab" and deletes the "b"; B, having seen nothing, types "c" at the
    start. The tombstone left behind by the delete keeps its place after "a", so
    it is still there for anything anchored to it, and it is skipped when the
    document is read. "a" and "c" are both anchored between the start and the end
    of the document, so their ids decide: "ac".

    Both the Rust implementation and the reference TypeScript implementation
    produce "ac" for this trace.
    """
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(B, 0, "c")
    __delete(A, 1)

    __drain([A, B])
    __report([A, B])


def shared_left_anchor_example():
    """Three characters anchored after the same one, and the run that is not split.

    A types "ab". B has seen only "a" and types "x" after it, so "x" is anchored
    between "a" and the end of the document. C has seen "ab" and types "y" after
    "a", so "y" is anchored between "a" and "b".

    "y" was typed against a version that already had "b", so it just goes between
    the two. "x" is the one that has to be ordered against them. Its right anchor
    is further away than "y"'s, so the scan does not stop inside the "y", "b" pair
    but steps over it, and against "b", which "x" shares both anchors with, the
    smaller id wins. "x" ends up last: "aybx".
    """
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)
    C = DiamondTypesClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "a")
    __insert(A, 1, "b")

    B.receive_from_client(A.client_id)  # B learns about a, but not about b
    __insert(B, 1, "x")

    C.receive_from_client(A.client_id)  # C learns about a
    C.receive_from_client(A.client_id)  # and about b
    __insert(C, 1, "y")

    __drain([A, B, C])
    __report([A, B, C])


def run_splitting_example():
    """The case that separates YjsMod from Yjs, run through eg-walker.

    The scenario is the one in sync9examples. B types "xy" as one run. A, unlike B,
    has already seen the character P that sits to the right, and inserts a single
    character just after "x".

    Diamond Types uses the right anchors to keep B's run contiguous and gives
    "xyaP", which is what the repository's YjsMod implementation gives. Yjs and
    Sync9 compare ids sooner and split the run, giving "xayP". This is also the
    scenario that tells the FugueMax right origin rule from plain Fugue's: taking
    the right origin only when it shares the new item's left origin gives "xayP"
    here instead, so it is the run, not the tie break, that pins the rule.
    """
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)
    W = DiamondTypesClient(2)

    A.set_clients([A, B, W])
    B.set_clients([A, B, W])
    W.set_clients([A, B, W])

    __insert(W, 0, "P")  # W types P
    __insert(B, 0, "x")  # B types x, without ever having seen P

    W.receive_from_client(B.client_id)  # W learns about x
    A.receive_from_client(W.client_id)  # A learns about P
    A.receive_from_client(B.client_id)  # A learns about x

    __insert(B, 1, "y")  # B continues its run: "xy"
    __insert(A, __position_of(A, "x") + 1, "a")  # A inserts just after x

    __drain([A, B, W])
    __report([A, B, W])


def three_way_concurrency_example():
    """Three clients all editing the same spot, each having seen one of the others.

    Each client types one character into an empty document, so "a", "b" and "c"
    are all anchored between the start and the end and their ids order them. A
    then learns about "c" and types "x" between "a" and "c"; B learns about "a",
    which lands ahead of its own "b", and types "y" between the two.

    "x" and "y" are both anchored after "a", so both come before "b", which is
    anchored at the start of the document. Their right anchors then separate them,
    and "x", whose right anchor is the further away of the two, goes first:
    "axybc". Each client's pair of characters still comes out adjacent.
    """
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)
    C = DiamondTypesClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "a")
    __insert(B, 0, "b")
    __insert(C, 0, "c")

    A.receive_from_client(C.client_id)
    B.receive_from_client(A.client_id)
    C.receive_from_client(B.client_id)

    __insert(B, 1, "y")
    __insert(A, 1, "x")

    __drain([A, B, C])
    __report([A, B, C])


if __name__ == "__main__":
    print("--- concurrent runs")
    concurrent_runs_example()
    print("--- concurrent insert and delete")
    concurrent_insert_and_delete_example()
    print("--- shared left anchor")
    shared_left_anchor_example()
    print("--- run splitting")
    run_splitting_example()
    print("--- three way concurrency")
    three_way_concurrency_example()
