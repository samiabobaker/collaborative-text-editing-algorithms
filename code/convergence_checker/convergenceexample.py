from convergence_checker.convergence_checker import (
    check_for_convergence_client_client,
    check_for_convergence_client_server,
)
from fugue.fugueclient import FugueClient
from fuguemax.fuguemaxclient import FugueMaxClient
from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer


def jupiter_convergence():
    cases = 0

    while True:
        if cases % 1000 == 0:
            print(f"{cases} cases checked.")

        A = JupiterClient(0)
        B = JupiterClient(1)
        C = JupiterClient(2)

        server = JupiterServer([A, B, C])

        A.set_server(server)
        B.set_server(server)
        C.set_server(server)

        converges = check_for_convergence_client_server(server, {A.client_id: A, B.client_id: B, C.client_id: C}, 30)

        if not converges:
            print(f"Converges {converges}")
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            print("Server:", *server.read_state(), sep="")
            print("-" * 80)
            input()

        cases += 1


def fugue_convergence():
    cases = 0

    while True:
        if cases % 1000 == 0:
            print(f"{cases} cases checked.")

        A = FugueClient(0)
        B = FugueClient(1)
        C = FugueClient(2)

        A.set_clients([A, B, C])
        B.set_clients([A, B, C])
        C.set_clients([A, B, C])

        converges = check_for_convergence_client_client({A.client_id: A, B.client_id: B, C.client_id: C}, 30)

        if not converges:
            print(f"Converges {converges}")
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            print("-" * 80)
            input()

        cases += 1


def fuguemax_convergence():
    cases = 0

    while True:
        if cases % 1000 == 0:
            print(f"{cases} cases checked.")

        A = FugueMaxClient(0)
        B = FugueMaxClient(1)
        C = FugueMaxClient(2)

        A.set_clients([A, B, C])
        B.set_clients([A, B, C])
        C.set_clients([A, B, C])

        converges = check_for_convergence_client_client({A.client_id: A, B.client_id: B, C.client_id: C}, 30)

        if not converges:
            print(f"Converges {converges}")
            print("A:", *A.read_state(), sep="")
            print("B:", *B.read_state(), sep="")
            print("C:", *C.read_state(), sep="")
            print("-" * 80)
            input()

        cases += 1


# fugue_convergence()
