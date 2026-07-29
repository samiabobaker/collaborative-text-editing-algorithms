from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from list_spec_checker.list_spec_checker import strong_list_specification_checker
from algorithm_setup.algorithm_setup import fugue_setup, fuguemax_setup, DeviceSetup, jupiter_setup, tibot_setup, adopted_tombstone_setup
import random
from typing import Sequence

def stronglistspec(device_setup: DeviceSetup, num_of_clients:int = 3,num_of_operations:int=30):
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")
        
        stronglistspec_with_seed(n, device_setup, num_of_clients,num_of_operations)



def stronglistspec_with_seed(n: int, device_setup: DeviceSetup, num_of_clients:int, num_of_operations:int=30,print_ops:bool=False) -> bool:
        random.seed(n)

        server, clients = device_setup(num_of_clients)

        client_dict: dict[int, ClientDevice] = {}

        for client in clients:
            client_dict[client.client_id] = client

        if not strong_list_specification_checker(client_dict, server,num_of_operations,print_ops):
            '''print(f"Failed with seed {n}")

            for client in clients:
                print(f"{client.client_id}:", *client.read_state(), sep="")
            input()
            print("-"*80)'''
            return False
        return True
