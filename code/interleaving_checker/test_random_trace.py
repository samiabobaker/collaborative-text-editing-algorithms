import random

from algorithm_setup.algorithm_setup import fugue_setup, jupiter_setup, yjs_setup
from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation
from interleaving_checker.random_trace import build_random_trace


def test_trace_ends_with_all_messages_delivered():
    random.seed(0)
    server, clients = fugue_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    build_random_trace(client_dict, server, 30)

    for client in clients:
        assert client.can_receive_from() == []


def test_client_server_trace_ends_with_all_messages_delivered():
    random.seed(0)
    server, clients = jupiter_setup(3)
    assert server is not None

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    build_random_trace(client_dict, server, 30)

    assert server.can_receive_from() == []
    for client in clients:
        assert client.can_receive_from_server() is False
        assert client.can_receive_from() == []


def test_peer_trace_can_generate_deletes_and_still_drain_messages():
    random.seed(7)
    server, clients = yjs_setup(3)
    client_dict = {client.client_id: client for client in clients}

    client_logs, _ = build_random_trace(client_dict, server, 30, with_deletes=True)

    assert any(
        isinstance(operation, ClientDeleteOperation)
        for client_log in client_logs.values()
        for event in client_log.events_seen
        for operation in event.operation
    )
    assert all(client.can_receive_from() == [] for client in clients)


def test_client_server_trace_can_generate_deletes_and_still_drain_messages():
    random.seed(5)
    server, clients = jupiter_setup(3)
    assert server is not None
    client_dict = {client.client_id: client for client in clients}

    client_logs, _ = build_random_trace(client_dict, server, 30, with_deletes=True)

    assert any(
        isinstance(operation, ClientDeleteOperation)
        for client_log in client_logs.values()
        for event in client_log.events_seen
        for operation in event.operation
    )
    assert server.can_receive_from() == []
    assert all(client.can_receive_from_server() is False for client in clients)
    assert all(client.can_receive_from() == [] for client in clients)


if __name__ == "__main__":
    test_trace_ends_with_all_messages_delivered()
    test_client_server_trace_ends_with_all_messages_delivered()
    test_peer_trace_can_generate_deletes_and_still_drain_messages()
    test_client_server_trace_can_generate_deletes_and_still_drain_messages()
    print("OK")
