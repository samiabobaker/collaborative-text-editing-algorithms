from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class CollabsCreateOperation:
    # The parent waypoint is identified by its sender and its counter. The counter
    # also carries the side it was created on, encoded so that a left child is the
    # bitwise complement of the counter and a right child is the counter itself.
    parent_waypoint_sender_id: str
    parent_waypoint_counter_and_side: int
    parent_value_index: int


@dataclass
class CollabsInsertionOperation:
    # The waypoint is identified by the sender of the message and this counter.
    waypoint_counter: int
    value_index: int
    value: UniqueChar


@dataclass
class CollabsDeletionOperation:
    position: str


CollabsOperation = CollabsCreateOperation | CollabsInsertionOperation | CollabsDeletionOperation


# One transaction, delivered atomically and applied in order. The vector clock
# entries start with the sender, followed by the causally maximal keys. That order
# matters: only the first maximal_vc_key_count entries after the sender are checked
# when deciding whether the message is ready.
@dataclass
class CollabsMessage:
    sender_id: str
    sender_counter: int
    vc_entries: dict[str, int]
    maximal_vc_key_count: int
    operations: list[CollabsOperation]
    causing_operation: ClientInsertOperation | ClientDeleteOperation
