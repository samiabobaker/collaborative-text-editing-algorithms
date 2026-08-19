from got.operations.delete import GOTDeleteOperation
from got.operations.insert import GOTInsertOperation
from got.operations.operation import GOTOperation
from got.operations.split_delete import GOTSplitDeleteOperation
from got.transformations.inclusion import InclusionTransformer


class OriginalInclusionTransformer(InclusionTransformer):
    num_transformations_performed: int = 0

    def __init__(self):
        self.num_transformations_performed = 0

    # Performs an inclusion transform on two operations op_a and op_b that are both insertions
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_insert_insert(self, op_a: GOTInsertOperation, op_b: GOTInsertOperation) -> GOTOperation:
        transformed_op = op_a.copy()

        if op_a.idx < op_b.idx:
            return op_a.copy()
        else:
            transformed_op.idx += len(op_b.sequence)

        return transformed_op

    # Performs an inclusion transform on two operations op_a and op_b, where op_a is an insertion and op_b is a deletion
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_insert_delete(self, op_a: GOTInsertOperation, op_b: GOTDeleteOperation) -> GOTOperation:
        transformed_op = op_a.copy()

        if op_a.idx <= op_b.idx:
            return op_a.copy()
        elif op_a.idx > (op_b.idx + op_b.num_to_delete):
            transformed_op.idx -= op_b.num_to_delete
        else:
            transformed_op.idx = op_b.idx
            # op_a wanted to insert something after op_b.idx but before op_b.idx + op_b.num_to_delete (inclusive).
            # op_b deleted everything in that range, so op_a should be moved to op_b.idx
            # In this process, we have lost the position of *where exactly* op_a wanted to insert after op_b.idx
            # We save this lost information in the metadata so that when op_b is reversed and op_a is applied on top of
            # it, we know *exactly where* op_a.sequence should be inserted *relative* to op_b's starting index.
            # self.metadata.save_lost_information(transformed_op, op_a, op_b)
            transformed_op.save_lost_information(op_a, op_b)

        return transformed_op

    # Performs an inclusion transform on two operations op_a and op_b, where op_a is a deletion and op_b is an insertion
    # Assumes op_b has already been performed
    # Applies the effect of op_b on op_a
    # Returns a transformed op_a
    def _it_delete_insert(self, op_a: GOTDeleteOperation, op_b: GOTInsertOperation) -> GOTOperation:
        transformed_op = op_a.copy()

        if op_b.idx >= (op_a.idx + op_a.num_to_delete):
            return transformed_op
        elif op_a.idx >= op_b.idx:
            transformed_op.idx += len(op_b.sequence)
            return transformed_op
        else:
            transformed_op.num_to_delete = op_b.idx - op_a.idx
            transformed_op.sequence = op_a.sequence[: op_b.idx - op_a.idx]

            chained_op = op_a.copy()
            chained_op.num_to_delete = op_a.num_to_delete - (op_b.idx - op_a.idx)
            chained_op.idx = op_b.idx + len(op_b.sequence)
            chained_op.sequence = op_a.sequence[op_b.idx - op_a.idx :]
            chained_op.assign_unique_id()

            return GOTSplitDeleteOperation(
                transformed_op.client_id, transformed_op.state_vector.copy(), transformed_op, chained_op
            )

    def _it_delete_delete(self, op_a: GOTDeleteOperation, op_b: GOTDeleteOperation) -> GOTOperation:
        transformed_op = op_a.copy()

        if op_b.idx >= (op_a.idx + op_a.num_to_delete):
            return transformed_op
        elif op_a.idx >= (op_b.idx + op_b.num_to_delete):
            transformed_op.idx -= op_b.num_to_delete
            return transformed_op
        else:  # The deleting ranges are overlapping
            if op_b.idx <= op_a.idx and (op_a.idx + op_a.num_to_delete) <= (op_b.idx + op_b.num_to_delete):
                # op_b has already deleted everything in op_a's range
                transformed_op.num_to_delete = 0
                transformed_op.sequence = []
            elif op_b.idx <= op_a.idx and (op_a.idx + op_a.num_to_delete) > (op_b.idx + op_b.num_to_delete):
                transformed_op.num_to_delete = (op_a.idx + op_a.num_to_delete) - (op_b.idx + op_b.num_to_delete)
                transformed_op.idx = op_b.idx
                transformed_op.sequence = op_a.sequence[op_b.idx + op_b.num_to_delete - op_a.idx :]
            elif op_b.idx > op_a.idx and (op_b.idx + op_b.num_to_delete) >= (op_a.idx + op_a.num_to_delete):
                transformed_op.num_to_delete = op_b.idx - op_a.idx
                transformed_op.sequence = op_a.sequence[: op_b.idx - op_a.idx]
            else:
                transformed_op.num_to_delete -= op_b.num_to_delete
                transformed_op.sequence = (
                    op_a.sequence[: op_b.idx - op_a.idx] + op_a.sequence[op_b.idx + op_b.num_to_delete - op_a.idx :]
                )

            transformed_op.save_lost_information(op_a, op_b)
        return transformed_op

    def _inclusion_transform(self, op_a: GOTOperation, op_b: GOTOperation) -> GOTOperation:
        assert isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation))
        assert op_a.relative_addressed_to is None

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

    def list_inclusion_transform(self, op_a: GOTOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        if isinstance(op_a, (GOTInsertOperation, GOTDeleteOperation)):
            return self._list_it(op_a, op_list_2)
        elif isinstance(op_a, GOTSplitDeleteOperation):
            return self._list_it_split(op_a, op_list_2)
        else:
            raise ValueError("Invalid operation types")

    def _list_it_split(self, split_op: GOTSplitDeleteOperation, op_list_2: list[GOTOperation]) -> GOTOperation:
        transformed_list_1 = self.list_inclusion_transform(split_op.first, op_list_2)
        transformed_list_2 = self.list_inclusion_transform(split_op.second, op_list_2)  # + transformed_list_1)

        assert isinstance(transformed_list_1, (GOTDeleteOperation, GOTSplitDeleteOperation))
        assert isinstance(transformed_list_2, (GOTDeleteOperation, GOTSplitDeleteOperation))

        return GOTSplitDeleteOperation(
            client_id=split_op.client_id,
            state_vector=split_op.state_vector.copy(),
            first=transformed_list_1,
            second=transformed_list_2,
        )

    def _list_it(
        self, incoming_operation: GOTInsertOperation | GOTDeleteOperation, remaining: list[GOTOperation]
    ) -> GOTOperation:
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

    def include_split_deletes(self, split_delete_op: GOTSplitDeleteOperation) -> list[GOTOperation]:
        flattened = split_delete_op.flatten()

        transformed: list[GOTOperation] = []
        for i, op in enumerate(flattened):
            if i == 0:
                transformed.append(op)
            else:
                result = self.list_inclusion_transform(op, transformed[:i])

                if isinstance(result, GOTSplitDeleteOperation):
                    transformed.extend(self.include_split_deletes(result))
                else:
                    transformed.append(result)

        return transformed
