import abc

from got.operations.operation import GOTOperation


class ExclusionTransformer(abc.ABC):
    num_transformations_performed: int

    @abc.abstractmethod
    def __init__(self):
        pass

    @abc.abstractmethod
    def _exclusion_transform(self, op_a: GOTOperation, op_b: GOTOperation) -> GOTOperation:
        pass

    @abc.abstractmethod
    def list_exclusion_transform(self, op_a: GOTOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        pass
