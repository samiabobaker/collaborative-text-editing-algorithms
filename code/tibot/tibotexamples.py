from tibot.tibotclient import TIBOTClient
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation, ClientDeleteOperation, ClientTimestepOperation, ClientReceiveFromClientOperation

#Examples from: https://github.com/aryan-25/got/blob/main/experiments/jupiter_examples.py
def strong_list_specification_violation_example():
    #Set Up
    A = TIBOTClient(0)
    B = TIBOTClient(1)

    A.set_clients([A,B])
    B.set_clients([A,B])

    #Operations

    A.perform_operation(ClientInsertOperation(0, 0, UniqueChar.get_unique_char("a")))
    B.perform_operation(ClientInsertOperation(1, 0, UniqueChar.get_unique_char("b")))

    A.perform_operation(ClientTimestepOperation(A.client_id))
    B.perform_operation(ClientTimestepOperation(B.client_id))

    A.perform_operation(ClientReceiveFromClientOperation(A.client_id, B.client_id))
    B.perform_operation(ClientReceiveFromClientOperation(B.client_id, A.client_id))

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")

def interleaving_example():
    #Set Up
    A = JupiterClient(0)
    B = JupiterClient(1)

    server = JupiterServer([A, B])

    A.set_server(server)
    B.set_server(server)    

    #Operations

    A.perform_local_insert(0, UniqueChar.get_unique_char("a"))
    B.perform_local_insert(0, UniqueChar.get_unique_char("x"))
    A.perform_local_insert(1, UniqueChar.get_unique_char("b"))

    server.receive_message(A.client_id)
    server.receive_message(B.client_id)
    server.receive_message(A.client_id)

    A.receive_message()
    B.receive_message()
    B.receive_message()

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")
    print("Server:", *server.read_state(), sep="")

strong_list_specification_violation_example()
#interleaving_example()