import random

from algorithm_setup.algorithm_setup import (
    DeviceSetup,
    diamondtypes_setup,
    fugue_setup,
    fuguemax_setup,
    yjsmod_setup,
)
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientReceiveFromClientOperation
from diamondtypes.diamondtypesclient import DiamondTypesClient
from unique_char.uniquechar import UniqueChar


def insert(client: ClientDevice, position: int, char: str) -> None:
    client.perform_operation(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def delete(client: ClientDevice, position: int) -> None:
    character = client.read_state()[position]
    client.perform_operation(ClientDeleteOperation(client.client_id, position, character))


def receive(client: ClientDevice, sender: ClientDevice) -> None:
    client.perform_operation(ClientReceiveFromClientOperation(client.client_id, sender.client_id))


def drain(clients: list[ClientDevice]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.perform_operation(ClientReceiveFromClientOperation(client.client_id, sender_id))
                progressed = True


def text(client: ClientDevice) -> str:
    return "".join(character.char for character in client.read_state())


def two_clients(setup: DeviceSetup) -> tuple[ClientDevice, ClientDevice]:
    _, clients = setup(2)
    return clients[0], clients[1]


def right_origin_schedule(setup: DeviceSetup) -> list[str]:
    """Type "a" and "b" concurrently, then "c" and "d" after "a" from two different views."""
    A, B = two_clients(setup)

    insert(A, 0, "a")  # A types "a" into an empty document
    insert(B, 0, "b")  # B types "b" into an empty document, having seen nothing
    receive(B, A)  # B learns about "a", so B reads "ab"
    insert(B, 1, "c")  # B types "c" after "a", between "a" and "b"
    insert(A, 1, "d")  # A types "d" after "a", and A still cannot see "b"

    drain([A, B])

    return [text(A), text(B)]


def tombstone_anchor_schedule(setup: DeviceSetup) -> list[str]:
    """Delete the only character, then type into position 0 from either side of the delete."""
    A, B = two_clients(setup)

    insert(A, 0, "a")  # A types "a"
    receive(B, A)  # B learns about "a"
    delete(A, 0)  # A deletes it, so A reads an empty document
    insert(A, 0, "x")  # A types "x" at position 0, with only the tombstone in the way
    insert(B, 0, "y")  # B types "y" at position 0, and B can still see "a"

    drain([A, B])

    return [text(A), text(B)]


# A tombstone keeps the place it held, so a concurrent insert is still ordered against
# the character that was deleted. Both the Rust implementation and the reference
# TypeScript implementation answer "ac" here, not "ca".
def test_tombstone_keeps_its_place():
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    insert(A, 0, "a")
    insert(A, 1, "b")
    insert(B, 0, "c")
    delete(A, 1)

    drain([A, B])

    assert text(A) == "ac"
    assert text(B) == "ac"
    # The tombstone is still in the document, between the two visible characters.
    assert "".join(character.char for character in A.read_state_with_tombstones()) == "abc"


# The YjsMod ordering rule: a concurrent insert that anchors to the left of a run does
# not split it, because the run's right anchors are compared before the ids are.
def test_concurrent_insert_does_not_split_a_run():
    A = DiamondTypesClient(0)
    B = DiamondTypesClient(1)
    W = DiamondTypesClient(2)

    A.set_clients([A, B, W])
    B.set_clients([A, B, W])
    W.set_clients([A, B, W])

    insert(W, 0, "P")
    insert(B, 0, "x")

    W.receive_from_client(B.client_id)
    A.receive_from_client(W.client_id)
    A.receive_from_client(B.client_id)

    insert(B, 1, "y")
    insert(A, 1, "a")

    drain([A, B, W])

    assert text(A) == "xyaP"
    assert text(B) == "xyaP"
    assert text(W) == "xyaP"


# The shortest schedule on which plain Fugue and FugueMax disagree, found by searching
# every schedule up to length five. "c" anchors between "a" and "b", "d" between "a" and
# the end of the document, and this module settles it the way fuguemax does. It does not
# on its own pin the right origin rule, since ordering the two by site id alone reaches
# the same answer: test_concurrent_insert_does_not_split_a_run is what pins that.
def test_concurrent_inserts_settle_the_way_fuguemax_does():
    assert right_origin_schedule(fugue_setup) == ["acdb", "acdb"]
    assert right_origin_schedule(fuguemax_setup) == ["adcb", "adcb"]
    assert right_origin_schedule(diamondtypes_setup) == ["adcb", "adcb"]


# A character typed locally anchors before the run of tombstones at the cursor, because the
# right origin is the first item that still exists at the prepare version, tombstone or not.
# YjsMod anchors after that run instead, since a local position there counts past every
# tombstone it skipped, which is why calling eg-walker YjsMod only holds for insert only
# traces. This schedule fixes one site order; the anchoring is what forces yjsmod's answer
# under all of them, while this module's also has the tie break behind it, so the origin
# order checker's own scenario is what classifies the two.
def test_a_local_insert_anchors_before_a_tombstone():
    assert tombstone_anchor_schedule(diamondtypes_setup) == ["xy", "xy"]
    assert tombstone_anchor_schedule(yjsmod_setup) == ["xy", "xy"]


# The document is maintained incrementally as the event graph is replayed, so it has to
# stay equal to the items that no delete ever reached, in the order the items are in.
def test_document_matches_the_items_that_are_not_tombstones():
    random.seed(7)
    server, clients = diamondtypes_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 40) is True

    for client in clients:
        assert isinstance(client, DiamondTypesClient)
        replayed = [item.value for item in client.document.items if not item.end_state_deleted]
        assert client.read_state() == replayed


# Concurrent traces with deletes converge, which is what the walk has to guarantee: every
# replica replays the same event graph in a different order and ends up with one document.
def test_random_traces_converge():
    for seed in range(1, 26):
        random.seed(seed)
        server, clients = diamondtypes_setup(3)

        client_dict: dict[int, ClientDevice] = {}
        for client in clients:
            client_dict[client.client_id] = client

        assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_tombstone_keeps_its_place()
    test_concurrent_insert_does_not_split_a_run()
    test_concurrent_inserts_settle_the_way_fuguemax_does()
    test_a_local_insert_anchors_before_a_tombstone()
    test_document_matches_the_items_that_are_not_tombstones()
    test_random_traces_converge()
    print("OK")
