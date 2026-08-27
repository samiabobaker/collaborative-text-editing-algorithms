from __future__ import annotations

from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientReceiveFromServerOperation,
    ServerReceiveFromClientOperation,
)
from twc.twcclient import TWCClient
from twc.twcserver import TWCServer
from unique_char.uniquechar import UniqueChar


def __setup(num_of_clients: int) -> tuple[TWCServer, list[TWCClient]]:
    clients = [TWCClient(n) for n in range(num_of_clients)]
    server = TWCServer(clients)
    for client in clients:
        client.set_server(server)
    return server, clients


def __insert(client: TWCClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: TWCClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __commit(server: TWCServer, client_id: int) -> None:
    """Take one update off a client's queue, which fixes its place in the total order."""
    server.perform_operation(ServerReceiveFromClientOperation(client_id))


def __drain(server: TWCServer, clients: list[TWCClient]) -> None:
    """Commit every pending update, then hand the committed ones back to the clients."""
    progressed = True
    while progressed:
        progressed = False
        for client_id in server.can_receive_from():
            server.perform_operation(ServerReceiveFromClientOperation(client_id))
            progressed = True
        for client in clients:
            if client.can_receive_from_server():
                client.perform_operation(ClientReceiveFromServerOperation(client.client_id))
                progressed = True


def __report(server: TWCServer, clients: list[TWCClient]) -> None:
    print("server:", *server.read_state(), sep="")
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def concurrent_insert_example():
    """Two clients type one character each at the same position.

    Both send an insert after the start of the document. The server takes client 0's
    update first, but inserts after the same target end up in the reverse of the order
    the server received them, so client 1's character comes first.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "a")
    __insert(B, 0, "b")
    print("before either update reaches the server:")
    __report(server, clients)

    __commit(server, A.client_id)
    __commit(server, B.client_id)
    __drain(server, clients)
    __report(server, clients)


def interleaving_example():
    """Two clients type a run of characters at the same position at once.

    Each client chains its second character after its own first, so even though the
    server takes the updates interleaved, a, C, b, D, the runs stay contiguous.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(B, 0, "C")
    __insert(B, 1, "D")

    __commit(server, A.client_id)
    __commit(server, B.client_id)
    __commit(server, A.client_id)
    __commit(server, B.client_id)
    __drain(server, clients)
    __report(server, clients)


def concurrent_insert_and_delete_example():
    """A deletes the only character while B, which has not seen the delete, types after it.

    The server takes the delete first. The insert still lands because a deleted element
    keeps its place in the list as a tombstone, so there is still something to insert
    after.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "x")
    __drain(server, clients)

    __delete(A, 0)
    __insert(B, 1, "y")
    print("before either update reaches the server:")
    __report(server, clients)

    __commit(server, A.client_id)
    __commit(server, B.client_id)
    __drain(server, clients)
    __report(server, clients)


def pending_reconciliation_example():
    """A types two characters that are still pending when B's character commits first.

    A keeps showing its own two characters until the committed one arrives, at which
    point it rebuilds its view as the committed state plus its pending updates in the
    order it made them.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(B, 0, "z")
    print("with a and b still pending on client 0:")
    __report(server, clients)

    __commit(server, B.client_id)
    clients[0].perform_operation(ClientReceiveFromServerOperation(clients[0].client_id))
    print("after B's commit reaches client 0, its own updates still pending:")
    __report(server, clients)

    __drain(server, clients)
    __report(server, clients)


if __name__ == "__main__":
    print("--- concurrent inserts at the same position")
    concurrent_insert_example()
    print("--- interleaving")
    interleaving_example()
    print("--- concurrent insert and delete")
    concurrent_insert_and_delete_example()
    print("--- pending updates and reconciliation")
    pending_reconciliation_example()
