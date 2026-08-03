import abc

from got.operations.split_delete import GOTSplitDeleteOperation
from got.operations.operation import GOTOperation

class InclusionTransformer(abc.ABC):
    num_transformations_performed: int

    @abc.abstractmethod
    def __init__(self):
        pass

    @abc.abstractmethod
    def _inclusion_transform(self, op_a: GOTOperation, op_b: GOTOperation) -> GOTOperation:
        pass

    @abc.abstractmethod
    def list_inclusion_transform(self, op_a: GOTOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        pass

    @abc.abstractmethod
    def include_split_deletes(self, split_delete_op: GOTSplitDeleteOperation) -> list[GOTOperation]:
        pass
