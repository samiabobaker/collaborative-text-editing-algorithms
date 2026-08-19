import random

from algorithm_setup.algorithm_setup import logoot_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from logoot.logootdocument import LogootIdentifier, position_less_than


# A position that is a strict prefix of another sorts before it.
def test_prefix_position_sorts_first():
    p = [LogootIdentifier(5, 1, 1)]
    q = [LogootIdentifier(5, 1, 1), LogootIdentifier(3, 2, 1)]

    assert position_less_than(p, q) is True
    assert position_less_than(q, p) is False


# Dense traces generate positions of different lengths, so comparing them must not raise.
def test_trace_with_different_length_positions_converges():
    random.seed(41)
    server, clients = logoot_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 10) is True


if __name__ == "__main__":
    test_prefix_position_sorts_first()
    test_trace_with_different_length_positions_converges()
    print("OK")
