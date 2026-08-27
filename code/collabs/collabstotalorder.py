from collections.abc import Callable

from collabs.collabsmessage import CollabsCreateOperation

RADIX = 36
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36(n: int) -> str:
    """Render a non-negative integer in base 36."""
    if n == 0:
        return "0"
    out = ""
    while n > 0:
        out = _DIGITS[n % RADIX] + out
        n //= RADIX
    return out


def _value_and_side_encode(value: int, is_right: bool) -> int:
    """Pack a value and the side it sits on into one integer.

    A right child keeps the value, a left child takes its bitwise complement, so
    left children sort below the value and right children above it.
    """
    return value if is_right else ~value


def _value_and_side_decode(value_and_side: int) -> tuple[int, bool]:
    """Unpack a value and its side."""
    is_right = value_and_side >= 0
    value = value_and_side if is_right else ~value_and_side
    return value, is_right


class CollabsWaypoint:
    """A node in the tree of positions, identified by its sender and a counter."""

    def __init__(
        self,
        sender_id: str,
        counter: int,
        parent_waypoint: CollabsWaypoint | None,
        parent_value_index: int,
        is_right: bool,
    ):
        self.sender_id = sender_id
        self.counter = counter
        self.parent_waypoint = parent_waypoint
        self.parent_value_index = parent_value_index
        self.is_right = is_right
        # Sort order: left children by value_index, then right children by
        # reverse value_index, ties broken by sender_id.
        self.children: list[CollabsWaypoint] = []

    def __repr__(self) -> str:
        return f"CollabsWaypoint({self.sender_id!r},{self.counter},pv={self.parent_value_index},{'R' if self.is_right else 'L'})"


