import random

from algorithm_setup.algorithm_setup import logoot_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from logoot.logootdocument import LogootDocument, LogootIdentifier, position_less_than


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


# Two concurrent inserts can pick the same digit, so the positions differ only by their
# sites. Generating a position between them must terminate instead of searching the
# digits forever.
def test_generate_line_id_between_same_digit_positions():
    document = LogootDocument(1)
    p = [LogootIdentifier(480, 0, 2)]
    q = [LogootIdentifier(480, 2, 1)]

    new_id = document.generate_line_id(p, q, 1, 1)[0]

    assert position_less_than(p, new_id) is True
    assert position_less_than(new_id, q) is True


def test_trace_with_same_digit_positions_converges():
    random.seed(66)
    server, clients = logoot_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_prefix_position_sorts_first()
    test_trace_with_different_length_positions_converges()
    test_generate_line_id_between_same_digit_positions()
    test_trace_with_same_digit_positions_converges()
    print("OK")
