from dataclasses import dataclass
from random import randint

from unique_char.uniquechar import UniqueChar

MAX_VALUE = 2**3
MIN_VALUE = -(2**3)


@dataclass
class LogootSplitId:
    base: list[int]
    offset: int
    client_id: int

    def get_at_otherwise(self, index: int, otherwise: int) -> int:
        if index < len(self.base):
            return self.base[index]
        elif index == len(self.base):
            return self.offset
        else:
            return otherwise

    def less_than(self, other: LogootSplitId) -> bool:
        id1 = self.base + [self.offset]
        id2 = other.base + [other.offset]

        for n1, n2 in zip(id1, id2, strict=False):
            if n1 != n2:
                return n1 < n2
        return len(id1) < len(id2)


@dataclass
class LogootSplitIdInterval:
    base: list[int]
    begin: int
    end: int


@dataclass
class LogootSplitCharacter:
    id: LogootSplitId
    character: UniqueChar | None  # None for the begin and end sentinels.


@dataclass
class LogootSplitBlock:
    id: LogootSplitIdInterval
    characters: list[LogootSplitCharacter]
    client_id: int

    def length(self) -> int:
        return len(self.characters)

    def get_id_at(self, position: int) -> LogootSplitId:
        return self.characters[position].id

    def add_to_end(self, character: UniqueChar) -> LogootSplitId:
        self.id.end += 1
        id = LogootSplitId(self.id.base, self.id.end, self.client_id)
        c = LogootSplitCharacter(id, character)
        self.characters.append(c)
        return id

    def add_to_start(self, character: UniqueChar) -> LogootSplitId:
        self.id.begin -= 1
        id = LogootSplitId(list(self.id.base), self.id.begin, self.client_id)
        c = LogootSplitCharacter(id, character)
        self.characters.insert(0, c)
        return id

    def contains_id(self, id: LogootSplitId):
        return any(id == character.id for character in self.characters)


