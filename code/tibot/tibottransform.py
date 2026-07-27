from unique_char.uniquechar import UniqueChar
from tibot.tibotmessage import TIBOTOperation, TIBOTNoOperation, TIBOTInsertionOperation, TIBOTDeletionOperation
from typing import assert_never

def undo_TIBOT_operation(state: list[UniqueChar], operation: TIBOTOperation) -> list[UniqueChar]:
    match operation.operation:
        case TIBOTInsertionOperation(position, _):
            return state[:position] + state[position+1:]
        case TIBOTDeletionOperation(position, character):
            #Insert character at position
            return state[:position] + [character] + state[position:] 
        case TIBOTNoOperation():
            return state
        case _ as unreachable:
            assert_never(unreachable)

def undo_TIBOT_operations(state: list[UniqueChar], operations: list[TIBOTOperation]) -> list[UniqueChar]:
    new_state = state
    for operation in reversed(operations):
        new_state = undo_TIBOT_operation(new_state, operation)
    return new_state

def SLOT(L1: list[TIBOTOperation], L2: list[TIBOTOperation]) -> list[TIBOTOperation]:
    transformed_L1 = list(L1)
    transformed_L2 = list(L2)
    for i in range(len(L1)):
        for j in range(len(L2)):
            transformed_L2[j], transformed_L1[i] = transform_TIBOT_operation(transformed_L2[j], transformed_L1[i])
    return transformed_L1


def transform_TIBOT_operation(O1: TIBOTOperation, O2: TIBOTOperation) -> tuple[TIBOTOperation, TIBOTOperation]:
    match O1.operation, O2.operation:
        case TIBOTInsertionOperation(i, x), TIBOTInsertionOperation(j, y):
            if i < j:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTInsertionOperation(i, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTInsertionOperation(j+1, y))
            else:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTInsertionOperation(i+1, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTInsertionOperation(j, y))
        case TIBOTInsertionOperation(i, x), TIBOTDeletionOperation(j, y):
            if i <= j:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTInsertionOperation(i, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTDeletionOperation(j+1, y))
            else:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTInsertionOperation(i-1, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTDeletionOperation(j, y))
        case TIBOTDeletionOperation(i, x), TIBOTInsertionOperation(j, y):
            if i < j:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTDeletionOperation(i, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTInsertionOperation(j-1, y))
            else:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTDeletionOperation(i+1, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTInsertionOperation(j, y))
        case TIBOTDeletionOperation(i, x), TIBOTDeletionOperation(j, y):
            if i > j:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTDeletionOperation(i-1, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTDeletionOperation(j, y))
            elif i < j:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTDeletionOperation(i, x))
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTDeletionOperation(j-1, y))
            else:
                transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTNoOperation())
                transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTNoOperation())
        case TIBOTNoOperation(), _:
            transformed_O1 = TIBOTOperation(O1.time_interval, O1.client_id, O1.sequence_number, TIBOTNoOperation())
            transformed_O2 = O2
        case _, TIBOTNoOperation():
            transformed_O1 = O1
            transformed_O2 = TIBOTOperation(O2.time_interval, O2.client_id, O2.sequence_number, TIBOTNoOperation())
        case _ as unreachable:
            assert_never(unreachable)
    return transformed_O1, transformed_O2