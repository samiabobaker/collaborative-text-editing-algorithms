import random

from algorithm_setup.algorithm_setup import loro_setup, sync9_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from loro.loroclient import LoroClient
from unique_char.uniquechar import UniqueChar


def insert(client: LoroClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def delete(client: LoroClient, position: int) -> None:
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, client.read_state()[position]))


def drain(clients: list[LoroClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def text(chars: list[UniqueChar]) -> str:
    return "".join(char.char for char in chars)


# Loro's own test_yjs_interleave (crates/loro-internal/tests/fugue.rs): "b" has the end of
# the document as its right origin and "1" has "2", so reverse right origin order puts "b"
# first rather than between "1" and "2".
def test_yjs_interleaving_case_is_not_interleaved():
    A = LoroClient(0)
    B = LoroClient(1)
    C = LoroClient(2)
    for client in [A, B, C]:
        client.set_clients([A, B, C])

    insert(C, 0, "2")
    A.receive_from_client(C.client_id)
    insert(A, 0, "1")
    insert(B, 0, "b")

    drain([A, B, C])

    assert text(A.read_state()) == "b12"
    assert text(B.read_state()) == "b12"
    assert text(C.read_state()) == "b12"


# Two concurrent inserts sharing both origins have nothing but their peers to separate
# them, and the peer ids break the tie ascending (crdt_rope.rs line 187).
def test_shared_origins_tie_break_by_peer():
    A = LoroClient(0)
    B = LoroClient(1)
    A.set_clients([A, B])
    B.set_clients([A, B])

    insert(A, 0, "a")
    B.receive_from_client(A.client_id)
    insert(A, 1, "b")
    B.receive_from_client(A.client_id)

    insert(A, 1, "x")
    insert(B, 1, "y")

    drain([A, B])

    assert text(A.read_state()) == "axyb"
    assert text(B.read_state()) == "axyb"


# The scan for a right origin stops at the first span that is not future, deleted or not
# (crdt_rope.rs lines 110-149), so a tombstone can be a right origin.
def test_right_origin_can_be_a_tombstone():
    A = LoroClient(0)
    B = LoroClient(1)
    A.set_clients([A, B])
    B.set_clients([A, B])

    insert(A, 0, "a")
    insert(A, 1, "b")
    insert(A, 2, "c")
    delete(A, 1)
    insert(A, 1, "x")

    drain([A, B])

    assert text(A.read_state()) == "axc"
    assert text(B.read_state()) == "axc"
    assert text(B.read_state_with_tombstones()) == "axbc"

    rope = {element.char.char: element for element in B.document.rope}
    assert rope["x"].origin_left == rope["a"].op_id
    assert rope["x"].origin_right == rope["b"].op_id


# Definition 4's right parent rule, the one place where Loro is paper Fugue rather than
# FugueMax. "g" and "h" are concurrent and share "a" as their left origin. "g" has "e" as
# its right origin and "h" has the end of the document, but "e" does not share their left
# origin, so under Definition 4 it is not a right parent and collapses to nothing to
# compare. Both sides are then equal and the peer ids decide, giving "baghe". FugueMax
# would compare "e"'s position and put "h" first, giving "bahge", which is exactly what
# removing the collapse at crdt_rope.rs lines 203-207 produces. This is the shortest
# schedule that separates the two rules.
def test_definition_4_right_parent_rule():
    A = LoroClient(0)
    B = LoroClient(1)
    C = LoroClient(2)
    for client in [A, B, C]:
        client.set_clients([A, B, C])

    insert(A, 0, "a")
    C.receive_from_client(A.client_id)
    insert(C, 0, "b")  # C: "ba"
    insert(B, 0, "e")  # B has seen nothing yet
    B.receive_from_client(A.client_id)  # B: "ae"
    insert(B, 1, "g")  # B: "age", so "g" takes "e" as its right origin
    insert(C, 2, "h")  # C: "bah", so "h" takes the end of the document

    drain([A, B, C])

    assert text(A.read_state()) == "baghe"
    assert text(B.read_state()) == "baghe"
    assert text(C.read_state()) == "baghe"


# A remote insert is integrated against the sender's version of the rope, so a delete the
# sender had not seen is rolled back for the duration of the integration.
def test_checkout_rolls_a_concurrent_delete_back():
    A = LoroClient(0)
    B = LoroClient(1)
    A.set_clients([A, B])
    B.set_clients([A, B])

    insert(A, 0, "a")
    insert(A, 1, "b")
    insert(A, 2, "c")
    drain([A, B])

    delete(A, 1)  # A removes "b" while B, which still sees it, types after it
    insert(B, 2, "x")

    drain([A, B])

    assert text(A.read_state()) == "axc"
    assert text(B.read_state()) == "axc"
    assert text(A.read_state_with_tombstones()) == "abxc"


# Random traces have to converge, and the checker exercises delete and receive orders that
# the hand written cases do not.
def test_trace_converges():
    random.seed(7)
    server, clients = loro_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


# Loro's rope and the repo's Sync9 document order concurrent inserts the same way, so one
# trace has to leave the two character for character identical. UniqueChar has no __eq__ and
# hands out ids from a global counter, so the counter is reset before each run and the states
# are compared by value.
def test_loro_matches_sync9():
    states: list[list[tuple[str, int]]] = []
    for setup in [loro_setup, sync9_setup]:
        UniqueChar.now = 0
        random.seed(20)
        server, clients = setup(3)
        client_dict: dict[int, ClientDevice] = {client.client_id: client for client in clients}
        assert convergence_checker(client_dict, server, 60) is True
        states.append([(char.char, char.id) for char in clients[0].read_state()])

    assert len(states[0]) > 10
    assert states[0] == states[1]


if __name__ == "__main__":
    test_yjs_interleaving_case_is_not_interleaved()
    test_shared_origins_tie_break_by_peer()
    test_right_origin_can_be_a_tombstone()
    test_definition_4_right_parent_rule()
    test_checkout_rolls_a_concurrent_delete_back()
    test_trace_converges()
    test_loro_matches_sync9()
    print("OK")
