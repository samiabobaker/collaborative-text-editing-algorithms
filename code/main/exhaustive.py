import copy
from collections.abc import Callable, Iterator

from algorithm_setup.algorithm_setup import DeviceSetup
from convergence_checker.convergence_checker import deliver_everything, states_agree
from convergence_checker.exhaustive_trace import build_exhaustive_states
from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from interleaving_checker.client_trace import Character
from interleaving_checker.client_trace import ClientTrace as InterleavingClientTrace
from interleaving_checker.exhaustive_trace import build_exhaustive_interleaving_trace
from interleaving_checker.interleaving_checker import (
    forward_non_interleaving_for_client_log,
    maximally_non_interleaving_for_client_log,
)
from list_spec_checker.client_trace import ClientTrace as ListSpecClientTrace
from list_spec_checker.exhaustive_trace import build_exhaustive_trace as build_exhaustive_list_spec_trace
from list_spec_checker.list_spec_checker import (
    strong_list_specification_checker_for_client_log,
    weak_list_specification_checker_for_client_log,
)

ExhaustiveResult = tuple[bool, int]
ListSpecChecker = Callable[[dict[int, ListSpecClientTrace]], bool]
InterleavingChecker = Callable[[dict[int, InterleavingClientTrace], dict[int, Character]], bool]


def _client_dict(device_setup: DeviceSetup, num_of_clients: int) -> tuple[ServerDevice | None, dict[int, ClientDevice]]:
    server, clients = device_setup(num_of_clients)
    return server, {client.client_id: client for client in clients}


def _run(traces: Iterator[bool]) -> ExhaustiveResult:
    checked = 0
    try:
        for passed in traces:
            checked += 1
            if not passed:
                return False, checked
    except (IndexError, ValueError) as e:
        print(f"This algorithms does not satisfy the property ({type(e).__name__} while applying an operation: {e})")
        return False, checked
    return True, checked


def exhaustive_list_spec(
    checker: ListSpecChecker, device_setup: DeviceSetup, num_of_clients: int, depth: int
) -> ExhaustiveResult:
    server, clients = _client_dict(device_setup, num_of_clients)
    return _run(checker(trace) for trace in build_exhaustive_list_spec_trace(clients, server, depth))


def exhaustive_interleaving(
    checker: InterleavingChecker, device_setup: DeviceSetup, num_of_clients: int, depth: int
) -> ExhaustiveResult:
    server, clients = _client_dict(device_setup, num_of_clients)
    return _run(
        checker(trace, characters) for trace, characters in build_exhaustive_interleaving_trace(clients, server, depth)
    )


def strong_list_spec_exhaustive(device_setup: DeviceSetup, num_of_clients: int, depth: int) -> ExhaustiveResult:
    return exhaustive_list_spec(strong_list_specification_checker_for_client_log, device_setup, num_of_clients, depth)


def weak_list_spec_exhaustive(device_setup: DeviceSetup, num_of_clients: int, depth: int) -> ExhaustiveResult:
    return exhaustive_list_spec(weak_list_specification_checker_for_client_log, device_setup, num_of_clients, depth)


def forward_interleaving_exhaustive(device_setup: DeviceSetup, num_of_clients: int, depth: int) -> ExhaustiveResult:
    return exhaustive_interleaving(forward_non_interleaving_for_client_log, device_setup, num_of_clients, depth)


def interleaving_exhaustive(device_setup: DeviceSetup, num_of_clients: int, depth: int) -> ExhaustiveResult:
    return exhaustive_interleaving(maximally_non_interleaving_for_client_log, device_setup, num_of_clients, depth)


def _converges_from(server: ServerDevice | None, clients: dict[int, ClientDevice]) -> bool:
    # Convergence is a statement about where the clients settle, so the messages still in
    # flight at this node have to be delivered before the states mean anything. The search
    # continues from this node, so the delivery runs against a copy and leaves the devices
    # it was handed untouched.
    server_copy, clients_copy = copy.deepcopy((server, clients))
    deliver_everything(clients_copy, server_copy)
    return states_agree(clients_copy)


def convergence_exhaustive(device_setup: DeviceSetup, num_of_clients: int, depth: int) -> ExhaustiveResult:
    server, clients = _client_dict(device_setup, num_of_clients)
    return _run(
        _converges_from(node_server, node_clients)
        for node_server, node_clients in build_exhaustive_states(clients, server, depth)
    )


EXHAUSTIVE_CHECKS: dict[str, Callable[[DeviceSetup, int, int], ExhaustiveResult]] = {
    "convergence": convergence_exhaustive,
    "strong-list-spec": strong_list_spec_exhaustive,
    "weak-list-spec": weak_list_spec_exhaustive,
    "forward-interleaving": forward_interleaving_exhaustive,
    "interleaving": interleaving_exhaustive,
}
