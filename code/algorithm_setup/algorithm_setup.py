from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from abt.abtclient import ABTClient
from adopted.adoptedclient import AdOPTedClient
from adoptedrandolph.adoptedrandolphclient import AdOPTedRandolphClient
from adoptedtm11.adoptedtm11client import AdOPTedTM11Client
from adoptedtombstone.adoptedtombstoneclient import AdOPTedTombstoneClient
from collabs.collabsclient import CollabsClient
from cot.cotclient import COTClient
from cot.cotserver import COTServer
from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from diffsync.diffsyncclient import DiffsyncClient
from dopt.doptclient import dOPTClient
from easysync.easysyncclient import EasySyncClient
from easysync.easysyncserver import EasySyncServer
from fugue.fugueclient import FugueClient
from fuguemax.fuguemaxclient import FugueMaxClient
from got.gotclient import GOTClient
from gottombstone.gottombstoneclient import GOTTombstoneClient
from jupiter.jupiterclient import JupiterClient
from jupiter.jupiterserver import JupiterServer
from logoot.logootclient import LogootClient
from logootsplit.logootsplitclient import LogootSplitClient
from loro.loroclient import LoroClient
from lseq.lseqclient import LSEQClient
from markandretrace.markandretraceclient import MarkAndRetraceClient
from pot.potclient import POTClient
from pot.potserver import POTServer
from pps.ppsclient import PPSClient
from rga.rgaclient import RGAClient
from sharedb.sharedbclient import ShareDBClient
from sharedb.sharedbserver import ShareDBServer
from soct2.soct2client import SOCT2Client
from soct3.soct3client import SOCT3Client
from soct3.soct3server import SOCT3Server
from soct4.soct4client import SOCT4Client
from soct4.soct4server import SOCT4Server
from sync7.sync7client import Sync7Client
from sync9.sync9client import Sync9Client
from tibot.tibotclient import TIBOTClient
from tibot2.tibot2client import TIBOT2Client
from twc.twcclient import TWCClient
from twc.twcserver import TWCServer
from woot.wootclient import WOOTClient
from wooto.wootoclient import WOOTOClient
from yjs.yjsclient import YjsClient
from yjsmod.yjsmodclient import YjsModClient

Devices = tuple[ServerDevice | None, Sequence[ClientDevice]]
DeviceSetup = Callable[[int], Devices]


# Neither hook is on the ClientDevice ABC, so they are described structurally here.
# The parameters are Any because each client narrows them to its own class,
# e.g. TIBOT2Client.set_clients(self, clients: list[TIBOT2Client]).
class PeerClient(Protocol):
    # A client that is handed the peer list at setup time.
    def set_clients(self, clients: Any) -> None: ...


class ServedClient(Protocol):
    # A client that is handed the server at setup time.
    def set_server(self, server: Any) -> None: ...


def make_setup(
    client_class: Callable[[int], ClientDevice],
    server_class: Callable[[Any], ServerDevice] | None = None,
    *,
    peer_to_peer: bool = True,
) -> DeviceSetup:
    # Builds the DeviceSetup for one algorithm.
    # peer_to_peer: every client is told about its peers; the algorithms whose clients
    # never need the peer list pass False.
    # server_class: a server is built from the clients, and every client is told about it.
    def setup(num_of_clients: int) -> Devices:
        clients = [client_class(n) for n in range(num_of_clients)]

        if peer_to_peer:
            for client in clients:
                cast(PeerClient, client).set_clients(clients)

        if server_class is None:
            return None, clients

        server = server_class(clients)
        for client in clients:
            cast(ServedClient, client).set_server(server)

        return server, clients

    return setup


# Peer to peer
SOCT2_setup = make_setup(SOCT2Client)
abt_setup = make_setup(ABTClient)
adopted_randolph_setup = make_setup(AdOPTedRandolphClient)
adopted_tm11_setup = make_setup(AdOPTedTM11Client)
adopted_tombstone_setup = make_setup(AdOPTedTombstoneClient)
collabs_setup = make_setup(CollabsClient)
diffsync_setup = make_setup(DiffsyncClient)
dOPT_setup = make_setup(dOPTClient)
fugue_setup = make_setup(FugueClient)
fuguemax_setup = make_setup(FugueMaxClient)
got_setup = make_setup(GOTClient)
got_tombstone_setup = make_setup(GOTTombstoneClient)
logoot_setup = make_setup(LogootClient)
logoot_split_setup = make_setup(LogootSplitClient)
loro_setup = make_setup(LoroClient)
lseq_setup = make_setup(LSEQClient)
markandretrace_setup = make_setup(MarkAndRetraceClient)
pps_setup = make_setup(PPSClient)
rga_setup = make_setup(RGAClient)
sync7_setup = make_setup(Sync7Client)
sync9_setup = make_setup(Sync9Client)
tibot_setup = make_setup(TIBOTClient)
tibot2_setup = make_setup(TIBOT2Client)
woot_setup = make_setup(WOOTClient)
wooto_setup = make_setup(WOOTOClient)
yjs_setup = make_setup(YjsClient)
yjsmod_setup = make_setup(YjsModClient)

# Client server
cot_setup = make_setup(COTClient, COTServer)
easysync_setup = make_setup(EasySyncClient, EasySyncServer, peer_to_peer=False)
jupiter_setup = make_setup(JupiterClient, JupiterServer, peer_to_peer=False)
pot_setup = make_setup(POTClient, POTServer)
sharedb_setup = make_setup(ShareDBClient, ShareDBServer, peer_to_peer=False)
soct3_setup = make_setup(SOCT3Client, SOCT3Server)
soct4_setup = make_setup(SOCT4Client, SOCT4Server)
twc_setup = make_setup(TWCClient, TWCServer, peer_to_peer=False)


# AdOPTed is parameterised by its transformation function, so it takes one more step.
def adopted_setup(transformation: Callable[[], Any]) -> DeviceSetup:
    return make_setup(lambda n: AdOPTedClient(n, transformation()))
