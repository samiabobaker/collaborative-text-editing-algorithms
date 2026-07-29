from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from interleaving_checker.interleaving_checker import maximally_non_interleaving, forward_non_interleaving
from algorithm_setup.algorithm_setup import jupiter_setup, fugue_setup, fuguemax_setup, DeviceSetup, tibot_setup, adopted_tombstone_setup
import random
from typing import Sequence

def interleaving(device_setup: DeviceSetup):
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")
        
        interleaving_with_seed(n, device_setup)

def forward_interleaving(device_setup: DeviceSetup):
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")
        
        forward_interleaving_with_seed(n, device_setup)


def forward_interleaving_with_seed(n: int, device_setup: DeviceSetup, num_of_clients:int = 3, num_of_ops: int = 30,print_ops:bool=False) -> bool:
        random.seed(n)

        server, clients = device_setup(num_of_clients)

        client_dict: dict[int, ClientDevice] = {}

        for client in clients:
            client_dict[client.client_id] = client

        if not forward_non_interleaving(client_dict, server, num_of_ops,print_ops):
            print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            input()
            print("-"*80)
            return False
        return True

def interleaving_with_seed(n: int, device_setup: DeviceSetup, num_of_clients:int = 3, num_of_ops: int = 30,print_ops:bool=False) -> bool:
        random.seed(n)

        server, clients = device_setup(num_of_clients)

        client_dict: dict[int, ClientDevice] = {}

        for client in clients:
            client_dict[client.client_id] = client

        if not maximally_non_interleaving(client_dict, server, num_of_ops,print_ops):
            print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            input()
            print("-"*80)
            return False
        return True