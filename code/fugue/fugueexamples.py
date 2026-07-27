from fugue.fugueclient import FugueClient
from unique_char.uniquechar import UniqueChar

def strong_list_specification_violation_example():
    #Set Up
    A = FugueClient(0)
    B = FugueClient(1)
    C = FugueClient(2)

    A.set_clients([A,B,C])
    B.set_clients([A,B,C])
    C.set_clients([A,B,C])

    #Operations

    A.perform_local_insert(0, UniqueChar.get_unique_char("b"))
    B.receive_from_client(A.client_id)
    C.receive_from_client(A.client_id)

    A.perform_local_delete(0)
    B.perform_local_insert(1, UniqueChar.get_unique_char("c"))
    C.perform_local_insert(0, UniqueChar.get_unique_char("a"))

    Alist = A.can_receive_from()
    while Alist:
        c = Alist.pop(0)
        A.receive_from_client(c)
        Alist = A.can_receive_from()

    Alist = B.can_receive_from()
    while Alist:
        c = Alist.pop(0)
        B.receive_from_client(c)
        Alist = B.can_receive_from()

    Alist = C.can_receive_from()
    while Alist:
        c = Alist.pop(0)
        C.receive_from_client(c)
        Alist = C.can_receive_from()


    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")
    print("C:", *C.read_state(), sep="")

def interleaving_example():
    #Set Up
    A = FugueClient(0)
    B = FugueClient(1)

    A.set_clients([A,B])
    B.set_clients([A,B])   

    #Operations

    A.perform_local_insert(0, UniqueChar.get_unique_char("a"))
    B.perform_local_insert(0, UniqueChar.get_unique_char("x"))
    A.perform_local_insert(1, UniqueChar.get_unique_char("b"))

    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    B.receive_from_client(A.client_id)

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")

def maximal_interleaving_example():
    A = FugueClient(0)
    B = FugueClient(1)
    C = FugueClient(2)

    A.set_clients([A,B,C])
    B.set_clients([A,B,C])
    C.set_clients([A,B,C])

    A.perform_local_insert(0, UniqueChar.get_unique_char("a"))
    B.perform_local_insert(0, UniqueChar.get_unique_char("b"))
    C.perform_local_insert(0, UniqueChar.get_unique_char("c"))

    A.receive_from_client(C.client_id)
    B.receive_from_client(A.client_id)
    C.receive_from_client(B.client_id)

    B.perform_local_insert(1, UniqueChar.get_unique_char("y"))
    A.perform_local_insert(1, UniqueChar.get_unique_char("x"))
    

    C.receive_from_client(A.client_id)

    A.receive_from_client(B.client_id)
    B.receive_from_client(C.client_id)
    C.receive_from_client(B.client_id)

    A.receive_from_client(B.client_id)
    B.receive_from_client(A.client_id)
    C.receive_from_client(A.client_id)

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")
    print("C:", *C.read_state(), sep="")

#strong_list_specification_violation_example()
#interleaving_example()