from __future__ import annotations

import abc

from unique_char.uniquechar import UniqueChar


class GOTOperation:
    """
    An abstract class to represent operations in the GOT algorithm.

    Contains concrete definitions for the following methods:
    - is_totally_ordered
    - is_causally_ordered
    - is_independent
    """

    client_id: int
    state_vector: dict[int, int]
    idx: int
    sequence: list[UniqueChar]

    @abc.abstractmethod
    def copy(self) -> GOTOperation:
        pass

    @abc.abstractmethod
    def copy_without_relative_addressing(self) -> GOTOperation:
        pass

    @abc.abstractmethod
    def remove_all_metadata(self) -> GOTOperation:
        pass

    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @abc.abstractmethod
    def __repr__(self) -> str:
        pass

    @abc.abstractmethod
    def __str__(self) -> str:
        pass

    @abc.abstractmethod
    def __hash__(self) -> int:
        pass

    def is_totally_ordered(self, other: GOTOperation) -> bool:
        """
        For `self` to be totally ordered before `other`, the following must hold:
        - The sum of `self.state_vector` must be less than the sum of `other.state_vector`.
        - If the sums are equal, then the client ID of `self` must be less than the client ID of `other`.
        """
        self_sum = sum(self.state_vector.values())
        other_sum = sum(other.state_vector.values())

        return (self_sum < other_sum) or (self_sum == other_sum and self.client_id < other.client_id)

    def is_causally_ordered(self, other: GOTOperation) -> bool:
        """
        For `self` to be causally ordered before to `other`, `self` has to be executed at the site
        `other` is coming from _before_ `other` was generated, i.e.:
        `self.state_vector[self.client_id]` <= `other.state_vector[self.client_id]`
        """

        return self.state_vector[self.client_id] <= other.state_vector[self.client_id]

    def is_independent(self, other: GOTOperation) -> bool:
        """
        `self` is independent of `other` iff `self` is not causally ordered before `other` and
        `other` is not causally ordered before `self`.
        """

        return not self.is_causally_ordered(other) and not other.is_causally_ordered(self)
