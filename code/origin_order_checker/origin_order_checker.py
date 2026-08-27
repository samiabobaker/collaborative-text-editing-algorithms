import random
from dataclasses import dataclass

from algorithm_setup.algorithm_setup import DeviceSetup
from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientReceiveFromClientOperation,
)
from device.serverdevice import ServerDevice
from random_operation_generator.random_operation_generator import generate_random_client_client_operation
from unique_char.uniquechar import UniqueChar


@dataclass
class InsertRecord:
    """One insertion in origin form: what was typed, between which elements, by whom.

    left_origin and right_origin are the neighbours the insertion was anchored
    between, tombstones included, with None standing for the start and the end of
    the document. seen holds the creation indices of every insertion the inserting
    client had integrated, which is what the tree schemes need to reproduce the
    generator's parent choice.
    """

    char: UniqueChar
    left_origin: UniqueChar | None
    right_origin: UniqueChar | None
    site: int
    site_seq: int
    creation: int
    lamport: int
    seen: frozenset[int]


def sibling_key(record: InsertRecord, key: str) -> tuple[int, int]:
    if key == "creation":
        return (record.creation, 0)
    if key == "site":
        return (record.site, record.site_seq)
    if key == "lamport":
        return (record.lamport, record.site)
    raise ValueError(f"unknown sibling key {key}")


def build_trace(
    clients: dict[int, ClientDevice],
    cell: tuple[str, str, str],
    num_of_operations: int = 30,
    with_deletes: bool = True,
) -> tuple[list[InsertRecord], set[int], list[tuple[str, int, int]], list[UniqueChar] | None]:
    """Run a random trace, recording every insertion in origin form.

    A local insertion names a visible position, and turning that back into origins takes
    the tombstone inclusive order, which no client exposes. The declared anchoring is what
    supplies it: it says whether an insertion stops in front of a run of tombstones at the
    cursor or steps past it, so ordering the records the inserter had seen gives the
    neighbours the visible state cannot. The returned set holds the deleted characters,
    since the scheme predicts the order with tombstones still in it.
    """
    scheme, key, anchoring = cell
    records: list[InsertRecord] = []
    stream: list[tuple[str, int, int]] = []
    deleted: set[int] = set()
    deleted_seen: dict[int, set[int]] = {client_id: set() for client_id in clients}
    creation_by_char_id: dict[int, int] = {}
    seen: dict[int, set[int]] = {client_id: set() for client_id in clients}
    site_seq: dict[int, int] = dict.fromkeys(clients, 0)
    max_lamport: dict[int, int] = dict.fromkeys(clients, 0)

    client_list = list(clients.values())

    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(client_list, with_deletes=with_deletes)
        client = clients[operation.client_id]

        if isinstance(operation, ClientInsertOperation):
            stream.append(("insert", client.client_id, operation.character.id))
            visible = list(client.read_state())
            neighbour = visible[operation.position - 1] if operation.position > 0 else None
            integrated = [record for record in records if record.creation in seen[client.client_id]]
            order = SCHEMES[scheme](integrated, key)
            after = order.index(neighbour) + 1 if neighbour is not None else 0
            if anchoring == AFTER:
                while after < len(order) and order[after].id in deleted_seen[client.client_id]:
                    after += 1
            lamport = max_lamport[client.client_id] + 1
            record = InsertRecord(
                operation.character,
                order[after - 1] if after > 0 else None,
                order[after] if after < len(order) else None,
                client.client_id,
                site_seq[client.client_id],
                len(records),
                lamport,
                frozenset(seen[client.client_id]),
            )
            client.perform_operation(operation)
            records.append(record)
            creation_by_char_id[record.char.id] = record.creation
            seen[client.client_id].add(record.creation)
            site_seq[client.client_id] += 1
            max_lamport[client.client_id] = lamport
        elif isinstance(operation, ClientDeleteOperation):
            stream.append(("delete", client.client_id, operation.character.id))
            deleted.add(operation.character.id)
            deleted_seen[client.client_id].add(operation.character.id)
            client.perform_operation(operation)
        elif isinstance(operation, ClientReceiveFromClientOperation):
            for caused in client.perform_operation(operation):
                if isinstance(caused, ClientInsertOperation):
                    creation = creation_by_char_id[caused.character.id]
                    seen[client.client_id].add(creation)
                    max_lamport[client.client_id] = max(max_lamport[client.client_id], records[creation].lamport)
                else:
                    # A delete this client has now integrated, which is what an anchoring
                    # past a run of tombstones needs in order to know the run is there.
                    deleted_seen[client.client_id].add(caused.character.id)
        else:
            raise ValueError("the origin order checker only generates inserts, deletes and receives")

    # Deliver the messages still in flight, so the models compare against settled states.
    for client_id in clients:
        client = clients[client_id]
        client_can_receive_from = client.can_receive_from()
        while len(client_can_receive_from) != 0:
            receive_from = random.choice(client_can_receive_from)
            client.perform_operation(ClientReceiveFromClientOperation(client.client_id, receive_from))
            client_can_receive_from = client.can_receive_from()

    states = [list(client.read_state()) for client in clients.values()]
    for state in states[1:]:
        if state != states[0]:
            return records, deleted, stream, None
    return records, deleted, stream, states[0]


