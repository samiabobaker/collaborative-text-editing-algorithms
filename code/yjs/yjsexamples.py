from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar
from yjs.yjsclient import YjsClient


def __insert(client: YjsClient, position: int, char: str) -> None:
    client.perform_local_insert(
        ClientInsertOperation(
            client.client_id, position, UniqueChar.get_unique_char(char)
        )
    )


def __delete(client: YjsClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(
        ClientDeleteOperation(client.client_id, position, character)
    )


def __drain(clients: list[YjsClient]) -> None:
    """Deliver every message that is causally ready, until nothing is left."""
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def __position_of(client: YjsClient, char: str) -> int:
    return [c.char for c in client.read_state()].index(char)


def __report(clients: list[YjsClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def interleaving_example():
    """Two clients type a run of characters at the same position at once."""
    A = YjsClient(0)
    B = YjsClient(1)

    A.set_clients([A, B])
    B.set_clients([A, B])

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")

    __insert(B, 0, "x")
    __insert(B, 1, "y")
    __insert(B, 2, "z")

    __drain([A, B])
    __report([A, B])


def concurrent_insert_and_delete_example():
    """A deletes the only character while B and C insert around it."""
    A = YjsClient(0)
    B = YjsClient(1)
    C = YjsClient(2)

    A.set_clients([A, B, C])
    B.set_clients([A, B, C])
    C.set_clients([A, B, C])

    __insert(A, 0, "b")
    __drain([A, B, C])

    __delete(A, 0)
    __insert(B, 1, "c")
    __insert(C, 0, "a")

    __drain([A, B, C])
    __report([A, B, C])


def run_splitting_example():
    """The case that separates Yjs from YjsMod / Fugue.

    B types "xy" as one run. A concurrently inserts a single character just
    after "x", but A - unlike B - has already seen the character P that sits to
    the right. Yjs resolves the conflict on client id alone, so A's character
    lands between "x" and "y" and splits B's run.
    """
    A = YjsClient(0)
    B = YjsClient(1)
    W = YjsClient(2)

    A.set_clients([A, B, W])
    B.set_clients([A, B, W])
    W.set_clients([A, B, W])

    __insert(W, 0, "P")  # W types P
    __insert(B, 0, "x")  # B types x, without ever having seen P

    W.receive_from_client(B.client_id)  # W learns about x
    A.receive_from_client(W.client_id)  # A learns about P
    A.receive_from_client(B.client_id)  # A learns about x

    __insert(B, 1, "y")  # B continues its run: "xy"
    __insert(A, __position_of(A, "x") + 1, "a")  # A inserts just after x

    __drain([A, B, W])
    __report([A, B, W])


if __name__ == "__main__":
    print("--- interleaving")
    interleaving_example()
    print("--- concurrent insert and delete")
    concurrent_insert_and_delete_example()
    print("--- run splitting")
    run_splitting_example()
