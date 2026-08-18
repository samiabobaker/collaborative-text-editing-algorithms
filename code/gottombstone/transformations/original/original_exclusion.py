
from gottombstone.operations.delete import GOTDeleteOperation
from gottombstone.operations.insert import GOTInsertOperation
from gottombstone.operations.operation import GOTTombstoneOperation
from gottombstone.transformations.exclusion import ExclusionTransformer


class OriginalExclusionTransformer(ExclusionTransformer):
    num_transformations_performed: int

    def __init__(self):
        self.num_transformations_performed = 0

    def _et_insert_insert(self, op_a: GOTInsertOperation, op_b: GOTInsertOperation) -> GOTTombstoneOperation:
        if op_a.idx <= op_b.idx:
            return op_a.copy()

        transformed = op_a.copy()
        transformed.idx -= 1
        return transformed

    def _et_insert_delete(self, op_a: GOTInsertOperation, op_b: GOTDeleteOperation) -> GOTTombstoneOperation:
        return op_a.copy()

    def _et_delete_insert(self, op_a: GOTDeleteOperation, op_b: GOTInsertOperation) -> GOTTombstoneOperation:
        if op_a.idx < op_b.idx:
            return op_a.copy()
        else:
            transformed_op = op_a.copy()
            transformed_op.idx -= 1
            return transformed_op
        
    def _et_delete_delete(self, op_a: GOTDeleteOperation, op_b: GOTDeleteOperation) -> GOTTombstoneOperation:
        return op_a.copy()

    def _exclusion_transform(self, op_a: GOTTombstoneOperation, op_b: GOTTombstoneOperation) -> GOTTombstoneOperation:
        assert isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation))

        if isinstance(op_a, GOTInsertOperation) and isinstance(op_b, GOTInsertOperation):
            out = self._et_insert_insert(op_a, op_b)
        elif isinstance(op_a, GOTInsertOperation) and isinstance(op_b, GOTDeleteOperation):
            out = self._et_insert_delete(op_a, op_b)
        elif isinstance(op_a, GOTDeleteOperation) and isinstance(op_b, GOTInsertOperation):
            out = self._et_delete_insert(op_a, op_b)
        elif isinstance(op_a, GOTDeleteOperation) and isinstance(op_b, GOTDeleteOperation):
            out = self._et_delete_delete(op_a, op_b)
        else:
            raise ValueError("Invalid operation types")

        self.num_transformations_performed += 1
        return out

    def list_exclusion_transform(self, op_a: GOTTombstoneOperation, op_list_2: list[GOTTombstoneOperation]) -> GOTTombstoneOperation:
        if isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation)):
            return self._list_et(op_a, op_list_2)
        else:
            raise ValueError("Invalid operation type")

    def _list_et(self, op_a: GOTInsertOperation | GOTDeleteOperation, remaining: list[GOTTombstoneOperation]) -> GOTTombstoneOperation:
        if op_a.is_relatively_addressed() or not remaining:
            return op_a.copy()

        excluded_head = self._exclusion_transform(op_a, remaining[0])
        return self.list_exclusion_transform(excluded_head, remaining[1:])
