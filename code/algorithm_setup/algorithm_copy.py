import copy
from collections.abc import Sequence

from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice


def copy_clients(clients: list[ClientDevice]) -> Sequence[ClientDevice]:
    return copy.deepcopy(clients)


def copy_client_server(server: ServerDevice, clients: list[ClientDevice]) -> tuple[ServerDevice, list[ClientDevice]]:
    return copy.deepcopy((server, clients))
