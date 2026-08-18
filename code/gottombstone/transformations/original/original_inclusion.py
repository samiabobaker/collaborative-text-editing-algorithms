from gottombstone.operations.delete import GOTDeleteOperation
from gottombstone.operations.insert import GOTInsertOperation
from gottombstone.operations.operation import GOTTombstoneOperation
from gottombstone.transformations.inclusion import InclusionTransformer


class OriginalInclusionTransformer(InclusionTransformer):
    num_transformations_performed: int = 0

    def __init__(self):
        self.num_transformations_performed = 0

    # Performs an inclusion transform on two operations op_a and op_b that are both insertions
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_insert_insert(self, op_a: GOTInsertOperation, op_b: GOTInsertOperation) -> GOTTombstoneOperation:
        transformed_op = op_a.copy()

        if op_a.idx < op_b.idx or op_a.idx == op_b.idx and op_a.client_id < op_b.client_id:
            return op_a.copy()
        else:
            transformed_op.idx += 1
        return transformed_op

    # Performs an inclusion transform on two operations op_a and op_b, where op_a is an insertion and op_b is a deletion
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_insert_delete(self, op_a: GOTInsertOperation, op_b: GOTDeleteOperation) -> GOTTombstoneOperation:
        return op_a.copy()

    # Performs an inclusion transform on two operations op_a and op_b, where op_a is a deletion and op_b is an insertion
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_delete_insert(self, op_a: GOTDeleteOperation, op_b: GOTInsertOperation) -> GOTTombstoneOperation:
        if op_a.idx < op_b.idx:
            return op_a.copy()
        else:
            transformed = op_a.copy()
            transformed.idx += 1
            return transformed

    def _it_delete_delete(self, op_a: GOTDeleteOperation, op_b: GOTDeleteOperation) -> GOTTombstoneOperation:
        return op_a.copy()

    def _inclusion_transform(self, op_a: GOTTombstoneOperation, op_b: GOTTombstoneOperation) -> GOTTombstoneOperation:
        assert isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation))
        assert op_a._relative_addressed_to is None

        if isinstance(op_a, GOTInsertOperation) and isinstance(op_b, GOTInsertOperation):
            out = self._it_insert_insert(op_a, op_b)
        elif isinstance(op_a, GOTInsertOperation) and isinstance(op_b, GOTDeleteOperation):
            out = self._it_insert_delete(op_a, op_b)
        elif isinstance(op_a, GOTDeleteOperation) and isinstance(op_b, GOTInsertOperation):
            out = self._it_delete_insert(op_a, op_b)
        elif isinstance(op_a, GOTDeleteOperation) and isinstance(op_b, GOTDeleteOperation):
            out = self._it_delete_delete(op_a, op_b)
        else:
            raise ValueError("Invalid operation types")

        self.num_transformations_performed += 1
        return out

    def list_inclusion_transform(self, op_a: GOTTombstoneOperation, op_list_2: list[GOTTombstoneOperation]) -> GOTTombstoneOperation:
        if isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation)):
            return self._list_it(op_a, op_list_2)
        else:
            raise ValueError("Invalid operation types")


    def _list_it(
        self, incoming_operation: GOTInsertOperation | GOTDeleteOperation, remaining: list[GOTTombstoneOperation]
    ) -> GOTTombstoneOperation:
        if not remaining:
            return incoming_operation.copy()

        head = remaining[0]
        assert isinstance(head, (GOTInsertOperation, GOTDeleteOperation))
        tail = remaining[1:]

        if incoming_operation.is_relatively_addressed() and not incoming_operation.check_relative_addressing(head):
            return self.list_inclusion_transform(incoming_operation, tail)
        elif incoming_operation.is_relatively_addressed() and incoming_operation.check_relative_addressing(head):
            assert isinstance(head, GOTInsertOperation)
            transformed = self._convert_to_absolutely_addressed(incoming_operation, head)
            return self.list_inclusion_transform(transformed, tail)
        else:
            return self.list_inclusion_transform(self._inclusion_transform(incoming_operation, head), tail)

    def _convert_to_absolutely_addressed(
        self, ra_op: GOTInsertOperation | GOTDeleteOperation, base_op: GOTInsertOperation
    ) -> GOTInsertOperation | GOTDeleteOperation:
        transformed_op = ra_op.copy_without_relative_addressing()
        transformed_op.idx += base_op.idx

        return transformed_op
