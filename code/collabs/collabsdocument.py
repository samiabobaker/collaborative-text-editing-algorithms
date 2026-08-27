from collections.abc import Iterator

from collabs.collabstotalorder import CollabsTotalOrder, CollabsWaypoint
from unique_char.uniquechar import UniqueChar

# Alternating runs along a waypoint: a list of present values, or a count of
# deleted positions. A run of values is never followed by another run of values.
Run = list[UniqueChar] | int


class CollabsWaypointInfo:
    """What the local view knows about one waypoint."""

    def __init__(self, total: int = 0, seen: int = 0, items: list[Run] | None = None):
        self.total = total  # present values at this waypoint and descendants
        self.seen = seen  # 1 + the highest value_index ever set at this waypoint
        # Alternating runs: list (present values) | int (count of deleted
        # positions). Never ends with a count.
        self.items: list[Run] = items if items is not None else []


class CollabsValuesOrChild:
    """Either a run of values at a waypoint, or one of its children."""

    def __init__(
        self,
        is_values: bool,
        item: list[UniqueChar] | None = None,
        start: int = 0,
        end: int = 0,
        value_index: int = 0,
        child: CollabsWaypoint | None = None,
        total: int = 0,
    ):
        self.is_values = is_values
        self.item = item
        self.start = start
        self.end = end
        self.value_index = value_index
        self.child = child
        self.total = total


