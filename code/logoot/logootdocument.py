from dataclasses import dataclass
from random import randint

from unique_char.uniquechar import UniqueChar


@dataclass
class LogootIdentifier:
    pos: int
    client_id: int
    clock: int

    def less_than(self, other: LogootIdentifier):
        return (self.pos, self.client_id, self.clock) < (other.pos, other.client_id, other.clock)


LogootPosition = list[LogootIdentifier]


def position_less_than(pos1: LogootPosition, pos2: LogootPosition) -> bool:
    # Positions can differ in length, and a strict prefix sorts before its extensions.
    for id1, id2 in zip(pos1, pos2, strict=False):
        if id1 != id2:
            return id1.less_than(id2)
    return len(pos1) < len(pos2)


class LogootDocument:
    state: list[UniqueChar]
    ids: list[LogootPosition]
    site: int
    clock: int

    def __init__(self, site: int) -> None:
        self.state = []
        self.clock = 0
        self.begin = [LogootIdentifier(0, 0, 0)]
        self.end = [LogootIdentifier(self.BASE - 1, 0, 0)]
        self.ids = [self.begin, self.end]
        self.site = site

    BASE = 2**10

    def insert_char(self, character: UniqueChar, position: int):
        p = self.ids[position]
        q = self.ids[position + 1]
        new_id = self.generate_line_id(p, q, 1, self.site)[0]
        self.ids.insert(position + 1, new_id)
        self.state.insert(position, character)
        return new_id

    def integrate_insert(self, new_id: LogootPosition, character: UniqueChar):
        index = self.index_of(new_id)
        self.ids.insert(index, new_id)
        self.state.insert(index - 1, character)

    def index_of(self, target: LogootPosition) -> int:
        index = 1
        while index < len(self.ids) - 1 and position_less_than(self.ids[index], target):
            index += 1
        return index

    def delete_char(self, position: int) -> LogootPosition:
        target = self.ids[position + 1]
        del self.ids[position + 1]
        del self.state[position]
        return target

    def integrate_delete(self, target: LogootPosition):
        index = self.index_of(target)
        if index < len(self.ids) - 1 and self.ids[index] == target:
            del self.ids[index]
            del self.state[index - 1]

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def generate_line_id(self, p: LogootPosition, q: LogootPosition, N: int, site: int) -> list[LogootPosition]:
        assert position_less_than(p, q)

        ids: list[LogootPosition] = []
        index = 0
        interval = 0

        # The digits of q can compare lower than the digits of p while q still sorts after p
        # on sites alone, and then no digit interval ever opens. New positions in that case
        # extend the digits of p, which sorts them after p and before q at the identifier
        # where p and q already differ. The check must look past both lengths: digits of q
        # that extend the digits of p through a 0 still open an interval further down.
        depth = max(len(p), len(q))
        if self.prefix(q, depth) > self.prefix(p, depth):
            while interval < N:
                index += 1
                interval = self.prefix(q, index) - self.prefix(p, index) - 1
        else:
            while interval < N:
                index += 1
                interval = self.BASE ** max(index - len(p), 0) - 1

        step = interval // N
        r = self.prefix(p, index)
        for _ in range(N):
            ids.append(self.construct_position(r + randint(1, step), index, p, q, site))
            r += step
        return ids

    def construct_position(self, r: int, index: int, p: LogootPosition, q: LogootPosition, site: int) -> LogootPosition:
        digits: list[int] = []
        for _ in range(index):
            digits.append(r % self.BASE)
            r //= self.BASE
        digits.reverse()

        self.clock += 1

        position: LogootPosition = []
        last = index - 1
        for i, digit in enumerate(digits):
            if i == last:
                site_id, clock = site, self.clock
            elif i < len(p) and digit == p[i].pos:
                site_id, clock = p[i].client_id, p[i].clock
            elif i < len(q) and digit == q[i].pos:
                site_id, clock = q[i].client_id, q[i].clock
            else:
                site_id, clock = site, self.clock
            position.append(LogootIdentifier(digit, site_id, clock))
        return position

    def prefix(self, p: LogootPosition, index: int) -> int:
        result = 0
        for i in range(index):
            digit = p[i].pos if i < len(p) else 0
            result *= self.BASE
            result += digit
        return result
