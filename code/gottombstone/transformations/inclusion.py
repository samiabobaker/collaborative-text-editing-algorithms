import abc

from gottombstone.operations.operation import GOTTombstoneOperation


class InclusionTransformer(abc.ABC):
    num_transformations_performed: int

    @abc.abstractmethod
    def __init__(self):
        pass

    @abc.abstractmethod
    def _inclusion_transform(self, op_a: GOTTombstoneOperation, op_b: GOTTombstoneOperation) -> GOTTombstoneOperation:
        pass

    @abc.abstractmethod
    def list_inclusion_transform(self, op_a: GOTTombstoneOperation, op_list_2: list[GOTTombstoneOperation]) -> GOTTombstoneOperation:
        pass
