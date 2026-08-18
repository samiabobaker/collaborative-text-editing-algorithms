from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer
from unique_char.uniquechar import UniqueChar


# Examples from: https://github.com/aryan-25/got/blob/main/experiments/jupiter_examples.py
def strong_list_specification_violation_example():
    # Set Up
    A = JupiterClient(0)
    B = JupiterClient(1)
    C = JupiterClient(2)

    server = JupiterServer([A, B, C])

    A.set_server(server)
    B.set_server(server)
    C.set_server(server)

    # Operations

    A.perform_local_insert(0, UniqueChar.get_unique_char("b"))
    server.receive_message(A.client_id)
    B.receive_message()
    C.receive_message()

    A.perform_local_delete(0)
    B.perform_local_insert(1, UniqueChar.get_unique_char("c"))
    C.perform_local_insert(0, UniqueChar.get_unique_char("a"))

    server.receive_message(A.client_id)
    B.receive_message()
    C.receive_message()

    server.receive_message(B.client_id)
    server.receive_message(C.client_id)

    A.receive_message()
    A.receive_message()

    B.receive_message()
    B.receive_message()

    C.receive_message()
    C.receive_message()

    print("A:", *A.read_state(), sep="")
    print("B:", *B.read_state(), sep="")
    print("C:", *C.read_state(), sep="")
    print("Server:", *server.read_state(), sep="")


def interleaving_example():
    # Set Up
    A = JupiterClient(0)
    B = JupiterClient(1)

    server = JupiterServer([A, B])

    A.set_server(server)
    B.set_server(server)

    # Operations

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
# interleaving_example()
