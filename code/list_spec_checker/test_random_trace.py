import random

from adopted.adoptedtransform import EllisTransform
from algorithm_setup.algorithm_setup import adopted_setup, fugue_setup, jupiter_setup
from device.clientdevice import ClientDevice
from list_spec_checker.list_spec_checker import strong_list_specification_checker
from list_spec_checker.random_trace import build_random_trace


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


# Ellis's transformation rules can produce a delete one position past the end of a
# diverged replica's state while draining. The checker reports a violation instead
# of crashing.
def test_inapplicable_operation_reports_violation():
    random.seed(55)
    server, clients = adopted_setup(EllisTransform)(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert strong_list_specification_checker(client_dict, server, 30) is False


if __name__ == "__main__":
    test_trace_ends_with_all_messages_delivered()
    test_client_server_trace_ends_with_all_messages_delivered()
    test_inapplicable_operation_reports_violation()
    print("OK")
