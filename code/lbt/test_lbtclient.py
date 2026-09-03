from device.operations import ClientDeleteOperation, ClientInsertOperation
from lbt.lbtclient import LBTClient
from unique_char.uniquechar import UniqueChar

# The worked example from Li and Li (2005), "A Landmark-Based Transformation Approach to
# Concurrency Control in Group Editors", figure 2 and section 6.
#
# Four sites start from state "1". Site 1 generates o1 = ins("b", 1), site 2 concurrently
# generates o2 = del(0), and site 4 concurrently generates o3 = ins("a", 0). Site 3 sees
# o3 and then generates o4 = ins("c", 1), so o3 -> o4 and o4 is concurrent with o1 and o2.
# Every site is expected to converge on "acb".
#
# The paper fixes an execution order at two of the sites and walks through the states they
# pass through, so those are checked as well as the final state. Site 1 executes
# o1, o3, o4, o2 and site 4 executes o3, o2, o4, o1.
#
# Sites are numbered from 1 in the paper and clients from 0 here, so site n is client n-1.
# The tie-break in get_effect_relation_it compares client ids, so this keeps the relative
# order the paper's site ids give.
SITE_1, SITE_2, SITE_3, SITE_4 = 0, 1, 2, 3


def _setup() -> list[LBTClient]:
    # The paper's initial state s0 = "1", reached by site 1 inserting it and everybody
    # merging that insert, so all four sites share it and it precedes o1 to o4.
    clients = [LBTClient(n) for n in range(4)]
    for client in clients:
        client.set_clients(clients)

    _insert(clients[SITE_1], 0, "1")
    for client in clients:
        if client.client_id != SITE_1:
            client.receive_from_client(SITE_1)

    return clients


def _insert(client: LBTClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def _delete(client: LBTClient, position: int) -> None:
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, client.read_state()[position]))


def _drain(clients: list[LBTClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def _word(client: LBTClient) -> str:
    return "".join(character.char for character in client.read_state())


def _generate_figure_2_operations(clients: list[LBTClient]) -> None:
    # o1 at site 1, o2 at site 2 and o3 at site 4 are all generated from "1", so they are
    # pairwise concurrent. o4 is generated at site 3 after o3 has been merged there.
    _insert(clients[SITE_1], 1, "b")  # o1 = ins("b", 1)
    _delete(clients[SITE_2], 0)  # o2 = del(0)
    _insert(clients[SITE_4], 0, "a")  # o3 = ins("a", 0)

    clients[SITE_3].receive_from_client(SITE_4)
    _insert(clients[SITE_3], 1, "c")  # o4 = ins("c", 1), so o3 -> o4


# Section 6, site 1. The history buffer is transposed into sqh = [o3] and sqc = [o1], and
# o4 is integrated by ITSQ against sqc alone. Then o2 arrives concurrent with everything
# in the history buffer and is transformed into del(2).
def test_figure_2_site_1_trace():
    clients = _setup()
    _generate_figure_2_operations(clients)
    site_1 = clients[SITE_1]

    assert _word(site_1) == "1b"

    site_1.receive_from_client(SITE_4)  # o3
    assert _word(site_1) == "a1b"

    site_1.receive_from_client(SITE_3)  # o4
    assert _word(site_1) == "ac1b"

    site_1.receive_from_client(SITE_2)  # o2
    assert _word(site_1) == "acb"


# Section 6, site 4. When o1 arrives the whole history buffer is concurrent with it, so
# BuildETSOS rewrites [o3, o2, o4] into the ETSOS [o3, ins("c", 1), del(2)], which
# TransposeInsDel then splits into sqi = [o3, ins("c", 1)] and sqd = [del(2)].
def test_figure_2_site_4_trace():
    clients = _setup()
    _generate_figure_2_operations(clients)
    site_4 = clients[SITE_4]

    assert _word(site_4) == "a1"

    site_4.receive_from_client(SITE_2)  # o2
    assert _word(site_4) == "a"

    site_4.receive_from_client(SITE_3)  # o4
    assert _word(site_4) == "ac"

    site_4.receive_from_client(SITE_1)  # o1
    assert _word(site_4) == "acb"


# The property the example is there to show: every site ends on "acb", whatever order the
# operations reach it in.
def test_figure_2_all_sites_converge():
    clients = _setup()
    _generate_figure_2_operations(clients)

    _drain(clients)

    assert [_word(client) for client in clients] == ["acb", "acb", "acb", "acb"]


if __name__ == "__main__":
    # pytest rewrites asserts to show what was compared; running the file directly does not,
    # so report the line that failed.
    import sys
    import traceback

    for test in (test_figure_2_site_1_trace, test_figure_2_site_4_trace, test_figure_2_all_sites_converge):
        try:
            test()
        except AssertionError:
            frame = traceback.extract_tb(sys.exc_info()[2])[-1]
            print(f"FAIL {test.__name__} (line {frame.lineno}): {frame.line}")
        else:
            print(f"ok   {test.__name__}")
