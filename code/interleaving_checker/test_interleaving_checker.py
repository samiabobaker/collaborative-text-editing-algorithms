import random

from adopted.adoptedtransform import IMORTransform, SuleimanTransform
from algorithm_setup.algorithm_setup import adopted_setup, fugue_setup
from device.clientdevice import ClientDevice
from interleaving_checker.interleaving_checker import maximally_non_interleaving


# IMOR and Suleiman turn one of two concurrent inserts of the same character into a
# no-op, so a later insert can record the dropped element as its origin. The checker
# must report that as a failure instead of raising when it looks the element up.
def test_lost_origin_is_reported_for_imor():
    random.seed(21)
    server, clients = adopted_setup(IMORTransform)(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert maximally_non_interleaving(client_dict, server, 30) is False


def test_lost_origin_is_reported_for_suleiman():
    random.seed(21)
    server, clients = adopted_setup(SuleimanTransform)(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert maximally_non_interleaving(client_dict, server, 30) is False


# Algorithms that never lose elements must be unaffected by the origin check.
def test_fugue_still_passes():
    random.seed(0)
    server, clients = fugue_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert maximally_non_interleaving(client_dict, server, 30) is True


if __name__ == "__main__":
    test_lost_origin_is_reported_for_imor()
    test_lost_origin_is_reported_for_suleiman()
    test_fugue_still_passes()
    print("OK")
