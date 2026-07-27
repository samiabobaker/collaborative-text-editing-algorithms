from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer
from fugue.fugueclient import FugueClient
from fuguemax.fuguemaxclient import FugueMaxClient
from list_spec_checker.list_spec_checker import strong_list_specification_checker, weak_list_specification_checker

def jupiter_strong():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = JupiterClient(0)
        B = JupiterClient(1)
        C = JupiterClient(2)

        server = JupiterServer([A, B, C])

        A.set_server(server)
        B.set_server(server)
        C.set_server(server)

        if not strong_list_specification_checker({0: A, 1: B, 2: C}, server):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)

def fugue_strong():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = FugueClient(0)
        B = FugueClient(1)
        C = FugueClient(2)

        A.set_clients([A,B,C])
        B.set_clients([A,B,C])
        C.set_clients([A,B,C])

        if not strong_list_specification_checker({0: A, 1: B, 2: C}):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)

def fuguemax_strong():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = FugueMaxClient(0)
        B = FugueMaxClient(1)
        C = FugueMaxClient(2)

        A.set_clients([A,B,C])
        B.set_clients([A,B,C])
        C.set_clients([A,B,C])

        if not strong_list_specification_checker({0: A, 1: B, 2: C}):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)

def jupiter_weak():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = JupiterClient(0)
        B = JupiterClient(1)
        C = JupiterClient(2)

        server = JupiterServer([A, B, C])

        A.set_server(server)
        B.set_server(server)
        C.set_server(server)

        if not weak_list_specification_checker({0: A, 1: B, 2: C}, server):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)

def fugue_weak():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = FugueClient(0)
        B = FugueClient(1)
        C = FugueClient(2)

        A.set_clients([A,B,C])
        B.set_clients([A,B,C])
        C.set_clients([A,B,C])

        if not weak_list_specification_checker({0: A, 1: B, 2: C}):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)

def fuguemax_weak():
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")

        A = FugueMaxClient(0)
        B = FugueMaxClient(1)
        C = FugueMaxClient(2)

        A.set_clients([A,B,C])
        B.set_clients([A,B,C])
        C.set_clients([A,B,C])

        if not weak_list_specification_checker({0: A, 1: B, 2: C}):
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            input()
            print("-"*80)