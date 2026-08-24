import random

from algorithm_setup.algorithm_setup import sync7_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from sync7.sync7client import Sync7Client
from sync7.sync7diff import Sync7Equal, Sync7Replace, apply_diff, compose_diffs
from unique_char.uniquechar import UniqueChar


def _setup(number_of_clients: int) -> list[Sync7Client]:
    clients = [Sync7Client(n) for n in range(number_of_clients)]
    for client in clients:
        client.set_clients(clients)
    return clients


def _insert(client: Sync7Client, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def _delete(client: Sync7Client, position: int) -> None:
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, client.read_state()[position]))


def _drain(clients: list[Sync7Client]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def _word(client: Sync7Client) -> str:
    return "".join(character.char for character in client.read_state())


# Two clients that both edit and both delete, and every message delivered. A merge writes
# one diff component per region rather than running neighbouring ones together, and the
# two clients read the same text out of the graph only if it does.
def test_two_clients_converge():
    A, B = _setup(2)

    _insert(A, 0, "a")
    _insert(B, 0, "b")
    B.receive_from_client(A.client_id)
    _insert(B, 2, "c")
    _insert(A, 0, "d")
    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    _delete(A, 2)
    _delete(B, 2)
    _insert(A, 0, "e")

    _drain([A, B])

    assert _word(A) == _word(B) == "edac"


# A character that was deleted, and whose delete both clients had already merged, is back
# in the text at the end. A merge reads a region from whichever side changed it, and a
# delete next to a character counts as changing the region that character is in, so a
# later merge can take the region from the side that never saw the delete. Nothing here
# records that a character was ever deleted.
def test_a_deleted_character_comes_back():
    A, B = _setup(2)

    _insert(B, 0, "a")
    _delete(B, 0)
    _insert(A, 0, "b")
    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    _insert(B, 0, "c")
    _delete(A, 1)
    _delete(B, 1)
    A.receive_from_client(B.client_id)
    A.receive_from_client(B.client_id)
    _insert(A, 0, "d")

    _drain([A, B])

    assert _word(A) == _word(B) == "dbc"


# Six insertions over three clients, no deletions, and two of the clients end up without
# two of the characters. All three hold the same graph and read every leaf as the same
# text; what differs is the order each learned a version's children in, which is the order
# the merge walks them in when working out where it may cut.
def test_three_clients_can_lose_characters():
    A, B, C = _setup(3)

    _insert(B, 0, "a")
    _insert(C, 0, "b")
    B.receive_from_client(C.client_id)
    _insert(C, 0, "c")
    A.receive_from_client(C.client_id)
    _insert(A, 0, "d")
    A.receive_from_client(B.client_id)
    _insert(A, 0, "e")
    _insert(B, 1, "f")

    _drain([A, B, C])

    assert _word(A) == "edcb"
    assert _word(B) == "edcbaf"
    assert _word(C) == "edcb"


# Reading a version means composing the diffs along the way to it, and a diff is read
# backwards by swapping its two sides, which is what going down the graph rather than up
# needs.
def test_diffs_compose_along_a_chain():
    text = [UniqueChar(character, index) for index, character in enumerate("abcd")]

    # The diff a version holding "abd" keeps against the parent it was made from, "abcd".
    to_abcd = [Sync7Equal(2), Sync7Replace([], [text[2]]), Sync7Equal(1)]
    assert "".join(c.char for c in apply_diff([text[0], text[1], text[3]], to_abcd)) == "abcd"

    # The one a version holding "ab" keeps against "abd". Composing the two gives the diff
    # from "ab" all the way to "abcd", which is what reading a version two steps away does.
    to_abd = [Sync7Equal(2), Sync7Replace([], [text[3]])]
    composed = compose_diffs(to_abd, to_abcd)
    assert "".join(c.char for c in apply_diff([text[0], text[1]], composed)) == "abcd"


# The two lines that register the algorithm, exercised the way the checker will reach it.
def test_registered_algorithm_converges_at_two_clients():
    random.seed(1)
    server, clients = sync7_setup(2)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_two_clients_converge()
    test_a_deleted_character_comes_back()
    test_three_clients_can_lose_characters()
    test_diffs_compose_along_a_chain()
    test_registered_algorithm_converges_at_two_clients()
    print("OK")