class CollabsTotalOrder:
    """The tree of positions.

    Positions are a waypoint and an index within it. Waypoints carry a parent, an
    index within that parent, and the side they were created on. Same side siblings
    are ordered by the parent's own waypoint first, then by ascending sender.
    """

    def __init__(self, replica_id: str, send_callback: Callable[[CollabsCreateOperation], None]):
        self.replica_id = replica_id
        # Map key is waypoint.sender_id, index in the array is waypoint.counter.
        self.waypoints_by_id: dict[str, list[CollabsWaypoint]] = {}
        self.root_waypoint = CollabsWaypoint("", 0, None, 0, True)
        self.waypoints_by_id[""] = [self.root_waypoint]
        # Tracks waypoints created by this replica: waypoint -> next
        # value_index to create. Only these waypoints can be extended.
        self.our_waypoints: dict[CollabsWaypoint, int] = {}
        # sendPrimitive hook (installed by the owning CollabsClient):
        # applies the message locally (echo) and adds it to the current
        # transaction.
        self.send_callback = send_callback

    # ---- creating positions ----------------------------------------------

    def create_positions(
        self,
        prev_position: str | None,
        next_position: str | None,
        count: int,
    ) -> list[str]:
        """Creates `count` new positions between prev_position and next_position."""
        if prev_position is not None and prev_position == next_position:
            raise ValueError("prev_position == next_position")
        if count <= 0:
            raise ValueError(f"count is <= 0: {count}")

        if prev_position is None:
            prev_waypoint, prev_value_index = self.root_waypoint, 0
        else:
            prev_waypoint, prev_value_index = self.decode(prev_position)

        # If next_position is a (right) descendant of prev_position,
        # create a new left descendant of next_position.
        if next_position is not None:
            next_waypoint, next_value_index = self.decode(next_position)
            if self.is_descendant(next_waypoint, next_value_index, prev_waypoint, prev_value_index):
                # Not always a left *child* of next_position: there can be left
                # child tombstones already.
                parent_waypoint, parent_value_index = self.leftmost_descendant(next_waypoint, next_value_index)
                return self.create_children(parent_waypoint, parent_value_index, False, count)

        # Otherwise anywhere in prev_position's right subtree will do.

        # First try to extend prev_waypoint.
        extend_value_index = self.our_waypoints.get(prev_waypoint)
        if extend_value_index is not None:
            # A waypoint of this replica's own, so it can be extended.
            self.our_waypoints[prev_waypoint] = extend_value_index + count
            return self.encode_all(prev_waypoint, extend_value_index, count)

        # Next, try to create a new right child of prev_position.
        existing_right = self.first_right_child(prev_waypoint, prev_value_index)
        if existing_right is None:
            # This is better than creating a left child of
            # [prev_waypoint, prev_value_index + 1] because it will be ordered
            # after concurrently-created extensions of prev_waypoint
            # (same-author gets non-interleaving priority).
            return self.create_children(prev_waypoint, prev_value_index, True, count)
        else:
            # Treat (child, 0) like next_position: create a new leftmost
            # descendant of child.
            parent_waypoint = self.leftmost_descendant0(existing_right)
            return self.create_children(parent_waypoint, 0, False, count)

    def is_descendant(
        self,
        a_waypoint: CollabsWaypoint,
        a_value_index: int,
        b_waypoint: CollabsWaypoint,
        b_value_index: int,
    ) -> bool:
        """Whether [a_waypoint, a_value_index] is a descendant of [b_waypoint, b_value_index]."""
        if a_waypoint is b_waypoint:
            return a_value_index >= b_value_index
        current = a_waypoint
        while current.parent_waypoint is not b_waypoint:
            if current.parent_waypoint is None:
                return False
            current = current.parent_waypoint
        if current.parent_value_index > b_value_index:
            return True
        elif current.parent_value_index == b_value_index:
            return current.is_right
        else:
            return False

    def leftmost_descendant(self, waypoint: CollabsWaypoint, value_index: int) -> tuple[CollabsWaypoint, int]:
        """The (waypoint, value_index) for the leftmost descendant of (waypoint, value_index)."""
        for child in waypoint.children:
            if not child.is_right and child.parent_value_index == value_index:
                return self.leftmost_descendant0(child), 0
            elif child.is_right or child.parent_value_index > value_index:
                # Past where a left child of the input would be.
                break
        return waypoint, value_index

    def leftmost_descendant0(self, waypoint: CollabsWaypoint) -> CollabsWaypoint:
        """The waypoint for the leftmost descendant of (waypoint, 0)."""
        current = waypoint
        while len(current.children) > 0:
            first_child = current.children[0]
            if first_child.parent_value_index == 0 and not first_child.is_right:
                current = first_child
            else:
                break
        return current

    def first_right_child(self, waypoint: CollabsWaypoint, value_index: int) -> CollabsWaypoint | None:
        """The waypoint of the first right child of [waypoint, value_index]."""
        for child in waypoint.children:
            if child.parent_value_index == value_index and child.is_right:
                return child
        return None

    def create_children(
        self,
        parent_waypoint: CollabsWaypoint,
        parent_value_index: int,
        is_right: bool,
        count: int,
    ) -> list[str]:
        message = CollabsCreateOperation(
            parent_waypoint.sender_id,
            _value_and_side_encode(parent_waypoint.counter, is_right),
            parent_value_index,
        )
        # The callback echoes the creation locally, which is what registers the new
        # waypoint in waypoints_by_id, and adds it to the current transaction.
        self.send_callback(message)

        # The new waypoint is last in this replica's waypoints_by_id array.
        replica_waypoints = self.waypoints_by_id[self.replica_id]
        new_waypoint = replica_waypoints[-1]

        # Record created positions in our_waypoints.
        self.our_waypoints[new_waypoint] = count

        return self.encode_all(new_waypoint, 0, count)

    # ---- applying remote creations ---------------------------------------

    def apply_create(self, message: CollabsCreateOperation, sender_id: str) -> None:
        """Apply a waypoint creation from another replica."""
        parent_waypoint_counter, is_right = _value_and_side_decode(message.parent_waypoint_counter_and_side)
        parent_waypoint = self.get_waypoint(message.parent_waypoint_sender_id, parent_waypoint_counter)
        sender_waypoints = self.waypoints_by_id.get(sender_id)
        if sender_waypoints is None:
            sender_waypoints = []
            self.waypoints_by_id[sender_id] = sender_waypoints
        waypoint = CollabsWaypoint(
            sender_id,
            len(sender_waypoints),
            parent_waypoint,
            message.parent_value_index,
            is_right,
        )
        sender_waypoints.append(waypoint)
        self.add_to_children(waypoint)

    def add_to_children(self, new_waypoint: CollabsWaypoint) -> None:
        """Adds new_waypoint to parent_waypoint.children in the proper order."""
        parent = new_waypoint.parent_waypoint
        if parent is None:
            raise ValueError("A created waypoint has no parent")
        children = parent.children
        i = 0
        while i < len(children) and not self.is_sibling_less(new_waypoint, children[i]):
            i += 1
        children.insert(i, new_waypoint)

    def is_sibling_less(self, sibling1: CollabsWaypoint, sibling2: CollabsWaypoint) -> bool:
        """Whether sibling1 < sibling2 in the sibling order."""
        if sibling1.is_right == sibling2.is_right:
            if sibling1.parent_value_index == sibling2.parent_value_index:
                # sender_id order. Identical sender_ids are impossible.
                return sibling1.sender_id < sibling2.sender_id
            else:
                # is_right: reverse value_index order; is_left: value_index order.
                return sibling1.is_right == (sibling1.parent_value_index > sibling2.parent_value_index)
        else:
            return sibling2.is_right

    def get_waypoint(self, sender_id: str, counter: int) -> CollabsWaypoint:
        by_sender = self.waypoints_by_id.get(sender_id)
        if by_sender is None:
            raise ValueError(f"Invalid position: unknown sender_id {sender_id!r}")
        if counter < 0:
            raise ValueError("Invalid position: counter < 0")
        if counter >= len(by_sender):
            raise ValueError(f"Invalid position: unknown counter {counter} for sender {sender_id!r}")
        return by_sender[counter]

    # ---- encoding positions ----------------------------------------------

    def encode(self, waypoint: CollabsWaypoint, value_index: int) -> str:
        return f"{_base36(waypoint.counter)}.{_base36(value_index)},{waypoint.sender_id}"

    def encode_all(self, waypoint: CollabsWaypoint, value_index: int, count: int) -> list[str]:
        return [self.encode(waypoint, value_index + i) for i in range(count)]

    def decode(self, position: str) -> tuple[CollabsWaypoint, int]:
        dot = position.find(".")
        comma = position.find(",", dot)
        if dot == -1 or comma == -1:
            raise ValueError(f"Not a Position: {position!r}")
        try:
            counter = int(position[:dot], RADIX)
            value_index = int(position[dot + 1 : comma], RADIX)
        except ValueError:
            raise ValueError(f"Not a Position: {position!r}") from None
        sender_id = position[comma + 1 :]
        waypoint = self.get_waypoint(sender_id, counter)
        if value_index < 0:
            raise ValueError(f"Invalid value_index < 0: {value_index}")
        return waypoint, value_index
