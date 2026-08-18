from typing import assert_never

from dopt.doptmessage import (
    dOPTDeletionOperation,
    dOPTInsertionOperation,
    dOPTNoOperation,
    dOPTOperation,
)


class dOPTTransform:
    @staticmethod
    def transform_dOPT_operation(O1: dOPTOperation, O2: dOPTOperation) -> dOPTOperation:
        match O1, O2:
            case dOPTInsertionOperation(pr1, i, x), dOPTInsertionOperation(pr2, j, y):
                if i < j:
                    return dOPTInsertionOperation(pr1, i, x)
                elif i > j:
                    return dOPTInsertionOperation(pr1, i+1, x)
                else:
                    if x == y:
                        return dOPTNoOperation(pr1)
                    elif pr1 > pr2:
                        return dOPTInsertionOperation(pr1, i + 1, x)
                    else:
                        return dOPTInsertionOperation(pr1, i, x)
            case dOPTInsertionOperation(pr1, i, x), dOPTDeletionOperation(pr2, j):
                if i < j:
                    return dOPTInsertionOperation(pr1, i, x)
                else:
                    return dOPTInsertionOperation(pr1, i-1, x)
            case dOPTDeletionOperation(pr1, i), dOPTInsertionOperation(pr2, j, y):
                if i < j:
                    return dOPTDeletionOperation(pr1, i)
                else:
                    return dOPTDeletionOperation(pr1, i + 1)
            case dOPTDeletionOperation(pr1, i), dOPTDeletionOperation(pr2, j):
                if i < j:
                    return dOPTDeletionOperation(pr1, i)
                elif i > j:
                    return dOPTDeletionOperation(pr1, i - 1)
                else:
                    return dOPTNoOperation(pr1)
            case dOPTNoOperation(pr1), _:
                return dOPTNoOperation(pr1)
            case _, dOPTNoOperation():
                return O1
            case _ as unreachable:
                assert_never(unreachable)