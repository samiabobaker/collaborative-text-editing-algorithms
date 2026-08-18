from __future__ import annotations

from got.operations.delete import GOTDeleteOperation
from got.operations.operation import GOTOperation


class GOTSplitDeleteOperation(GOTOperation):
    """
    An implementation of a SplitDelete operation for the GOT algorithm. Simply a wrapper around two
    DeleteOperations or SplitDeleteOperations. Used to simplify the interface---each SplitDeleteOperation is an
    instance of `GOTOperation`, and can therefore be passed around to functions that expect a `GOTOperation`.
    """

    client_id: int
    state_vector: dict[int, int]

    first: GOTDeleteOperation | GOTSplitDeleteOperation
    second: GOTDeleteOperation | GOTSplitDeleteOperation

    def __init__(
        self,
        client_id: int,
        state_vector: dict[int, int],
        first: GOTDeleteOperation | GOTSplitDeleteOperation,
        second: GOTDeleteOperation | GOTSplitDeleteOperation,
    ):
        self.client_id = client_id
        self.state_vector = state_vector

        self.first = first
        self.second = second

    def copy(self) -> GOTSplitDeleteOperation:
        """
        Returns a deep copy of the operation.
        """
        return GOTSplitDeleteOperation(
            client_id=self.client_id,
            state_vector=self.state_vector.copy(),
            first=self.first.copy(),
            second=self.second.copy(),
        )

    def remove_all_metadata(self) -> GOTSplitDeleteOperation:
        """
        Remove all internal metadata from the operation, such as lost information and relative addressing.
        """
        return GOTSplitDeleteOperation(
            client_id=self.client_id,
            state_vector=self.state_vector.copy(),
            first=self.first.remove_all_metadata(),
            second=self.second.remove_all_metadata(),
        )

    def copy_without_relative_addressing(self) -> GOTSplitDeleteOperation:
        """
        Copy the operation, without any relative addressing information.
        """
        return GOTSplitDeleteOperation(
            client_id=self.client_id,
            state_vector=self.state_vector.copy(),
            first=self.first.copy_without_relative_addressing(),
            second=self.second.copy_without_relative_addressing(),
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GOTSplitDeleteOperation)
            and self.client_id == other.client_id
            and self.state_vector == other.state_vector
            and self.first == other.first
            and self.second == other.second
        )

    def __repr__(self) -> str:
        return f"SplitDel(first={self.first}, second={self.second}, c={self.client_id}, sv={self.state_vector})"

    def __str__(self):
        return self.__repr__()

    def __hash__(self):
        return hash(tuple(self.state_vector))

    def flatten(self) -> list[GOTDeleteOperation]:
        """
        A SplitDeleteOperation may contain either a DeleteOperation or another SplitDeleteOperation
        as its first and second operations. We need to flatten the split operations to a list of DeleteOperations
        to be able to perform them.
        """
        flattened: list[GOTDeleteOperation] = []

        if isinstance(self.first, GOTSplitDeleteOperation):
            flattened.extend(self.first.flatten())
        else:
            flattened.append(self.first)

        if isinstance(self.second, GOTSplitDeleteOperation):
            flattened.extend(self.second.flatten())
        else:
            flattened.append(self.second)

        return flattened
