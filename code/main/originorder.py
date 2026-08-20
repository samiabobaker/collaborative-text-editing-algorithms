import random

from algorithm_setup.algorithm_setup import DeviceSetup
from device.clientdevice import ClientDevice
from origin_order_checker.origin_order_checker import anchoring_checker, origin_order_checker


def origin_order_with_seed(
    n: int, device_setup: DeviceSetup, num_of_clients: int = 3, num_of_ops: int = 30, pause_on_failure: bool = True
) -> bool:
    # The anchoring scenario is fixed rather than generated, so it settles the same way on
    # every seed and is checked alongside the scheme and the key rather than instead of them.
    if not anchoring_checker(device_setup, print_ops=True):
        print(f"Failed with seed {n}")
        if pause_on_failure:
            input()
        return False

    random.seed(n)

    server, clients = device_setup(num_of_clients)

    client_dict: dict[int, ClientDevice] = {}

    for client in clients:
        client_dict[client.client_id] = client

    if not origin_order_checker(client_dict, server, num_of_ops, print_ops=True):
        print(f"Failed with seed {n}")

        for client in clients:
            print(f"{client.client_id}:", *client.read_state(), sep="")
        if pause_on_failure:
            input()
        return False
    return True
