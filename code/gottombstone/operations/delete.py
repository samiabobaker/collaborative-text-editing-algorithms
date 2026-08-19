from __future__ import annotations

from gottombstone.operations.operation import GOTTombstoneOperation
from unique_char.uniquechar import UniqueChar

type StateVector = dict[int, int]


class GOTDeleteOperation(GOTTombstoneOperation):
    """
    An implementation of a Delete operation for the GOT algorithm.
    """

    _lost_information: tuple[GOTDeleteOperation, GOTDeleteOperation] | None
    relative_addressed_to: StateVector | None

    # Global counter for split operations
    split_operation_id_global_counter = 0

    def __init__(
        self,
        num_to_delete: int,
        idx: int,
        sequence: list[UniqueChar],
        client_id: int,
        state_vector: dict[int, int],
        seq_number: int = 0,
    ):
        self.client_id = client_id
        self.state_vector = state_vector

        self.num_to_delete = num_to_delete
        self.idx = idx
        self.sequence = sequence
        self.unique_id = seq_number

        self._lost_information = None
        self.relative_addressed_to = None

    def save_lost_information(self, original_op_a: GOTDeleteOperation, op_b: GOTDeleteOperation) -> None:
        """
        Saves the lost information pair (original_op_a, op_b) for later retrieval.
        """
        self._lost_information = (original_op_a, op_b)

    def check_lost_information(self, op_b: GOTDeleteOperation) -> bool:
        """
        Checks if the operation has lost information related to op_b.
        """
        return self._lost_information is not None and op_b == self._lost_information[1]

    def retrieve_lost_information(self, op_b: GOTDeleteOperation) -> GOTDeleteOperation:
        """
        Returns the lost information pair if `op_b` matches the saved lost information.
        """
        assert self._lost_information is not None and op_b == self._lost_information[1]
        return self._lost_information[0]

    def save_relative_addressing(self, op_b: GOTTombstoneOperation) -> None:
        """
        Saves the state vector of the operation to which this delete operation is relatively addressed.
        """
        assert self.relative_addressed_to is None
        self.relative_addressed_to = op_b.state_vector

    def is_relatively_addressed(self) -> bool:
        """
        Returns True if the operation is relatively addressed to another operation.
        """
        return self.relative_addressed_to is not None

    def check_relative_addressing(self, op_b: GOTTombstoneOperation) -> bool:
        """
        Checks if the provided operation matches the relative addressing state vector.
        """
        assert self.relative_addressed_to is not None
        return op_b.state_vector == self.relative_addressed_to

    def copy(self) -> GOTDeleteOperation:
        """
        Returns a copy of the operation *including all internal state*.
        """
        copied = GOTDeleteOperation(
            self.num_to_delete,
            self.idx,
            self.sequence[:],
            self.client_id,
            self.state_vector.copy(),
            seq_number=self.unique_id,
        )

        copied._lost_information = self._lost_information
        copied.relative_addressed_to = self.relative_addressed_to

        return copied

    def remove_all_metadata(self):
        """
        Returns a copy of the operation with all metadata removed.
        This method is intended to be used to sanitise the internal state of an incoming operation from another client.
        """
        return GOTDeleteOperation(
            self.num_to_delete, self.idx, self.sequence[:], self.client_id, self.state_vector.copy()
        )

    def copy_without_relative_addressing(self) -> GOTDeleteOperation:
        """
        Returns a copy of the operation including all internal state *except `relative_addressed_to`*.
        """
        copied = GOTDeleteOperation(
            self.num_to_delete, self.idx, self.sequence[:], self.client_id, self.state_vector.copy(), self.unique_id
        )
        copied._lost_information = self._lost_information
        return copied

    def assign_unique_id(self) -> None:
        """
        Assigns a unique identifier to the operation to prevent the bug discussed in Section 3.1.3 of the dissertation.
        """
        GOTDeleteOperation.split_operation_id_global_counter += 1
        self.unique_id = GOTDeleteOperation.split_operation_id_global_counter

    def __str__(self):
        return rf"Del({self.num_to_delete} ({self.sequence}), {self.idx}, c={self.client_id}, sv={self.state_vector}, RA={self.relative_addressed_to}, LI={self._lost_information}, seq={self.unique_id})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other: object):
        return (
            isinstance(other, GOTDeleteOperation)
            and self.num_to_delete == other.num_to_delete
            and self.idx == other.idx
            and self.client_id == other.client_id
            and self.state_vector == other.state_vector
            # Required for differentiating between two split delete operations.
            # Assume we have ET_DI(Del(2 ("aa"), 0), Ins("abc", 1)). This will result in a split operation:
            # - Del(1 ("a"), 0), followed by Del(1 ("a"), 0).
            # Both operations have the same state vector, same index, same sequence, etc. We need a unique identifier to
            # differentiate between them. Discussed in Section 3.1.3 of the dissertation.
            and self.unique_id == other.unique_id
        )

    def __hash__(self):
        return hash(
            (
                self.num_to_delete,
                self.idx,
                self.client_id,
                tuple(self.state_vector),
                self.unique_id,
            )
        )
