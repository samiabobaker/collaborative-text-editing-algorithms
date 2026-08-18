from got.operations.delete import GOTDeleteOperation
from got.operations.insert import GOTInsertOperation
from got.operations.operation import GOTOperation
from got.operations.split_delete import GOTSplitDeleteOperation
from got.transformations.exclusion import ExclusionTransformer


class OriginalExclusionTransformer(ExclusionTransformer):
    num_transformations_performed: int

    def __init__(self):
        self.num_transformations_performed = 0

    def _et_insert_insert(self, op_a: GOTInsertOperation, op_b: GOTInsertOperation) -> GOTOperation:
        transformed_operation = op_a.copy()
        if op_a.idx <= op_b.idx:
            return op_a.copy()
        elif op_a.idx >= (op_b.idx + len(op_b.sequence)):
            transformed_operation.idx -= len(op_b.sequence)
        else:
            transformed_operation.idx -= op_b.idx
            transformed_operation.save_relative_addressing(op_b)
        return transformed_operation

    def _et_insert_delete(self, op_a: GOTInsertOperation, op_b: GOTDeleteOperation) -> GOTOperation:
        if op_a.check_lost_information(op_b):
            return op_a.retrieve_lost_information(op_b).copy()
        elif op_a.idx <= op_b.idx:
            return op_a.copy()
        else:
            transformed_operation = op_a.copy()
            transformed_operation.idx += op_b.num_to_delete
            return transformed_operation

    def _et_delete_insert(self, op_a: GOTDeleteOperation, op_b: GOTInsertOperation) -> GOTOperation:
        if op_a.num_to_delete == 0:
            return op_a.copy()

        transformed_operation = op_a.copy()
        if (op_a.idx + op_a.num_to_delete) <= op_b.idx:
            return op_a.copy()
        elif op_a.idx >= (op_b.idx + len(op_b.sequence)):
            transformed_operation.idx -= len(op_b.sequence)
            return transformed_operation

        if op_b.idx <= op_a.idx and (op_a.idx + op_a.num_to_delete) <= (op_b.idx + len(op_b.sequence)):
            transformed_operation.idx -= op_b.idx
            transformed_operation.save_relative_addressing(op_b)
            return transformed_operation

        if op_b.idx <= op_a.idx and (op_a.idx + op_a.num_to_delete) > (op_b.idx + len(op_b.sequence)):
            split_position = op_b.idx + len(op_b.sequence) - op_a.idx
            split_sequence = (
                transformed_operation.sequence[:split_position],
                transformed_operation.sequence[split_position:],
            )

            transformed_operation.num_to_delete = split_position
            transformed_operation.sequence = split_sequence[0]
            transformed_operation.idx -= op_b.idx

            chained_op = op_a.copy()
            chained_op.num_to_delete = (op_a.idx + op_a.num_to_delete) - (op_b.idx + len(op_b.sequence))
            chained_op.idx = op_b.idx
            chained_op.sequence = split_sequence[1]

        elif op_a.idx < op_b.idx and (op_b.idx + len(op_b.sequence)) <= (op_a.idx + op_a.num_to_delete):
            transformed_operation.num_to_delete = len(op_b.sequence)
            transformed_operation.sequence = op_b.sequence
            transformed_operation.idx = 0

            chained_op = op_a.copy()
            chained_op.num_to_delete = op_a.num_to_delete - len(op_b.sequence)
            chained_op.sequence = (
                op_a.sequence[: op_b.idx - op_a.idx] + op_a.sequence[op_b.idx + len(op_b.sequence) - op_a.idx :]
            )

        else:
            transformed_operation.num_to_delete = op_a.idx + op_a.num_to_delete - op_b.idx
            transformed_operation.sequence = op_a.sequence[op_b.idx - op_a.idx :]
            transformed_operation.idx = 0

            chained_op = op_a.copy()
            chained_op.num_to_delete = op_b.idx - op_a.idx
            chained_op.sequence = op_a.sequence[: op_b.idx - op_a.idx]

        transformed_operation.save_relative_addressing(op_b)
        chained_op.assign_unique_id()

        return GOTSplitDeleteOperation(
            client_id=transformed_operation.client_id,
            state_vector=transformed_operation.state_vector.copy(),
            first=transformed_operation,
            second=chained_op,
        )

    def _et_delete_delete(self, op_a: GOTDeleteOperation, op_b: GOTDeleteOperation) -> GOTOperation:
        if op_a.check_lost_information(op_b):
            return op_a.retrieve_lost_information(op_b).copy()
        else:
            if op_b.idx >= (op_a.idx + op_a.num_to_delete):
                return op_a.copy()

            transformed_operation = op_a.copy()
            if op_a.idx >= op_b.idx:
                transformed_operation.idx += op_b.num_to_delete
                return transformed_operation

            transformed_operation.num_to_delete = op_b.idx - op_a.idx
            transformed_operation.sequence = op_a.sequence[: op_b.idx - op_a.idx]

            chained_op = op_a.copy()
            chained_op.num_to_delete = op_a.num_to_delete - (op_b.idx - op_a.idx)
            chained_op.idx = op_b.idx + op_b.num_to_delete
            chained_op.sequence = op_a.sequence[op_b.idx - op_a.idx :]
            chained_op.assign_unique_id()

            return GOTSplitDeleteOperation(
                client_id=transformed_operation.client_id,
                state_vector=transformed_operation.state_vector.copy(),
                first=transformed_operation,
                second=chained_op,
            )

    def _exclusion_transform(self, op_a: GOTOperation, op_b: GOTOperation) -> GOTOperation:
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

    def list_exclusion_transform(self, op_a: GOTOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        if isinstance(op_a, GOTSplitDeleteOperation):
            return self._list_et_split(op_a, op_list_2)
        elif isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation)):
            return self._list_et(op_a, op_list_2)
        else:
            raise ValueError("Invalid operation type")

    def _list_et_split(self, split_op: GOTSplitDeleteOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        if len(op_list_2) == 0:
            return split_op.copy()

        tl1 = self.list_exclusion_transform(split_op.first, op_list_2)
        tl2 = self.list_exclusion_transform(split_op.second, op_list_2)

        assert isinstance(tl1, (GOTDeleteOperation, GOTSplitDeleteOperation))
        assert isinstance(tl2, (GOTDeleteOperation, GOTSplitDeleteOperation))

        return GOTSplitDeleteOperation(
            client_id=split_op.client_id, state_vector=split_op.state_vector.copy(), first=tl1, second=tl2
        )

    def _list_et(self, op_a: GOTInsertOperation | GOTDeleteOperation, remaining: list[GOTOperation]) -> GOTOperation:
        if op_a.is_relatively_addressed() or not remaining:
            return op_a.copy()

        excluded_head = self._exclusion_transform(op_a, remaining[0])
        return self.list_exclusion_transform(excluded_head, remaining[1:])
