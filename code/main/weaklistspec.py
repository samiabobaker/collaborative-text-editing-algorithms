from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from list_spec_checker.list_spec_checker import weak_list_specification_checker
from algorithm_setup.algorithm_setup import fugue_setup, fuguemax_setup, DeviceSetup, jupiter_setup, tibot_setup, adopted_tm11_setup
import random
from typing import Sequence

def weaklistspec(device_setup: DeviceSetup):
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")
        
        weaklistspec_with_seed(n, device_setup)



def weaklistspec_with_seed(n: int, device_setup: DeviceSetup, num_of_clients:int=3, num_of_ops:int=30) -> bool:
        random.seed(n)

        server, clients = device_setup(num_of_clients)

        client_dict: dict[int, ClientDevice] = {}

        for client in clients:
            client_dict[client.client_id] = client

        if not weak_list_specification_checker(client_dict, server, num_of_ops):
            print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            input()
            print("-"*80)
            return False
        return True