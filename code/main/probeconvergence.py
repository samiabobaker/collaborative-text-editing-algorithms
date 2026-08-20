from algorithm_setup.algorithm_setup import DeviceSetup
from probe_convergence_checker.probe_convergence_checker import probe_convergence_checker


def probe_convergence(device_setup: DeviceSetup):
    n = 0

    while True:
        n += 1

        if n % 1000 == 0:
            print(f"{n} cases checked.")

        probe_convergence_with_seed(n, device_setup, 3, 30)


def probe_convergence_with_seed(
    n: int, device_setup: DeviceSetup, num_of_clients: int = 3, num_of_ops: int = 30, pause_on_failure: bool = True
) -> bool:
    # The checker seeds the generator itself, once per world it builds, so unlike the other
    # drivers this one does not seed and does not hold on to the devices.
    if not probe_convergence_checker(n, device_setup, num_of_clients, num_of_ops):
        print(f"Failed with seed {n}")
        if pause_on_failure:
            input()
        print("-" * 80)
        return False
    return True
