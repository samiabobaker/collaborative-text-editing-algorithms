from __future__ import annotations

from got.operations.delete import GOTDeleteOperation
from got.operations.operation import GOTOperation
from unique_char.uniquechar import UniqueChar

type StateVector = dict[int, int]


class GOTInsertOperation(GOTOperation):
    """
    An implementation of an Insert operation for the GOT algorithm.
    """

    _lost_information: tuple[GOTInsertOperation, GOTDeleteOperation] | None
    _relative_addressed_to: StateVector | None = None

    def __init__(self, idx: int, sequence: list[UniqueChar], client_id: int, state_vector: dict[int, int]):
        self.client_id = client_id
        self.state_vector = state_vector
        self.idx = idx
        self.sequence = sequence

        self._precedes: set[tuple[int, ...]] = set()
        self._lost_information = None
        self._relative_addressed_to = None

    def save_lost_information(self, original_op_a: GOTInsertOperation, op_b: GOTDeleteOperation) -> None:
        """
        Saves the lost information pair (original_op_a, op_b) for later retrieval.
        """
        self._lost_information = (original_op_a, op_b)

    def check_lost_information(self, op_b: GOTDeleteOperation) -> bool:
        """
        Checks if the operation has lost information related to op_b.
        """
        return self._lost_information is not None and op_b == self._lost_information[1]

    def retrieve_lost_information(self, op_b: GOTDeleteOperation) -> GOTInsertOperation:
        """
        Returns the lost information pair if `op_b` matches the saved lost information.
        """
        assert self._lost_information is not None and op_b == self._lost_information[1]
        return self._lost_information[0]

    def save_relative_addressing(self, op_b: GOTInsertOperation) -> None:
        """
        Saves the relative addressing state vector of the operation `op_b`.
        """
        assert self._relative_addressed_to is None
        self._relative_addressed_to = op_b.state_vector

    def is_relatively_addressed(self) -> bool:
        """
        Checks if the operation is relatively addressed to another operation.
        """
        return self._relative_addressed_to is not None

    def check_relative_addressing(self, op_b: GOTOperation) -> bool:
        """
        Checks if the operation is relatively addressed to `op_b`.
        """
        assert self._relative_addressed_to is not None
        return op_b.state_vector == self._relative_addressed_to

    def save_precedes(self, op_b: GOTOperation) -> None:
        """
        Saves within this operation that it precedes the operation `op_b`. This information is then used by
        the IT_II transformation to never push the index of this operation past the index of `op_b`. This is the
        modified version of IT_II which we propose.
        """
        assert isinstance(op_b, GOTInsertOperation)
        self._precedes.add(tuple(op_b.state_vector.values()))

    def check_if_precedes(self, op_b: GOTInsertOperation) -> bool:
        """
        Checks if this operation precedes the provided `op_b` operation.
        """
        return tuple(op_b.state_vector) in self._precedes

    def copy(self) -> GOTInsertOperation:
        """
        Returns a copy of the operation *including all internal state*.
        """
        copied = GOTInsertOperation(self.idx, self.sequence[:], self.client_id, self.state_vector.copy())

        copied._precedes = self._precedes.copy()
        copied._lost_information = self._lost_information
        copied._relative_addressed_to = self._relative_addressed_to
        return copied

    def remove_all_metadata(self):
        """
        Returns a copy of the operation with all metadata removed.
        This method is intended to be used to sanitise the internal state of an incoming operation from another client.
        """
        return GOTInsertOperation(self.idx, self.sequence[:], self.client_id, self.state_vector.copy())

    def copy_without_relative_addressing(self) -> GOTInsertOperation:
        """
        Returns a copy of the operation including all internal state *except `relative_addressed_to`*.
        """
        copied = GOTInsertOperation(self.idx, self.sequence[:], self.client_id, self.state_vector.copy())
        copied._precedes = self._precedes.copy()
        copied._lost_information = self._lost_information
        return copied

    def __str__(self):
        return rf"Ins({self.sequence}, {self.idx}, c={self.client_id}, sv={self.state_vector}, RA={self._relative_addressed_to}, LI={self._lost_information})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other: object):
        return (
            isinstance(other, GOTInsertOperation)
            and self.idx == other.idx
            and self.sequence == other.sequence
            and self.client_id == other.client_id
            and self.state_vector == other.state_vector
        )

    def __hash__(self):
        return hash((tuple(self.state_vector), self.idx, self.sequence, self.client_id))