class CollabsLocalList:
    """The local view: which positions carry a value, in list order.

    Keeps a per waypoint running total so that an index can be turned into a
    position without walking the whole tree.
    """

    def __init__(self, source: CollabsTotalOrder):
        self.source = source
        self.values_by_waypoint: dict[CollabsWaypoint, CollabsWaypointInfo] = {}

    # ---- mutations ----

    def set_created(self, first_pos: str, values: list[UniqueChar]) -> None:
        """Set the values at freshly created positions, at or past everything seen."""
        if len(values) == 0:
            return
        waypoint, value_index = self.source.decode(first_pos)
        info = self.values_by_waypoint.get(waypoint)
        if info is None:
            values = list(values)
            new_items: list[Run] = [values] if value_index == 0 else [value_index, values]
            self.values_by_waypoint[waypoint] = CollabsWaypointInfo(
                total=0, seen=value_index + len(values), items=new_items
            )
        else:
            if value_index < info.seen:
                raise ValueError("set_created called on seen positions")
            existing = 0
            for item in info.items:
                existing += item if isinstance(item, int) else len(item)
            if existing < value_index:
                # Fill in deleted positions before values.
                info.items.append(value_index - existing)
                info.items.append(list(values))
            elif existing == value_index:
                if len(info.items) == 0:
                    info.items.append(list(values))
                else:
                    # Merge with previous (present) item.
                    last = info.items[-1]
                    assert not isinstance(last, int)
                    last.extend(values)
            else:
                raise ValueError("set_created called on seen positions")
            info.seen = max(info.seen, value_index + len(values))
        self.update_totals(waypoint, len(values))

    def delete(self, position: str) -> bool:
        """Deletes the position, if present. Returns whether it was present."""
        waypoint, value_index = self.source.decode(position)
        info = self.values_by_waypoint.get(waypoint)
        if info is None:
            return False
        items = info.items
        remaining = value_index
        for i, cur_item in enumerate(items):
            if isinstance(cur_item, int):
                if remaining < cur_item:
                    return False  # Already not present.
                remaining -= cur_item
            else:
                if remaining < len(cur_item):
                    # Replace current item[remaining] with
                    # [current item[:remaining], 1, current item[remaining+1:]].
                    start_index = i
                    delete_count = 1
                    new_items: list[Run] = [1]
                    if remaining != 0:
                        new_items.insert(0, list(cur_item[:remaining]))
                    elif i != 0:
                        # Combine 1 with left neighbour.
                        start_index -= 1
                        delete_count += 1
                        left = items[i - 1]
                        assert isinstance(left, int)
                        first = new_items[0]
                        assert isinstance(first, int)
                        new_items[0] = first + left
                    if remaining != len(cur_item) - 1:
                        new_items.append(list(cur_item[remaining + 1 :]))
                    elif i != len(items) - 1:
                        # Combine 1 with right neighbour.
                        delete_count += 1
                        right = items[i + 1]
                        assert isinstance(right, int)
                        last = new_items[-1]
                        assert isinstance(last, int)
                        new_items[-1] = last + right
                    items[start_index : start_index + delete_count] = new_items
                    # If the last item is a count (deleted), omit it.
                    if isinstance(items[-1], int):
                        items.pop()
                    self.update_totals(waypoint, -1)
                    return True
                remaining -= len(cur_item)
        # Position is in the implied last item, hence already deleted.
        return False

    def update_totals(self, waypoint: CollabsWaypoint, delta: int) -> None:
        """Changes total by delta for waypoint and all of its ancestors."""
        current: CollabsWaypoint | None = waypoint
        while current is not None:
            info = self.values_by_waypoint.get(current)
            if info is None:
                self.values_by_waypoint[current] = CollabsWaypointInfo(total=delta, seen=0, items=[])
            else:
                info.total += delta
            current = current.parent_waypoint

    # ---- queries ----

    def locate(self, waypoint: CollabsWaypoint, value_index: int) -> tuple[UniqueChar | None, bool, int]:
        """The value at a position, whether it is present, and how many precede it.

        The count is of present values at this waypoint alone, strictly before the
        given index.
        """
        info = self.values_by_waypoint.get(waypoint)
        if info is None:
            return None, False, 0
        remaining = value_index
        waypoint_values_before = 0
        for item in info.items:
            if isinstance(item, int):
                if remaining < item:
                    return None, False, waypoint_values_before
                remaining -= item
            else:
                if remaining < len(item):
                    return item[remaining], True, waypoint_values_before + remaining
                remaining -= len(item)
                waypoint_values_before += len(item)
        return None, False, waypoint_values_before

    def get_position(self, index: int) -> str:
        """The position currently at index."""
        if index < 0 or index >= self.length:
            raise IndexError(f"Index out of bounds: {index} (length: {self.length})")
        remaining = index
        waypoint = self.source.root_waypoint
        while True:
            descended = False
            for next_vc in self.values_and_children(waypoint):
                if next_vc.is_values:
                    length = next_vc.end - next_vc.start
                    if remaining < length:
                        return self.source.encode(waypoint, next_vc.value_index + remaining)
                    remaining -= length
                else:
                    if remaining < next_vc.total:
                        child = next_vc.child
                        assert child is not None
                        waypoint = child
                        descended = True
                        break
                    remaining -= next_vc.total
            if not descended:
                raise IndexError("Failed to find the index among the children")

    def values_and_children(self, waypoint: CollabsWaypoint) -> Iterator[CollabsValuesOrChild]:
        """Yields the non-empty value runs and children of a waypoint, in list order."""
        info = self.values_by_waypoint[waypoint]
        items = info.items
        children = waypoint.children
        child_index = 0
        start_value_index = 0
        for item in items:
            item_size = item if isinstance(item, int) else len(item)
            end_value_index = start_value_index + item_size
            value_index = start_value_index
            while child_index < len(children):
                child = children[child_index]
                if child.is_right or child.parent_value_index >= end_value_index:
                    # Child comes after item.
                    break
                if self.total(child) != 0:
                    if value_index < child.parent_value_index:
                        if not isinstance(item, int):
                            yield CollabsValuesOrChild(
                                True,
                                item=item,
                                start=value_index - start_value_index,
                                end=child.parent_value_index - start_value_index,
                                value_index=value_index,
                            )
                        value_index = child.parent_value_index
                    yield CollabsValuesOrChild(False, child=child, total=self.total(child))
                child_index += 1
            if not isinstance(item, int) and value_index < end_value_index:
                yield CollabsValuesOrChild(
                    True,
                    item=item,
                    start=value_index - start_value_index,
                    end=item_size,
                    value_index=value_index,
                )
            start_value_index = end_value_index
        # Remaining children (left children among a possible deleted final
        # item and right children).
        while child_index < len(children):
            child = children[child_index]
            if self.total(child) != 0:
                yield CollabsValuesOrChild(False, child=child, total=self.total(child))
            child_index += 1

    def entries(self) -> Iterator[tuple[int, UniqueChar, str]]:
        """Iterates [index, value, position] for every value, in list order."""
        if self.length == 0:
            return
        index = 0
        waypoint: CollabsWaypoint | None = self.source.root_waypoint
        stack = [self.values_and_children(waypoint)]
        while waypoint is not None:
            iter_ = stack[-1]
            try:
                next_vc = next(iter_)
            except StopIteration:
                stack.pop()
                waypoint = waypoint.parent_waypoint
                continue
            if next_vc.is_values:
                item = next_vc.item
                assert item is not None
                for i in range(next_vc.end - next_vc.start):
                    yield (
                        index,
                        item[next_vc.start + i],
                        self.source.encode(waypoint, next_vc.value_index + i),
                    )
                    index += 1
            else:
                child = next_vc.child
                assert child is not None
                waypoint = child
                stack.append(self.values_and_children(waypoint))

    def total(self, waypoint: CollabsWaypoint) -> int:
        """Total number of present values at waypoint and its descendants."""
        info = self.values_by_waypoint.get(waypoint)
        return info.total if info is not None else 0

    @property
    def length(self) -> int:
        return self.total(self.source.root_waypoint)

    def has_position(self, position: str) -> bool:
        return self.locate(*self.source.decode(position))[1]

    def values(self) -> Iterator[UniqueChar]:
        """Iterator over values in list order."""
        for _, value, _ in self.entries():
            yield value
