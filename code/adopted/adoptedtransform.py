from abc import ABC, abstractmethod
from typing import assert_never

from adopted.adoptedmessage import (
    AdOPTedDeletionOperation,
    AdOPTedInsertionOperation,
    AdOPTedNoOperation,
    AdOPTedOperation,
)
from unique_char.uniquechar import UniqueChar


class AdOPTedTransform(ABC):
    @abstractmethod
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        pass

    @abstractmethod
    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        pass

    @abstractmethod
    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        pass


class EllisTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)

    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i > j:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif x == y:
                    return AdOPTedNoOperation()
                elif pr1 > pr2:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)


class ResselTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)

    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if (i < j) or (i == j and pr1 < pr2):
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i <= j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)


class IMORTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, position, set(), set(), vector_clock)

    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, position, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i > j:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif pr1 < pr2:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif pr1 > pr2:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif x.char < y.char:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif x.char > y.char:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i > j:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)


class SuleimanTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)

    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedInsertionOperation(j, y, pr2, b2, a2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1, {})
                elif i > j or len(b1.intersection(a2)) != 0:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, b1, a1, {})
                elif len(a1.intersection(b2)) != 0 or x.char < y.char:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1, {})
                elif x.char > y.char:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, b1, a1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y, b2, a2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedDeletionOperation(j, pr2):
                if i > j:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, b1.union({O2}), a1, {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1.union({O2}), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)


class TombstoneTransform(AdOPTedTransform):
    state: list[tuple[UniqueChar, bool]]

    def view_to_model(self, view_pos: int) -> int:
        n = 1
        j = 1
        while j <= len(self.state) and (n < view_pos or not self.state[j][1]):
            if self.state[j][1]:
                n += 1
            j += 1
        return j


class TM11Transform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(
        self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)

    def get_delete_with_priority(
        self, position: int, client_id: int, vector_clock: dict[int, int]
    ) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedInsertionOperation(j, y, pr2, b2, a2):
                if i < j or (i == j and pr1 > pr2):
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y, b2, a2):
                if i + 1 <= j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedDeletionOperation(j, pr2):
                if i <= j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i >= j + 1:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i + 1 <= j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i >= j + 1:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)