class _TreeNode:
    record: InsertRecord | None  # None for the root
    left_children: list[_TreeNode]
    right_children: list[_TreeNode]

    def __init__(self, record: InsertRecord | None):
        self.record = record
        self.left_children = []
        self.right_children = []

    def traverse(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        for node in self.left_children:
            result += node.traverse()
        if self.record is not None:
            result.append(self.record.char)
        for node in self.right_children:
            result += node.traverse()
        return result


def _fugue_placements(records: list[InsertRecord]) -> dict[int, tuple[int | None, str]]:
    # Replays the generator choice of the paper's Algorithm 1: a right child of the
    # left origin if the inserter had seen no right child there yet, otherwise a
    # left child of the next element, which is exactly the recorded right origin.
    # Keyed by creation rather than positional, so that ordering the records one
    # client has seen, which is what recovering origins under deletion needs, works
    # on that subset alone.
    creation_by_char_id = {record.char.id: record.creation for record in records}
    placements: dict[int, tuple[int | None, str]] = {}
    right_children_of: dict[int | None, list[int]] = {}
    for record in records:
        left = creation_by_char_id[record.left_origin.id] if record.left_origin is not None else None
        taken = any(child in record.seen for child in right_children_of.get(left, []))
        if not taken:
            placements[record.creation] = (left, "right")
            right_children_of.setdefault(left, []).append(record.creation)
        else:
            assert record.right_origin is not None
            placements[record.creation] = (creation_by_char_id[record.right_origin.id], "left")
    return placements


def fugue_order(records: list[InsertRecord], key: str) -> list[UniqueChar]:
    placements = _fugue_placements(records)
    root = _TreeNode(None)
    nodes: dict[int, _TreeNode] = {}
    for record in records:
        node = _TreeNode(record)
        nodes[record.creation] = node
        parent_creation, side = placements[record.creation]
        parent = root if parent_creation is None else nodes[parent_creation]
        siblings = parent.left_children if side == "left" else parent.right_children
        index = 0
        while index < len(siblings):
            sibling_record = siblings[index].record
            assert sibling_record is not None
            if sibling_key(sibling_record, key) >= sibling_key(record, key):
                break
            index += 1
        siblings.insert(index, node)
    return root.traverse()


def fuguemax_order(records: list[InsertRecord], key: str) -> list[UniqueChar]:
    placements = _fugue_placements(records)
    root = _TreeNode(None)
    nodes: dict[int, _TreeNode] = {}
    for record in records:
        node = _TreeNode(record)
        nodes[record.creation] = node
        parent_creation, side = placements[record.creation]
        parent = root if parent_creation is None else nodes[parent_creation]
        if side == "left":
            index = 0
            while index < len(parent.left_children):
                sibling_record = parent.left_children[index].record
                assert sibling_record is not None
                if sibling_key(sibling_record, key) >= sibling_key(record, key):
                    break
                index += 1
            parent.left_children.insert(index, node)
        else:
            # Right siblings go in reverse order of their right origins, ties by key.
            current = root.traverse()
            new_rank = float("inf") if record.right_origin is None else current.index(record.right_origin)
            index = 0
            while index < len(parent.right_children):
                sibling_record = parent.right_children[index].record
                assert sibling_record is not None
                sibling_rank = (
                    float("inf") if sibling_record.right_origin is None else current.index(sibling_record.right_origin)
                )
                before = sibling_rank > new_rank or (
                    sibling_rank == new_rank and sibling_key(sibling_record, key) < sibling_key(record, key)
                )
                if not before:
                    break
                index += 1
            parent.right_children.insert(index, node)
    return root.traverse()


def rga_order(records: list[InsertRecord], key: str) -> list[UniqueChar]:
    # Siblings are held in descending key order, so the newest insertion at an
    # anchor comes first. RGA uses the Lamport timestamp with the site as tie
    # break, which is what the lamport key gives.
    creation_by_char_id = {record.char.id: record.creation for record in records}
    root = _TreeNode(None)
    nodes: dict[int, _TreeNode] = {}
    for record in records:
        node = _TreeNode(record)
        nodes[record.creation] = node
        parent_creation = creation_by_char_id[record.left_origin.id] if record.left_origin is not None else None
        parent = root if parent_creation is None else nodes[parent_creation]
        index = 0
        while index < len(parent.right_children):
            sibling_record = parent.right_children[index].record
            assert sibling_record is not None
            if sibling_key(record, key) > sibling_key(sibling_record, key):
                break
            index += 1
        parent.right_children.insert(index, node)
    return _rga_traverse(root)


def _rga_traverse(node: _TreeNode) -> list[UniqueChar]:
    result: list[UniqueChar] = []
    if node.record is not None:
        result.append(node.record.char)
    for child in node.right_children:
        result += _rga_traverse(child)
    return result


def yata_order(records: list[InsertRecord], key: str) -> list[UniqueChar]:
    sequence: list[InsertRecord] = []

    def index_of(char: UniqueChar | None, default: int) -> int:
        if char is None:
            return default
        for index, record in enumerate(sequence):
            if record.char is char:
                return index
        raise ValueError("origin not integrated yet")

    def key_greater(record: InsertRecord, other: InsertRecord) -> bool:
        # Yjs compares the creator alone here, so two insertions by the same
        # creator fall through to the right origin comparison.
        if key == "creation":
            return record.creation > other.creation
        return record.site > other.site

    for record in records:
        left = index_of(record.left_origin, -1)
        right = index_of(record.right_origin, len(sequence))

        dest_index = left + 1
        scanning = False
        index = dest_index
        while True:
            if not scanning:
                dest_index = index
            if index == len(sequence) or index == right:
                break
            other = sequence[index]
            other_left = index_of(other.left_origin, -1)
            other_right = index_of(other.right_origin, len(sequence))
            if other_left < left:
                break
            elif other_left == left:
                if key_greater(record, other):
                    scanning = False
                elif other_right == right:
                    break
                else:
                    scanning = True
            index += 1
        sequence.insert(dest_index, record)

    return [record.char for record in sequence]


SCHEMES = {
    "fugue": fugue_order,
    "fuguemax": fuguemax_order,
    "rga": rga_order,
    "yata": yata_order,
}

# Which side of a deleted character a locally typed one is anchored on. The client that
# deletes cannot see the character its own insertion is placed against, so the algorithm's
# definition has to supply the answer, and the definitions in use disagree: the paper's own
# implementation of Fugue takes the left origin from the visible characters and the right
# origin from the raw ones, tombstones included, which anchors the new character in front,
# while Yjs takes both from the raw ones, which anchors it after.
AFTER = "after"
BEFORE = "before"

# The algorithm has no fixed answer here: the order moves with the tie break inputs, so the
# two characters are landing in the same place rather than on either side of the tombstone.
UNSETTLED = "unsettled"

# The scheme, sibling key and anchoring each algorithm declares, by client class name.
# All three are read off the same traces: the anchoring is what turns a visible position
# back into origins once the state holds tombstones, so it is an input to the check
# rather than a separate claim about it.
CELLS: dict[str, tuple[str, str, str]] = {
    "FugueClient": ("fugue", "creation", BEFORE),
    "FugueMaxClient": ("fuguemax", "creation", BEFORE),
    "LoroClient": ("fugue", "site", BEFORE),
    "RGAClient": ("rga", "lamport", BEFORE),
    "Sync9Client": ("fugue", "site", BEFORE),
    "YjsClient": ("yata", "site", AFTER),
    "YjsModClient": ("fuguemax", "site", AFTER),
}


def deliver_everything(clients: dict[int, ClientDevice]) -> None:
    # The scenario has to settle the same way every time it is run, so unlike the random
    # trace builder this delivers in a fixed order rather than picking a sender at random.
    redo_check = True
    while redo_check:
        redo_check = False
        for client_id in sorted(clients):
            client = clients[client_id]
            for receive_from in sorted(client.can_receive_from()):
                redo_check = True
                client.perform_operation(ClientReceiveFromClientOperation(client_id, receive_from))


def run_anchoring_scenario(
    device_setup: DeviceSetup, trailing: bool, leading: bool, deleter: int, x_first: bool
) -> str:
    """Race a character typed against a deleted neighbour with one typed against the live one.

    One client types the document and the other receives it. That client then deletes the
    character a and types x where it used to be, without having sent the delete, while the
    other client types y next to the character it can still see.

    Without a trailing character the document ends at a and y goes in front of it, so the two
    are separated only if x is anchored past the deleted character. With one the document
    continues "ab" and y goes between a and b, so they are separated only if x is anchored in
    front. Whichever scenario separates them fixes their order; in the other they land in the
    same place and a tie break decides, which is why both are run.

    leading puts a live character in front of a, which keeps the deletion off the start of the
    document. Several trees special case an insertion at position 0 and so never consult their
    ordering rule for it, and without this they are only ever asked the easy question.

    deleter swaps which client deletes, and so which site id each character carries, and
    x_first swaps which is typed first, and so their creation order. An order that survives
    both was decided by the anchoring rather than by a tie break.
    """
    other = 1 - deleter
    random.seed(0)
    UniqueChar.now = 0

    _, client_list = device_setup(2)
    clients: dict[int, ClientDevice] = {}
    for client in client_list:
        clients[client.client_id] = client

    prefix = "c" if leading else ""
    for offset, letter in enumerate(prefix + ("ab" if trailing else "a")):
        clients[deleter].perform_operation(ClientInsertOperation(deleter, offset, UniqueChar.get_unique_char(letter)))
    deliver_everything(clients)

    deleted = len(prefix)
    clients[deleter].perform_operation(ClientDeleteOperation(deleter, deleted, clients[deleter].read_state()[deleted]))
    for client_id in [deleter, other] if x_first else [other, deleter]:
        if client_id == deleter:
            clients[deleter].perform_operation(ClientInsertOperation(deleter, deleted, UniqueChar.get_unique_char("x")))
        else:
            position = deleted + (1 if trailing else 0)
            clients[other].perform_operation(ClientInsertOperation(other, position, UniqueChar.get_unique_char("y")))
    deliver_everything(clients)

    states = ["".join(character.char for character in clients[client_id].read_state()) for client_id in sorted(clients)]
    if any(state != states[0] for state in states):
        return "diverged"
    return states[0]


def anchoring_outcomes(device_setup: DeviceSetup, trailing: bool) -> list[tuple[str, str]]:
    """Return the settled state of each run beside the state a separation would have given."""
    separated = "xyb" if trailing else "yx"
    return [
        (
            run_anchoring_scenario(device_setup, trailing, leading, deleter, x_first),
            ("c" if leading else "") + separated,
        )
        for leading in (False, True)
        for deleter in (0, 1)
        for x_first in (True, False)
    ]


def anchoring_of(device_setup: DeviceSetup) -> str:
    without_trailing = anchoring_outcomes(device_setup, False)
    with_trailing = anchoring_outcomes(device_setup, True)

    anchored_after = all(state == separated for state, separated in without_trailing)
    anchored_before = all(state == separated for state, separated in with_trailing)

    if anchored_after and not anchored_before:
        return AFTER
    if anchored_before and not anchored_after:
        return BEFORE
    return UNSETTLED


def anchoring_checker(device_setup: DeviceSetup, print_ops: bool = False) -> bool:
    # The scheme and the key are read off random traces, but those only ever contain
    # insertions, so this axis needs its own scenario: with tombstones in the state an
    # insertion's origins can no longer be recovered from what was visible when it was made.
    _, client_list = device_setup(2)
    cell = CELLS.get(type(client_list[0]).__name__)
    if cell is None:
        raise ValueError(f"no origin order scheme is declared for {type(client_list[0]).__name__}")

    declared = cell[2]
    observed = anchoring_of(device_setup)
    if observed == declared:
        return True

    print(f"This algorithm anchors {observed}, but {declared} is declared for it.")
    if print_ops:
        for trailing, label in ((False, "without a trailing character:"), (True, "with one:")):
            outcomes = anchoring_outcomes(device_setup, trailing)
            print(label, *(f"{state} (separated: {separated})" for state, separated in outcomes))
    return False


def origin_order_checker(
    clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_ops: int = 30, print_ops: bool = False
) -> bool:
    if server is not None:
        raise ValueError("the origin order check only applies to peer to peer algorithms")
    first = next(iter(clients.values()))
    cell = CELLS.get(type(first).__name__)
    if cell is None:
        raise ValueError(f"no origin order scheme is declared for {type(first).__name__}")
    scheme, key, _ = cell

    records, deleted, _stream, converged = build_trace(clients, cell, num_of_ops)
    if converged is None:
        if print_ops:
            print("Clients did not converge, so there is no settled order to compare.")
        return False

    # The scheme orders the tombstones along with everything else, and the clients only
    # show what is left, so the prediction is compared against the visible projection.
    predicted = [char for char in SCHEMES[scheme](records, key) if char.id not in deleted]
    if predicted == converged:
        return True
    if print_ops:
        print(f"State does not match the {scheme} scheme with the {key} key.")
        print("state:     ", *converged, sep="")
        print("predicted: ", *predicted, sep="")
    return False


def _values(state: list[UniqueChar]) -> list[tuple[str, int]]:
    return [(char.char, char.id) for char in state]


def _conforms(
    cell: tuple[str, str, str], records: list[InsertRecord], deleted: set[int], state: list[UniqueChar]
) -> bool:
    scheme, key, _ = cell
    predicted = [char for char in SCHEMES[scheme](records, key) if char.id not in deleted]
    return _values(predicted) == _values(state)


def _run(device_setup: DeviceSetup, seed: int, num_of_clients: int, num_of_ops: int):
    # Cross run comparisons need the id counter reset, so equal seeds mint equal ids.
    UniqueChar.now = 0
    random.seed(seed)
    server, clients = device_setup(num_of_clients)
    if server is not None:
        raise ValueError("the origin order check only applies to peer to peer algorithms")
    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client
    cell = CELLS.get(type(clients[0]).__name__)
    if cell is None:
        raise ValueError(f"no origin order scheme is declared for {type(clients[0]).__name__}")
    records, deleted, stream, converged = build_trace(client_dict, cell, num_of_ops)
    return cell, records, deleted, stream, converged


def classify_pair(
    setup_a: DeviceSetup, setup_b: DeviceSetup, seed: int, num_of_clients: int = 3, num_of_ops: int = 30
) -> str:
    """Name the axis that separates two algorithms' orders on this seed.

    Both algorithms run the same seed and their operation streams must agree, or
    the comparison is meaningless and "schedule-diverged" is returned. When the
    settled states agree the answer is "identical". Otherwise each state is
    checked against its own declared cell: if either fails to conform, the
    divergence is "unexplained" and worth investigating. When both conform, the
    answer is the coordinates their cells differ in, joined by a plus, and
    "delivery" when the cells are identical, which leaves the delivery discipline
    as the only input that could have differed. A records level swap of one axis
    cannot stand in for this, because origins are read off the local state mid
    trace, so changing the order changes what later insertions record.
    """
    cell_a, records_a, deleted_a, stream_a, state_a = _run(setup_a, seed, num_of_clients, num_of_ops)
    cell_b, records_b, deleted_b, stream_b, state_b = _run(setup_b, seed, num_of_clients, num_of_ops)
    if state_a is None or state_b is None:
        return "unexplained"

    if stream_a != stream_b:
        return "schedule-diverged"

    if _values(state_a) == _values(state_b):
        return "identical"

    if not _conforms(cell_a, records_a, deleted_a, state_a) or not _conforms(cell_b, records_b, deleted_b, state_b):
        return "unexplained"

    axes = [name for name, a, b in zip(("scheme", "key", "anchoring"), cell_a, cell_b, strict=True) if a != b]
    if len(axes) == 0:
        # Same abstract machine on the same operations, so the only input left to
        # differ is the causal context: the delivery discipline changed which
        # insertions each client had seen, and with them origins and timestamps.
        return "delivery"
    return "+".join(axes)
