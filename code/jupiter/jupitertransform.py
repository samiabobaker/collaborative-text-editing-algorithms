from jupiter.jupitermessage import JupiterOperation, JupiterInsertionOperation, JupiterDeletionOperation, JupiterNoOperation

class JupiterTransform:
    @staticmethod
    def transform_jupiter_operation(client_operation: JupiterOperation, server_operation: JupiterOperation) -> tuple[JupiterOperation, JupiterOperation]:
        match client_operation, server_operation:
            case JupiterInsertionOperation(i, x), JupiterInsertionOperation(j, y):
                if i < j:
                    return JupiterInsertionOperation(i, x), JupiterInsertionOperation(j+1, y)
                elif i>j:
                    return JupiterInsertionOperation(i+1, x), JupiterInsertionOperation(j, y)
                elif i==j:
                    return JupiterInsertionOperation(i, x), JupiterInsertionOperation(j+1, y)
            case JupiterInsertionOperation(i, x), JupiterDeletionOperation(j):
                if i <= j:
                    return JupiterInsertionOperation(i, x), JupiterDeletionOperation(j+1)
                else:
                    return JupiterInsertionOperation(i-1, x), JupiterDeletionOperation(j)
            case JupiterDeletionOperation(i), JupiterInsertionOperation(j, y):
                if i < j:
                    return JupiterDeletionOperation(i), JupiterInsertionOperation(j-1, y)
                else:
                    return JupiterDeletionOperation(i+1), JupiterInsertionOperation(j, y)
            case JupiterDeletionOperation(i), JupiterDeletionOperation(j):
                if i > j:
                    return JupiterDeletionOperation(i-1), JupiterDeletionOperation(j)
                elif i < j:
                    return JupiterDeletionOperation(i), JupiterDeletionOperation(j-1)
                else:
                    return JupiterNoOperation(), JupiterNoOperation()
            case JupiterNoOperation(), oper:
                return JupiterNoOperation(), oper
            case oper, JupiterNoOperation():
                return oper, JupiterNoOperation()
            case _ as unreachable:
                assert_never(unreachable)