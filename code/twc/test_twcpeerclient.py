import random
from itertools import permutations
from typing import assert_never

from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientReceiveFromClientOperation
from rga.rgatree import RGATimestamp, RGATree
from twc.twcclient import TWCClient
from twc.twcmessage import TWCDeletionOperation, TWCInsertionOperation, TWCMessage
from twc.twcpeerclient import TWCPeerClient, TWCPeerMessage
from twc.twcserver import TWCServer
from unique_char.uniquechar import UniqueChar


def _build(count: int) -> list[TWCPeerClient]:
    clients = [TWCPeerClient(i) for i in range(count)]
    for client in clients:
        client.set_clients(clients)
    return clients


def _insert(client: TWCPeerClient, position: int, char: str) -> None:
    operation = ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char))
    assert client.perform_operation(operation) == [operation]


def _delete(client: TWCPeerClient, position: int) -> None:
    operation = ClientDeleteOperation(client.client_id, position, client.read_state()[position])
    assert client.perform_operation(operation) == [operation]


def _word(client: TWCPeerClient) -> str:
    return "".join(char.char for char in client.read_state())


def _drain(clients: list[TWCPeerClient]) -> None:
    while any(client.can_receive_from() for client in clients):
        for client in clients:
            for sender in client.can_receive_from():
                client.receive_from_client(sender)
    assert all(not inbox for client in clients for inbox in client.message_buffer.values())


def test_concurrent_order_is_independent_of_delivery_order():
    for order in permutations(range(3)):
        clients = _build(3)
        for client, char in zip(clients, "abc", strict=True):
            _insert(client, 0, char)
        for client in clients:
            for sender in order:
                if sender != client.client_id:
                    client.receive_from_client(sender)
        assert [_word(client) for client in clients] == ["cba"] * 3


def test_replay_keeps_local_edits_when_an_earlier_timestamp_arrives():
    a, b = clients = _build(2)
    _insert(a, 0, "a")
    _insert(b, 0, "b")
    _insert(b, 1, "c")
    # A's (1,0) sorts before both of B's edits. B must replay them as well.
    b.receive_from_client(a.client_id)
    assert _word(b) == "bca"
    _drain(clients)
    assert _word(a) == _word(b) == "bca"


def test_delivery_waits_for_dependencies_and_advances_the_clock():
    a, b, c = _build(3)
    _insert(a, 0, "x")
    b.receive_from_client(a.client_id)
    _insert(b, 1, "y")
    assert b.client_id not in c.can_receive_from()
    assert c.receive_from_client(b.client_id) == []
    c.receive_from_client(a.client_id)
    assert b.client_id in c.can_receive_from()
    c.receive_from_client(b.client_id)
    _insert(c, 2, "z")
    assert _word(c) == "xyz"
    assert c.clock > b.clock


def test_concurrent_deletes_and_insertion_after_deleted_anchor():
    a, b, c = clients = _build(3)
    _insert(a, 0, "x")
    _insert(a, 1, "y")
    _drain(clients)
    _delete(a, 0)
    _delete(b, 0)
    _insert(c, 1, "z")
    _drain(clients)
    assert [_word(client) for client in clients] == ["zy"] * 3


def _apply_reference(tree: RGATree, message: TWCPeerMessage, ids: dict[int, RGATimestamp]) -> None:
    match message.operation:
        case TWCInsertionOperation(_, before_id, element_id, character):
            timestamp = RGATimestamp(*message.timestamp)
            ids[element_id] = timestamp
            tree.insert_node(timestamp, None if before_id is None else ids[before_id], character)
        case TWCDeletionOperation(_, element_id):
            tree.delete_node_with_timestamp(ids[element_id])
        case _ as unreachable:
            assert_never(unreachable)


def _compare_history(seed: int, num_of_ops: int) -> None:
    random_source = random.Random(seed)
    clients = _build(3)
    trees = [RGATree(i) for i in range(3)]
    ids: dict[int, RGATimestamp] = {}

    def check_views() -> None:
        for client, tree in zip(clients, trees, strict=True):
            assert client.read_state() == [node.value for node in tree.traverse()], seed

    def receive(client: TWCPeerClient, sender: int) -> None:
        message = client.message_buffer[sender][0]
        result = client.perform_operation(ClientReceiveFromClientOperation(client.client_id, sender))
        assert result == [message.causing_operation]
        _apply_reference(trees[client.client_id], message, ids)
        check_views()

    for step in range(num_of_ops):
        client = random_source.choice(clients)
        senders = client.can_receive_from()
        if senders and random_source.randrange(2) == 0:
            receive(client, random_source.choice(senders))
        else:
            state = client.read_state()
            if state and random_source.randrange(3) == 0:
                _delete(client, random_source.randrange(len(state)))
            else:
                _insert(client, random_source.randrange(len(state) + 1), chr(0x100 + step))
            message = client.operations[(client.clock, client.client_id)]
            _apply_reference(trees[client.client_id], message, ids)
            check_views()

    while any(client.can_receive_from() for client in clients):
        for client in clients:
            for sender in client.can_receive_from():
                receive(client, sender)
    assert all(not inbox for client in clients for inbox in client.message_buffer.values())
    expected = clients[0].read_state()
    assert all(client.read_state() == expected for client in clients)

    # Give the real server implementation the identical anchored edits and total
    # order. This checks the common reducer, independently of server receipt order.
    served_clients = [TWCClient(i) for i in range(3)]
    server = TWCServer(served_clients)
    for client in served_clients:
        client.set_server(server)
    for timestamp, message in sorted(clients[0].operations.items()):
        server.send_message(timestamp[1], TWCMessage(message.operation, message.causing_operation))
        server.receive_message(timestamp[1])
    assert server.read_state() == expected, seed
    for client in served_clients:
        while client.can_receive_from_server():
            client.receive_message()
        assert client.read_state() == expected, seed


def test_matches_rga_and_server_for_same_order(num_of_seeds: int = 50, num_of_ops: int = 40):
    for seed in range(num_of_seeds):
        _compare_history(seed, num_of_ops)


if __name__ == "__main__":
    test_concurrent_order_is_independent_of_delivery_order()
    test_replay_keeps_local_edits_when_an_earlier_timestamp_arrives()
    test_delivery_waits_for_dependencies_and_advances_the_clock()
    test_concurrent_deletes_and_insertion_after_deleted_anchor()
    test_matches_rga_and_server_for_same_order()
    print("OK")