class LogootSplitDocument:
    blocks: list[LogootSplitBlock]
    client_id: int
    clock: int
    base_bounds: dict[
        tuple[int, ...], tuple[int, int]
    ]  # Keep track of maximum and minimum of bases to ensure that ids are not reused.

    def __init__(self, client_id: int):
        begin_id = LogootSplitIdInterval([], MIN_VALUE + 1, MIN_VALUE + 1)
        end_id = LogootSplitIdInterval([], MAX_VALUE - 1, MAX_VALUE - 1)

        begin_block = LogootSplitBlock(begin_id, [LogootSplitCharacter(LogootSplitId([], MIN_VALUE + 1, -1), None)], -1)
        end_block = LogootSplitBlock(end_id, [LogootSplitCharacter(LogootSplitId([], MAX_VALUE - 1, -1), None)], -1)

        self.blocks = [begin_block, end_block]
        self.client_id = client_id
        self.clock = 0
        self.base_bounds = {}

    def read_state(self) -> list[UniqueChar]:
        state: list[UniqueChar] = []
        for block in self.blocks:
            for character in block.characters:
                if character.character is not None:
                    state.append(character.character)
        return state

    def get_id_at_position(self, position: int) -> tuple[LogootSplitBlock, int, int] | None:
        for block_index, block in enumerate(self.blocks):
            if position < block.length():
                return block, block_index, position
            position -= block.length()
        return None

    def local_insert(self, position: int, character: UniqueChar) -> LogootSplitId:
        # Step 1
        c1 = self.get_id_at_position(position)
        c2 = self.get_id_at_position(position + 1)

        assert c1 is not None and c2 is not None  # Because of the sentinels.

        block1, block1_index, index1 = c1
        block2, _, index2 = c2

        id1 = block1.get_id_at(index1)
        id2 = block2.get_id_at(index2)

        # Step 2
        if index1 == block1.length() - 1 and self.can_add_to_end(block1, id2):
            return self.add_to_end(block1, character)

        # Step 3
        if index2 == 0 and self.can_add_to_start(block2, id1):
            return self.add_to_start(block2, character)

        # Step 4

        # Is c1 inside a block?
        if index1 != block1.length() - 1:
            block1, block2 = self.split(block1_index, index1 + 1)

        new_id = self.generate_base(id1, id2)

        self.blocks.insert(block1_index + 1, self.new_block(new_id, character))
        return new_id

    def remote_insert(self, id: LogootSplitId, character: UniqueChar):
        block2_index, index2 = self.find_first_greater(id)
        block1_index, index1 = self.previous_character(block2_index, index2)

        block1 = self.blocks[block1_index]
        block2 = self.blocks[block2_index]

        if block1.get_id_at(index1) == id:
            return

        if index1 == block1.length() - 1 and block1.id.base == id.base and block1.id.end + 1 == id.offset:
            block1.add_to_end(character)
            return

        if index2 == 0 and block2.id.base == id.base and id.offset + 1 == block2.id.begin:
            block2.add_to_start(character)
            return

        if index1 != block1.length() - 1:
            self.split(block1_index, index1 + 1)

        self.blocks.insert(block1_index + 1, self.new_block(id, character))

    def local_delete(self, position: int) -> LogootSplitId:
        block_id = self.get_id_at_position(position + 1)
        assert block_id is not None
        block, _, index = block_id
        id = block.get_id_at(index)
        self.remote_delete(id)
        return id

    def remote_delete(self, id: LogootSplitId):
        block_index = self.find_block(id)
        if block_index is None:
            return
        block_to_delete = self.blocks[block_index]
        # Not at start
        if block_to_delete.id.begin != id.offset:
            self.split(block_index, id.offset - block_to_delete.id.begin)
            block_index += 1

        if self.blocks[block_index].id.end != id.offset:
            self.split(block_index, 1)

        del self.blocks[block_index]

    def generate_base(self, id_low: LogootSplitId, id_high: LogootSplitId) -> LogootSplitId:
        new_base: list[int] = []
        index = 0

        while True:
            l = id_low.get_at_otherwise(index, MIN_VALUE)
            h = id_high.get_at_otherwise(index, MAX_VALUE)
            if h - l >= 2:
                break
            new_base.append(l)
            index += 1

        self.clock += 1
        new_base.extend([randint(l + 1, h - 1), self.client_id, self.clock])

        self.base_bounds[tuple(new_base)] = (0, 0)

        return LogootSplitId(new_base, 0, self.client_id)

    def new_block(self, id: LogootSplitId, character: UniqueChar) -> LogootSplitBlock:
        interval = LogootSplitIdInterval(list(id.base), id.offset, id.offset)
        return LogootSplitBlock(interval, [LogootSplitCharacter(id, character)], id.client_id)

    def can_add_to_end(self, block: LogootSplitBlock, id_next: LogootSplitId) -> bool:
        bounds = self.base_bounds.get(tuple(block.id.base))
        if block.client_id != self.client_id or bounds is None or block.id.end != bounds[1]:
            return False
        if block.id.end + 1 >= MAX_VALUE:
            return False
        return LogootSplitId(block.id.base, block.id.end + 1, self.client_id).less_than(id_next)

    def can_add_to_start(self, block: LogootSplitBlock, id_previous: LogootSplitId) -> bool:
        bounds = self.base_bounds.get(tuple(block.id.base))
        if block.client_id != self.client_id or bounds is None or block.id.begin != bounds[0]:
            return False
        if block.id.begin - 1 <= MIN_VALUE:
            return False
        return id_previous.less_than(LogootSplitId(block.id.base, block.id.begin - 1, self.client_id))

    def add_to_end(self, block: LogootSplitBlock, character: UniqueChar) -> LogootSplitId:
        id = block.add_to_end(character)
        key = tuple(block.id.base)
        minimum, _ = self.base_bounds[key]
        self.base_bounds[key] = (minimum, id.offset)
        return id

    def add_to_start(self, block: LogootSplitBlock, character: UniqueChar) -> LogootSplitId:
        id = block.add_to_start(character)
        key = tuple(block.id.base)
        _, maximum = self.base_bounds[key]
        self.base_bounds[key] = (id.offset, maximum)
        return id

    def find_first_greater(self, id: LogootSplitId) -> tuple[int, int]:
        for block_index, block in enumerate(self.blocks):
            for index, character in enumerate(block.characters):
                if id.less_than(character.id):
                    return block_index, index
        raise AssertionError("The end sentinel is greater than every generated identifer.")

    def previous_character(self, block_index: int, index: int) -> tuple[int, int]:
        if index > 0:
            return block_index, index - 1
        assert block_index > 0
        return block_index - 1, self.blocks[block_index - 1].length() - 1

    def find_block(self, id: LogootSplitId) -> int | None:
        for index, block in enumerate(self.blocks):
            if block.id.base == id.base and block.id.begin <= id.offset <= block.id.end:
                return index
        return None

    def split(self, index: int, split_index: int) -> tuple[LogootSplitBlock, LogootSplitBlock]:
        block = self.blocks[index]

        id1 = LogootSplitIdInterval(list(block.id.base), block.id.begin, block.id.begin + split_index - 1)
        id2 = LogootSplitIdInterval(list(block.id.base), block.id.begin + split_index, block.id.end)

        block1 = LogootSplitBlock(id1, block.characters[:split_index], block.client_id)
        block2 = LogootSplitBlock(id2, block.characters[split_index:], block.client_id)

        self.blocks[index : index + 1] = [block1, block2]
        return block1, block2
