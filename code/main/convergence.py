import random

from algorithm_setup.algorithm_setup import DeviceSetup
from convergence_checker.convergence_checker import (
    check_for_convergence_client_client_with_time_steps,
    convergence_checker,
)
from device.clientdevice import ClientDevice, TimeSteppedClient


def convergence(device_setup: DeviceSetup):
    n = 0

    while True:
        n += 1

        if n % 1000 == 0:
            print(f"{n} cases checked.")

        convergence_with_seed(n, device_setup, 3, 50)


def convergence_with_seed(
    n: int, device_setup: DeviceSetup, num_of_clients: int = 3, num_of_ops: int = 30, pause_on_failure: bool = True
) -> bool:
    random.seed(n)

    server, clients = device_setup(num_of_clients)

    client_dict: dict[int, ClientDevice] = {}

    for client in clients:
        client_dict[client.client_id] = client
    if any(isinstance(client, TimeSteppedClient) for client in clients):
        if not check_for_convergence_client_client_with_time_steps(client_dict):  # type: ignore
            print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            if pause_on_failure:
                input()
            print("-" * 80)
            return False
    else:
        # print("-"*80)
        if not convergence_checker(client_dict, server, num_of_ops):
            print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            if pause_on_failure:
                input()
            return False
    return True
