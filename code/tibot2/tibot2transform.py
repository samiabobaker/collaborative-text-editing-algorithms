from typing import assert_never

from tibot2.tibot2message import (
    TIBOT2DeletionOperation,
    TIBOT2InsertionOperation,
    TIBOT2NoOperation,
    TIBOT2Operation,
)
from unique_char.uniquechar import UniqueChar


def undo_TIBOT_operation(state: list[UniqueChar], operation: TIBOT2Operation) -> list[UniqueChar]:
    match operation.operation:
        case TIBOT2InsertionOperation(position, _):
            return state[:position] + state[position + 1 :]
        case TIBOT2DeletionOperation(position, character):
            # Insert character at position
            return state[:position] + [character] + state[position:]
        case TIBOT2NoOperation():
            return state
        case _ as unreachable:
            assert_never(unreachable)


def undo_TIBOT_operations(state: list[UniqueChar], operations: list[TIBOT2Operation]) -> list[UniqueChar]:
    new_state = state
    for operation in reversed(operations):
        new_state = undo_TIBOT_operation(new_state, operation)
    return new_state


def SLOT(L1: list[TIBOT2Operation], L2: list[TIBOT2Operation]) -> tuple[list[TIBOT2Operation], list[TIBOT2Operation]]:
    transformed_L1 = list(L1)
    transformed_L2 = list(L2)
    for i in range(len(L1)):
        for j in range(len(L2)):
            transformed_L2[j], transformed_L1[i] = transform_TIBOT_operation(transformed_L2[j], transformed_L1[i])
    return transformed_L1, transformed_L2


def transform_TIBOT_operation(O1: TIBOT2Operation, O2: TIBOT2Operation) -> tuple[TIBOT2Operation, TIBOT2Operation]:
    match O1.operation, O2.operation:
        case TIBOT2InsertionOperation(i, x), TIBOT2InsertionOperation(j, y):
            if i < j:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2InsertionOperation(i, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2InsertionOperation(j + 1, y)
                )
            else:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2InsertionOperation(i + 1, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2InsertionOperation(j, y)
                )
        case TIBOT2InsertionOperation(i, x), TIBOT2DeletionOperation(j, y):
            if i <= j:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2InsertionOperation(i, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2DeletionOperation(j + 1, y)
                )
            else:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2InsertionOperation(i - 1, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2DeletionOperation(j, y)
                )
        case TIBOT2DeletionOperation(i, x), TIBOT2InsertionOperation(j, y):
            if i < j:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2DeletionOperation(i, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2InsertionOperation(j - 1, y)
                )
            else:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2DeletionOperation(i + 1, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2InsertionOperation(j, y)
                )
        case TIBOT2DeletionOperation(i, x), TIBOT2DeletionOperation(j, y):
            if i > j:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2DeletionOperation(i - 1, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2DeletionOperation(j, y)
                )
            elif i < j:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2DeletionOperation(i, x)
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2DeletionOperation(j - 1, y)
                )
            else:
                transformed_O1 = TIBOT2Operation(
                    O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2NoOperation()
                )
                transformed_O2 = TIBOT2Operation(
                    O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2NoOperation()
                )
        case TIBOT2NoOperation(), _:
            transformed_O1 = TIBOT2Operation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOT2NoOperation())
            transformed_O2 = O2
        case _, TIBOT2NoOperation():
            transformed_O1 = O1
            transformed_O2 = TIBOT2Operation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOT2NoOperation())
        case _ as unreachable:
            assert_never(unreachable)
    return transformed_O1, transformed_O2
