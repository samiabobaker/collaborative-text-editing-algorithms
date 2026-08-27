import random
from dataclasses import dataclass
from random import randint

from unique_char.uniquechar import UniqueChar


@dataclass
class LSEQIdentifier:
    pos: int
    client_id: int
    clock: int

    def less_than(self, other: LSEQIdentifier):
        return (self.pos, self.client_id, self.clock) < (other.pos, other.client_id, other.clock)


LSEQPosition = list[LSEQIdentifier]


def position_less_than(pos1: LSEQPosition, pos2: LSEQPosition) -> bool:
    # Positions can differ in length, and a strict prefix sorts before its extensions.
    for id1, id2 in zip(pos1, pos2, strict=False):
        if id1 != id2:
            return id1.less_than(id2)
    return len(pos1) < len(pos2)


class LSEQDocument:
    state: list[UniqueChar]
    ids: list[LSEQPosition]
    site: int
    clock: int

    strategies: dict[int, bool]

    def __init__(self, site: int) -> None:
        self.state = []
        self.clock = 0
        self.begin = [LSEQIdentifier(0, 0, 0)]
        self.end = [LSEQIdentifier(self.base(1) - 1, 0, 0)]
        self.ids = [self.begin, self.end]
        self.site = site
        self.strategies = {}

    START_BITS = 2
    BOUNDARY = 10

    def insert_char(self, character: UniqueChar, position: int):
        p = self.ids[position]
        q = self.ids[position + 1]
        new_id = self.generate_line_id(p, q, self.site)
        self.ids.insert(position + 1, new_id)
        self.state.insert(position, character)
        return new_id

    def integrate_insert(self, new_id: LSEQPosition, character: UniqueChar):
        index = self.index_of(new_id)
        self.ids.insert(index, new_id)
        self.state.insert(index - 1, character)

    def index_of(self, target: LSEQPosition) -> int:
        index = 1
        while index < len(self.ids) - 1 and position_less_than(self.ids[index], target):
            index += 1
        return index

    def delete_char(self, position: int) -> LSEQPosition:
        target = self.ids[position + 1]
        del self.ids[position + 1]
        del self.state[position]
        return target

    def integrate_delete(self, target: LSEQPosition):
        index = self.index_of(target)
        if index < len(self.ids) - 1 and self.ids[index] == target:
            del self.ids[index]
            del self.state[index - 1]

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def generate_line_id(self, p: LSEQPosition, q: LSEQPosition, site: int) -> LSEQPosition:
        assert position_less_than(p, q)

        limit = max(len(p), len(q))
        extend_p = self.prefix(q, limit) <= self.prefix(p, limit)

        depth = 0
        interval = 0
        if extend_p:
            while interval < 1:
                depth += 1
                interval = self.extension_room(len(p), depth)
        else:
            while interval < 1:
                depth += 1
                interval = self.prefix(q, depth) - self.prefix(p, depth) - 1
        step = min(self.BOUNDARY, interval)

        if depth not in self.strategies:
            rand = random.choice([True, False])
            self.strategies[depth] = rand

        if extend_p or self.strategies[depth]:
            addValue = randint(1, step)
            id = self.prefix(p, depth) + addValue
        else:
            subVal = randint(1, step)
            id = self.prefix(q, depth) - subVal

        return self.construct_position(id, depth, p, q, site)

    def extension_room(self, length: int, depth: int) -> int:
        room = 1
        for level in range(length + 1, depth + 1):
            room *= self.base(level)
        return room - 1

    def construct_position(self, r: int, depth: int, p: LSEQPosition, q: LSEQPosition, site: int) -> LSEQPosition:
        digits: list[int] = []
        for level in range(depth, 0, -1):
            digits.append(r % self.base(level))
            r //= self.base(level)
        digits.reverse()

        self.clock += 1

        position: LSEQPosition = []
        last = depth - 1
        for i, digit in enumerate(digits):
            if i == last:
                site_id, clock = site, self.clock
            elif i < len(p) and digit == p[i].pos:
                site_id, clock = p[i].client_id, p[i].clock
            elif i < len(q) and digit == q[i].pos:
                site_id, clock = q[i].client_id, q[i].clock
            else:
                site_id, clock = site, self.clock
            position.append(LSEQIdentifier(digit, site_id, clock))
        return position

    def base(self, depth: int) -> int:
        return 2 ** (self.START_BITS + depth)

    def prefix(self, p: LSEQPosition, depth: int) -> int:
        result = 0
        for level in range(1, depth + 1):
            digit = p[level - 1].pos if level - 1 < len(p) else 0
            result = result * self.base(level) + digit
        return result
