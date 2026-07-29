from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from convergence_checker.convergence_checker import convergence_checker, check_for_convergence_client_client_with_time_steps
from algorithm_setup.algorithm_setup import fuguemax_setup, jupiter_setup, fugue_setup, DeviceSetup, tibot_setup, adopted_tombstone_setup, adopted_setup, adopted_tm11_setup
import random



def convergence(device_setup: DeviceSetup, tibot: bool = False):
    n = 0

    while True:
        n += 1

        if n%1000 == 0:
            print(f"{n} cases checked.")
        
        convergence_with_seed(n, device_setup, 3, 30, tibot)



def convergence_with_seed(n: int, device_setup: DeviceSetup, num_of_clients:int=3, num_of_ops:int=30, tibot: bool = False) -> bool:
        random.seed(n)

        server, clients = device_setup(num_of_clients)

        client_dict: dict[int, ClientDevice] = {}

        for client in clients:
            client_dict[client.client_id] = client
        if tibot: 
            if not check_for_convergence_client_client_with_time_steps(client_dict):  # type: ignore
                print(f"Failed with seed {n}")

                for client in clients:
                    print(f"{client.client_id}:", *client.read_state(), sep="")
                input()
                print("-"*80)
                return False
        else:
            #print("-"*80)
            if not convergence_checker(client_dict, server, num_of_ops):
                print(f"Failed with seed {n}")

                for client in clients:
                    print(f"{client.client_id}:", *client.read_state(), sep="")
                input()
                return False
        return True
