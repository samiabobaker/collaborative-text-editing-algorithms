from adoptedtm11.adoptedtm11client import AdOPTedTM11Client
from unique_char.uniquechar import UniqueChar
from device.operations import ClientInsertOperation

def interleaving_example():
    #Set Up
    A = AdOPTedTM11Client(0)
    B = AdOPTedTM11Client(1)

    A.set_clients([A,B])
    B.set_clients([A,B])   

    #Operations

    A.perform_operation(ClientInsertOperation(A.client_id, 0, UniqueChar.get_unique_char("a")))
    B.perform_operation(ClientInsertOperation(B.client_id, 0, UniqueChar.get_unique_char("x")))
    A.perform_operation(ClientInsertOperation(A.client_id, 1, UniqueChar.get_unique_char("b")))

    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    B.receive_from_client(A.client_id)

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")


interleaving_example()
