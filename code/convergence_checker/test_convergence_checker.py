import random

from adopted.adoptedtransform import EllisTransform
from algorithm_setup.algorithm_setup import adopted_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice


# Ellis's transformation rules can produce a delete one position past the end of a
# diverged replica's state. The checker reports non-convergence instead of crashing.
def test_inapplicable_operation_reports_non_convergence():
    random.seed(55)
    server, clients = adopted_setup(EllisTransform)(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is False


if __name__ == "__main__":
    test_inapplicable_operation_reports_non_convergence()
    print("OK")
