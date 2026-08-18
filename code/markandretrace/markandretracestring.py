from markandretrace.markandretracemessage import (
    MarkAndRetraceDeletionOperation,
    MarkAndRetraceInsertionOperation,
)
from unique_char.uniquechar import UniqueChar


class MarkAndRetraceCharacter:
    client_id: int
    visible: bool
    character: UniqueChar
    insert_op: MarkAndRetraceInsertionOperation
    delete_ops: list[MarkAndRetraceDeletionOperation]

    def __init__(self, client_id: int, character: UniqueChar):
        self.visible = True
        self.delete_ops = []
        self.character = character
        self.client_id = client_id

    def attach_insert(self, insert_op: MarkAndRetraceInsertionOperation):
        self.insert_op = insert_op

    def attach_delete(self, delete_op: MarkAndRetraceDeletionOperation):
        self.delete_ops.append(delete_op)


class MarkAndRetraceString:
    string: list[MarkAndRetraceCharacter]

    def __init__(self):
        self.string = []

    def __state_vector_leq(self, SV1: dict[int, int], SV2: dict[int, int]) -> bool:
        return all(SV1[client_id] <= SV2[client_id] for client_id in SV1)

    def retrace(self, state_vector: dict[int, int]):
        for character in self.string:
            character.visible = False

            if self.__state_vector_leq(character.insert_op.state_vector, state_vector):
                character.visible = True

            for delete_op in character.delete_ops:
                if self.__state_vector_leq(delete_op.state_vector, state_vector):
                    character.visible = False

    def find_visible_character_at(self, position: int) -> MarkAndRetraceCharacter:
        index = 0
        n = 0
        while index < position or not self.string[n].visible:
            if self.string[n].visible:
                index += 1
            n += 1

        return self.string[n]

    def get_insertion_range(self, position: int) -> tuple[int, int]:
        # Get starting position
        start_index = 0
        visible = 0
        while visible < position:
            if self.string[start_index].visible:
                visible += 1
            start_index += 1

        end_index = start_index
        while end_index < len(self.string) and not self.string[end_index].visible:
            end_index += 1

        return start_index, end_index

    def __total_order_less_than(self, client_id1: int, SV1: dict[int, int], client_id2: int, SV2: dict[int, int]):
        SV1_sum = sum(SV1.values())
        SV2_sum = sum(SV2.values())
        return (SV1_sum < SV2_sum) or (SV1_sum == SV2_sum and client_id1 < client_id2)

    # Finds insertion position between start and end
    def range_scan(self, character: MarkAndRetraceCharacter, state_vector: dict[int, int], start: int, end: int) -> int:
        p: int = -1
        scan_index = start
        while scan_index < end:
            character_scanning = self.string[scan_index]
            if self.__state_vector_leq(self.string[scan_index].insert_op.state_vector, state_vector):
                if p == -1:
                    p = scan_index
                break
            elif not self.__state_vector_leq(state_vector, self.string[scan_index].insert_op.state_vector):
                if (
                    self.__total_order_less_than(
                        character.client_id,
                        character.insert_op.state_vector,
                        character_scanning.client_id,
                        character_scanning.insert_op.state_vector,
                    )
                    and p == -1
                ):
                    p = scan_index

                if self.__total_order_less_than(
                    character_scanning.client_id,
                    character_scanning.insert_op.state_vector,
                    character.client_id,
                    character.insert_op.state_vector,
                ) and (
                    p == -1
                    or self.__state_vector_leq(
                        character_scanning.insert_op.state_vector, self.string[p].insert_op.state_vector
                    )
                ):
                    p = -1
            scan_index += 1
        if p == -1:
            return end
        else:
            return p

    def insert_at(self, position: int, character: MarkAndRetraceCharacter):
        self.string.insert(position, character)

    def read_state(self) -> list[UniqueChar]:
        return [c.character for c in self.string if c.visible]
