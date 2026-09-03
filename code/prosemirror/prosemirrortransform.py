from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar

DEL_BEFORE = 1
DEL_AFTER = 2
DEL_ACROSS = 4
DEL_SIDE = 8


@dataclass
class ProseMirrorStepResult:
    doc: list[UniqueChar] | None
    failed: bool

    @staticmethod
    def from_replace(doc: list[UniqueChar], start: int, end: int, slice: list[UniqueChar]) -> ProseMirrorStepResult:
        if 0 <= start <= end <= len(doc):
            return ProseMirrorStepResult(doc[:start] + slice + doc[end:], False)
        return ProseMirrorStepResult(None, True)


@dataclass
class ProseMirrorStep:
    start: int
    end: int
    slice: list[UniqueChar]
    structure: bool = False

    MAP_BIAS = 1

    def map(self, mapping: ProseMirrorMapping) -> ProseMirrorStep | None:
        end = mapping.map_result(self.end, -1)
        start = end if self.start == self.end and self.MAP_BIAS < 0 else mapping.map_result(self.start, 1)
        if start.deleted_across() and end.deleted_across():
            return None
        return ProseMirrorStep(start.pos, max(start.pos, end.pos), self.slice, self.structure)

    def invert(self, doc: list[UniqueChar]) -> ProseMirrorStep:
        return ProseMirrorStep(self.start, self.start + len(self.slice), doc[self.start : self.end])

    def apply(self, doc: list[UniqueChar]) -> ProseMirrorStepResult:
        return ProseMirrorStepResult.from_replace(doc, self.start, self.end, self.slice)

    def get_map(self) -> ProseMirrorStepMap:
        return ProseMirrorStepMap([self.start, self.end - self.start, len(self.slice)])


@dataclass
class ProseMirrorStepMap:
    ranges: list[int]
    inverted: bool = False

    def map_result(self, pos: int, assoc: int = 1) -> ProseMirrorMapResult:
        return self._map(pos, assoc, False)

    def _map(self, pos: int, assoc: int, simple: bool) -> ProseMirrorMapResult:
        assert not simple

        diff = 0
        old_index = 2 if self.inverted else 1
        new_index = 1 if self.inverted else 2
        for i in range(0, len(self.ranges), 3):
            start = self.ranges[i] - (diff if self.inverted else 0)
            if start > pos:
                break
            old_size = self.ranges[i + old_index]
            new_size = self.ranges[i + new_index]
            end = start + old_size
            if pos <= end:
                side = assoc if not old_size else -1 if pos == start else 1 if pos == end else assoc
                result = start + diff + (0 if side < 0 else new_size)
                if simple:
                    return result
                recover = None if pos == (start if assoc < 0 else end) else self.make_recover(int(i / 3), pos - start)
                del_where = DEL_AFTER if pos == start else DEL_BEFORE if pos == end else DEL_ACROSS
                if pos != start if assoc < 0 else pos != end:
                    del_where |= DEL_SIDE
                return ProseMirrorMapResult(result, del_where, recover)
            diff += new_size - old_size
        return ProseMirrorMapResult(pos + diff, 0, None)

    def make_recover(self, index: int, offset: int) -> int:
        return index + offset * (2**16)

    def recover_index(self, value: int) -> int:
        return value & 0xFFFF

    def recover_offset(self, value: int) -> int:
        return int((value - (value & 0xFFFF)) / (2**16))

    def recover(self, value: int) -> int:
        diff = 0
        index = self.recover_index(value)
        if not self.inverted:
            for i in range(index):
                diff += self.ranges[i * 3 + 2] - self.ranges[i * 3 + 1]
        return self.ranges[index * 3] + diff + self.recover_offset(value)


@dataclass
class ProseMirrorMapResult:
    pos: int
    del_info: int
    recover: int | None

    def deleted_across(self) -> bool:
        return (self.del_info & DEL_ACROSS) > 0


class ProseMirrorMapping:
    maps: list[ProseMirrorStepMap] | None
    mirror: list[int] | None
    start: int
    end: int
    _maps: list[ProseMirrorStepMap]

    own_data = bool

    def __init__(self, maps: list[ProseMirrorStepMap] | None, mirror: list[int] | None):
        self.maps = maps
        self.mirror = mirror
        self.start = 0
        self.end = len(self.maps) if self.maps is not None else 0
        self._maps = self.maps if self.maps is not None else []
        self.own_data = not (self.maps is not None or self.mirror is not None)

    def slice(self, start: int = 0, end: int | None = None) -> ProseMirrorMapping:
        sliced = ProseMirrorMapping(self._maps, self.mirror)
        sliced.start = start
        sliced.end = len(self._maps) if end is None else end
        return sliced

    def get_mirror(self, n: int) -> int | None:
        if self.mirror is not None:
            for i in range(len(self.mirror)):
                if self.mirror[i] == n:
                    return self.mirror[i + (-1 if i % 2 else 1)]
        return None

    def set_mirror(self, n: int, m: int):
        if not self.mirror:
            self.mirror = []
        self.mirror.append(n)
        self.mirror.append(m)

    def append_map(self, map: ProseMirrorStepMap, mirrors: int | None):
        if not self.own_data:
            self._maps = list(self._maps)
            self.mirror = list(self.mirror) if self.mirror is not None else None
            self.own_data = True
        self._maps.append(map)
        self.end = len(self._maps)
        if mirrors is not None:
            self.set_mirror(len(self._maps) - 1, mirrors)

    def map_result(self, pos: int, assoc: int = 1) -> ProseMirrorMapResult:
        return self._map(pos, assoc, False)

    def _map(self, pos: int, assoc: int, simple: bool) -> ProseMirrorMapResult:
        del_info = 0

        i = self.start
        while i < self.end:
            map = self._maps[i]
            result = map.map_result(pos, assoc)
            if result.recover is not None:
                corr = self.get_mirror(i)
                if corr is not None and corr > i and corr < self.end:
                    i = corr + 1
                    pos = self._maps[corr].recover(result.recover)
                    continue
            del_info |= result.del_info
            pos = result.pos
            i += 1

        assert not simple

        return ProseMirrorMapResult(pos, del_info, None)


class ProseMirrorTransform:
    steps: list[ProseMirrorStep]
    docs: list[list[UniqueChar]]
    doc: list[UniqueChar]
    mapping: ProseMirrorMapping

    def __init__(self, doc: list[UniqueChar]):
        self.steps = []
        self.docs = []
        self.mapping = ProseMirrorMapping(None, None)
        self.doc = doc

    def step(self, step: ProseMirrorStep) -> ProseMirrorTransform:
        result = self.maybe_step(step)
        if result.failed:
            raise Exception("Transform error, result failed.")
        return self

    def maybe_step(self, step: ProseMirrorStep) -> ProseMirrorStepResult:
        result = step.apply(self.doc)
        if not result.failed:
            assert result.doc is not None
            self.add_step(step, result.doc)
        return result

    def add_step(self, step: ProseMirrorStep, doc: list[UniqueChar]):
        self.docs.append(self.doc)
        self.steps.append(step)
        self.mapping.append_map(step.get_map(), None)
        self.doc = doc


@dataclass
class ProseMirrorRebaseable:
    step: ProseMirrorStep
    inverted: ProseMirrorStep
    origin: ProseMirrorTransform
    causing_operation: ClientInsertOperation | ClientDeleteOperation
