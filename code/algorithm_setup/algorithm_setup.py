from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer
from fugue.fugueclient import FugueClient
from fuguemax.fuguemaxclient import FugueMaxClient
from tibot.tibotclient import TIBOTClient
from adoptedtombstone.adoptedtombstoneclient import AdOPTedTombstoneClient
from adopted.adoptedclient import AdOPTedClient
from adopted.adoptedtransform import EllisTransform, ResselTransform, IMORTransform, TM11Transform
from adoptedtm11.adoptedtm11client import AdOPTedTM11Client
from yjs.yjsclient import YjsClient
from yjsmod.yjsmodclient import YjsModClient
from sync9.sync9client import Sync9Client
from rga.rgaclient import RGAClient
from got.gotclient import GOTClient
from dopt.doptclient import dOPTClient
from soct2.soct2client import SOCT2Client
from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from typing import Sequence, Callable

Devices = tuple[ServerDevice | None, Sequence[ClientDevice]]
DeviceSetup = Callable[[int], Devices]


def jupiter_setup(num_of_clients: int) -> Devices:
    clients: list[JupiterClient] = []
    for n in range(num_of_clients):
        client = JupiterClient(n)
        clients.append(client)

    server = JupiterServer(clients)

    for client in clients:
        client.set_server(server)
    
    return server, clients

def fugue_setup(num_of_clients: int) -> Devices:
    clients: list[FugueClient] = []
    for n in range(num_of_clients):
        client = FugueClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def fuguemax_setup(num_of_clients: int) -> Devices:
    clients: list[FugueMaxClient] = []
    for n in range(num_of_clients):
        client = FugueMaxClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def rga_setup(num_of_clients: int) -> Devices:
    clients: list[RGAClient] = []
    for n in range(num_of_clients):
        client = RGAClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def got_setup(num_of_clients: int) -> Devices:
    clients: list[GOTClient] = []
    for n in range(num_of_clients):
        client = GOTClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients


def yjs_setup(num_of_clients: int) -> Devices:
    clients: list[YjsClient] = []
    for n in range(num_of_clients):
        client = YjsClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def yjsmod_setup(num_of_clients: int) -> Devices:
    clients: list[YjsModClient] = []
    for n in range(num_of_clients):
        client = YjsModClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def dOPT_setup(num_of_clients: int) -> Devices:
    clients: list[dOPTClient] = []
    for n in range(num_of_clients):
        client = dOPTClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def SOCT2_setup(num_of_clients: int) -> Devices:
    clients: list[SOCT2Client] = []
    for n in range(num_of_clients):
        client = SOCT2Client(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients


def sync9_setup(num_of_clients: int) -> Devices:
    clients: list[Sync9Client] = []
    for n in range(num_of_clients):
        client = Sync9Client(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients


def adopted_setup(transformation) -> Devices:
    def setup(num_of_clients: int):
        clients: list[AdOPTedClient] = []
        for n in range(num_of_clients):
            client = AdOPTedClient(n, transformation())
            clients.append(client)

        for client in clients:
            client.set_clients(clients)
        
        return None, clients
    return setup

def adopted_tombstone_setup(num_of_clients: int) -> Devices:
    clients: list[AdOPTedTombstoneClient] = []
    for n in range(num_of_clients):
        client = AdOPTedTombstoneClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients


def adopted_tm11_setup(num_of_clients: int) -> Devices:
    clients: list[AdOPTedTM11Client] = []
    for n in range(num_of_clients):
        client = AdOPTedTM11Client(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients

def tibot_setup(num_of_clients: int) -> Devices:
    clients: list[TIBOTClient] = []
    for n in range(num_of_clients):
        client = TIBOTClient(n)
        clients.append(client)

    for client in clients:
        client.set_clients(clients)
    
    return None, clients