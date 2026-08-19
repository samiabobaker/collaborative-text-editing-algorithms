from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from loro.loroclient import LoroClient
from unique_char.uniquechar import UniqueChar


def __insert(client: LoroClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: LoroClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(clients: list[LoroClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __report(clients: list[LoroClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def backward_interleaving_example():
    """Two clients each type a passage backwards, by prepending.

    Loro's own test_backward_interleaving
    (crates/loro-internal/tests/fugue.rs). Each prepended character takes the
    one before it as its right origin, and ordering siblings in reverse right
    origin order is what keeps the two passages apart. The expected result is
    "Hello World!".
    """
    A = LoroClient(0)
    B = LoroClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    for char in ["o", "l", "l", "e", "H"]:  # A types "Hello" by prepending
        __insert(A, 0, char)
    for char in ["!", "d", "l", "r", "o", "W", " "]:  # B types " World!" by prepending
        __insert(B, 0, char)

    __drain([A, B])
    __report([A, B])


def yjs_interleaving_example():
    """The case Yjs interleaves and Loro does not.

    Loro's own test_yjs_interleave (crates/loro-internal/tests/fugue.rs). "b"
    is concurrent with "1" and has seen nothing, so its right origin is the
    end of the document while "1" has "2" as its right origin. The two share a
    left origin, the start, so the reverse right origin rule puts "b" first
    and the expected result is "b12".
    """
    A = LoroClient(0)
    B = LoroClient(1)
    C = LoroClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(C, 0, "2")
    A.receive_from_client(C.client_id)
    __insert(A, 0, "1")
    __insert(B, 0, "b")

    __drain([A, B, C])
    __report([A, B, C])


def same_origin_tie_break_example():
    """Two concurrent inserts with nothing to tell them apart but their peers.

    Both land between "a" and "b", so they share a left origin and a right
    origin and neither reverse right origin order nor the Definition 4 right
    parent rule has anything to say. The peer ids break the tie, ascending
    (crdt_rope.rs line 187), so the expected result is "axyb".
    """
    A = LoroClient(0)
    B = LoroClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    B.receive_from_client(A.client_id)
    __insert(A, 1, "b")
    B.receive_from_client(A.client_id)

    __insert(A, 1, "x")
    __insert(B, 1, "y")

    __drain([A, B])
    __report([A, B])


def tombstone_origin_example():
    """An insert that anchors its right origin on a tombstone.

    The scan for a right origin stops at the first span that is not `future`,
    deleted or not (crdt_rope.rs, lines 110-149), so a tombstone can be a
    right origin. Here "b" is deleted and "x" is then typed where it used to
    be, giving the visible text "axc" and the rope order "axbc" with "x"
    anchored between "a" and the tombstone.
    """
    A = LoroClient(0)
    B = LoroClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")
    __delete(A, 1)  # delete b, leaving the tombstone in place
    __insert(A, 1, "x")  # between a and b's tombstone

    __drain([A, B])
    __report([A, B])

    print("rope: ", "".join(str(c) for c in B.read_state_with_tombstones()))
    print(
        "origins:",
        " ".join(
            f"{char}[{origin_left if origin_left is not None else 'start'}"
            f",{origin_right if origin_right is not None else 'end'}]"
            for char, origin_left, origin_right in B.read_origins()
        ),
    )


if __name__ == "__main__":
    print("--- backward interleaving")
    backward_interleaving_example()
    print("--- yjs interleaving")
    yjs_interleaving_example()
    print("--- same origin tie break")
    same_origin_tie_break_example()
    print("--- tombstone right origin")
    tombstone_origin_example()
