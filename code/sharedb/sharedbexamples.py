from __future__ import annotations

from device.operations import ClientDeleteOperation, ClientInsertOperation
from sharedb.sharedbclient import ShareDBClient
from sharedb.sharedbmessage import ShareDBDelete, ShareDBInsert, ShareDBMessage, ShareDBSkip
from sharedb.sharedbserver import ShareDBServer
from unique_char.uniquechar import UniqueChar


def __setup(number_of_clients: int) -> tuple[ShareDBServer, list[ShareDBClient]]:
    clients = [ShareDBClient(n) for n in range(number_of_clients)]
    server = ShareDBServer(clients)
    for client in clients:
        client.set_server(server)
    return server, clients


def __insert(client: ShareDBClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def __delete(client: ShareDBClient, position: int) -> None:
    character = client.read_state()[position]
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, character))


def __drain(server: ShareDBServer, clients: list[ShareDBClient]) -> None:
    """Deliver everything both ways until nothing is left in flight."""
    progressed = True
    while progressed:
        progressed = False
        for client_id in server.can_receive_from():
            server.receive_message(client_id)
            progressed = True
        for client in clients:
            while client.can_receive_from_server():
                client.receive_from_server()
                progressed = True


def __report(clients: list[ShareDBClient]) -> None:
    for client in clients:
        print(f"{client.client_id}:", *client.read_state(), sep="")


def __describe(message: ShareDBMessage) -> str:
    parts: list[str] = []
    for component in message.operation:
        match component:
            case ShareDBSkip(count):
                parts.append(str(count))
            case ShareDBInsert(characters):
                parts.append("".join(character.char for character in characters))
            case ShareDBDelete(count):
                parts.append(f"d{count}")
    return f"{message.client_id}:" + ",".join(parts)


def interleaving_example():
    """Two clients type a run of characters at the same position at once.

    A client sends one operation at a time and holds the rest, so of the three
    characters typed here only the first is sent on its own; the other two are made
    while it is still in flight and are composed into one operation. The server
    therefore sees each run as two operations rather than three, and the pair cannot be
    taken apart by anything the other client did, because transforming an insert against
    another insert never splits it.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "a")
    __insert(A, 1, "b")
    __insert(A, 2, "c")

    __insert(B, 0, "x")
    __insert(B, 1, "y")
    __insert(B, 2, "z")

    __drain(server, clients)
    __report(clients)
    print("committed:", [__describe(message) for message in server.committed])


def submitter_goes_first_example():
    """Two clients insert at the same position, with nothing else going on.

    Whichever operation the server commits second is transformed against the first as
    the left one, so it lands in front. The order is decided by the server, not by the
    client ids: it is the second one in that ends up first in the document.
    """
    server, clients = __setup(2)
    A, B = clients

    __insert(A, 0, "P")
    __drain(server, clients)

    __insert(A, 1, "a")
    __insert(B, 1, "b")

    server.receive_message(A.client_id)  # A's insert is committed first
    server.receive_message(B.client_id)  # B's is transformed against it, as the left one

    __drain(server, clients)
    __report(clients)


def concurrent_insert_and_delete_example():
    """A deletes the only character while B and C insert around it."""
    server, clients = __setup(3)
    A, B, C = clients

    __insert(A, 0, "b")
    __drain(server, clients)

    __delete(A, 0)
    __insert(B, 1, "c")
    __insert(C, 0, "a")

    __drain(server, clients)
    __report(clients)


if __name__ == "__main__":
    print("--- interleaving")
    interleaving_example()
    print("--- submitter goes first")
    submitter_goes_first_example()
    print("--- concurrent insert and delete")
    concurrent_insert_and_delete_example()
