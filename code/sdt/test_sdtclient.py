from device.operations import ClientDeleteOperation, ClientInsertOperation
from sdt.sdtclient import SDTClient
from unique_char.uniquechar import UniqueChar

# The worked examples from Li and Li (2008), "An Approach to Ensuring Consistency in
# Peer-to-Peer Real-Time Group Editors": figure 1 in section 3, figure 2 in section 5.4 and
# figure 4 in section 9.
#
# Sites are numbered from 1 in the paper and clients from 0 here, so site n is client n-1.
# The tie-break in precedes compares client ids, which keeps the relative order the paper's
# site ids give.
SITE_1, SITE_2, SITE_3 = 0, 1, 2


def _setup(initial: str, num_of_clients: int = 3) -> list[SDTClient]:
    # The paper's examples all start from a state every site already shares. Site 1 types it
    # and everybody merges that, so it precedes all the operations under test.
    clients = [SDTClient(n) for n in range(num_of_clients)]
    for client in clients:
        client.set_clients(clients)

    for position, char in enumerate(initial):
        _insert(clients[SITE_1], position, char)
    _drain(clients)

    return clients


def _insert(client: SDTClient, position: int, char: str) -> None:
    client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))


def _delete(client: SDTClient, position: int) -> None:
    client.perform_local_delete(ClientDeleteOperation(client.client_id, position, client.read_state()[position]))


def _receive_all_from(client: SDTClient, sender: SDTClient) -> None:
    while sender.client_id in client.can_receive_from():
        client.receive_from_client(sender.client_id)


def _drain(clients: list[SDTClient]) -> None:
    progressed = True
    while progressed:
        progressed = False
        for client in clients:
            for sender_id in client.can_receive_from():
                client.receive_from_client(sender_id)
                progressed = True


def _word(client: SDTClient) -> str:
    return "".join(character.char for character in client.read_state())


def test_figure_1_diverging_scenario_converges_under_sdt() -> None:
    # Section 3. Sites 1, 2 and 3 start from "abc" and concurrently generate
    # o1 = ins("1", 2), o2 = ins("2", 1) and o3 = del("b", 1). Under the transformation
    # functions of Ellis and Gibbs (1989) site 2 ends at "a21c" and site 3 at "a12c".
    #
    # Section 5.4 works this out for SDT: the latest synchronization point of o1 and o2 is
    # the initial state, where beta(o1) = 2 and beta(o2) = 1, so o2 precedes o1 whatever the
    # site ids say and site 3 gets ins("1", 2) rather than ins("1", 1).
    clients = _setup("abc")

    _insert(clients[SITE_1], 2, "1")
    _insert(clients[SITE_2], 1, "2")
    _delete(clients[SITE_3], 1)

    assert _word(clients[SITE_1]) == "ab1c"
    assert _word(clients[SITE_2]) == "a2bc"
    assert _word(clients[SITE_3]) == "ac"

    # Site 2 takes o3 then o1, and site 3 takes o2 then o1, the orders the paper walks.
    _receive_all_from(clients[SITE_2], clients[SITE_3])
    assert _word(clients[SITE_2]) == "a2c"
    _receive_all_from(clients[SITE_2], clients[SITE_1])

    _receive_all_from(clients[SITE_3], clients[SITE_2])
    assert _word(clients[SITE_3]) == "a2c"
    _receive_all_from(clients[SITE_3], clients[SITE_1])

    _drain(clients)

    assert _word(clients[SITE_2]) == "a21c"
    assert _word(clients[SITE_3]) == "a21c"
    assert _word(clients[SITE_1]) == "a21c"


def test_figure_2_dopt_puzzle() -> None:
    # Section 5.4, figure 2. Two sites start from "abc". Site 1 generates o1 = ins("x", 1),
    # site 2 generates o2 = ins("y", 1) and then o3 = ins("z", 2), so o3 is causally after
    # o2 but concurrent with o1, which is the dOPT puzzle.
    #
    # At site 2, o1 ties with o2 on both beta and position so the site ids break it and o1
    # precedes o2; against o3 the betas tie and the positions do not. Site 2 reaches
    # "axyzbc" and site 1 has to agree.
    clients = _setup("abc", num_of_clients=2)

    _insert(clients[SITE_1], 1, "x")
    _insert(clients[SITE_2], 1, "y")
    _insert(clients[SITE_2], 2, "z")

    assert _word(clients[SITE_1]) == "axbc"
    assert _word(clients[SITE_2]) == "ayzbc"

    _drain(clients)

    assert _word(clients[SITE_1]) == "axyzbc"
    assert _word(clients[SITE_2]) == "axyzbc"


def test_figure_4_example() -> None:
    # Section 9, figure 4. Three sites start from "abcd" and concurrently generate
    # o1 = ins("2", 2), o2 = del("b", 1) and o3 = ins("1", 1). Site 1 executes o2 and o3,
    # then generates o4 = ins("4", 3); site 3 generates o5 = ins("3", 3) after o3, so o5 is
    # causally after o3 and concurrent with o1, o2 and o4.
    #
    # Integrating o5 at site 1 exercises the whole algorithm: the log is transposed so that
    # o3 comes first, a state difference {del("b", 2), ins("2", 3)} is built between the
    # latest synchronization point "a1bcd" and the definition state of o4, and beta45(o4)
    # and beta45(o5) both come out as 3, so the site ids decide. Every site reaches
    # "a1243cd".
    clients = _setup("abcd")

    _insert(clients[SITE_1], 2, "2")
    _delete(clients[SITE_2], 1)
    _insert(clients[SITE_3], 1, "1")

    assert _word(clients[SITE_1]) == "ab2cd"
    assert _word(clients[SITE_2]) == "acd"
    assert _word(clients[SITE_3]) == "a1bcd"

    # Site 1 takes o2 and then o3, and only then generates o4.
    _receive_all_from(clients[SITE_1], clients[SITE_2])
    assert _word(clients[SITE_1]) == "a2cd"
    _receive_all_from(clients[SITE_1], clients[SITE_3])
    assert _word(clients[SITE_1]) == "a12cd"

    _insert(clients[SITE_1], 3, "4")
    assert _word(clients[SITE_1]) == "a124cd"

    # Site 3 generates o5 on the state it reached with o3 alone.
    _insert(clients[SITE_3], 3, "3")
    assert _word(clients[SITE_3]) == "a1b3cd"

    # o5 reaches site 1, which is the case the paper works through.
    _receive_all_from(clients[SITE_1], clients[SITE_3])
    assert _word(clients[SITE_1]) == "a1243cd"

    # Site 2 sees o1, o3, o5 and then o4; site 3 sees o2, o1 and then o4.
    _drain(clients)

    assert _word(clients[SITE_2]) == "a1243cd"
    assert _word(clients[SITE_3]) == "a1243cd"


def test_oster_counterexample_diverges() -> None:
    # Oster et al. (2005), "Proving correctness of transformation functions in collaborative
    # editing systems", figure 20: the counter-example that disproves SDT's claim to satisfy
    # TP2, found with the SPIKE theorem prover and confirmed against the authors' own
    # implementation. SDT does not converge, and this pins the shape of the failure so that
    # a change to the implementation that quietly repaired it would be noticed.
    #
    # Four sites start from "abcd". Site 4 deletes "c" and site 3 concurrently inserts "z"
    # before it. Sites 1 and 2 see the delete only, site 1 then inserts "y", and finally
    # site 4 inserts "x" while site 2 deletes "y". Sites 1 and 2 both reach "abzd" and then
    # transform the same insert of "x" against the same operation, but site 1 breaks the tie
    # on position and site 2 breaks it on site id, so they end at "abxzd" and "abzxd".
    clients = _setup("abcd", num_of_clients=4)
    site_4 = 3

    _delete(clients[site_4], 2)
    _insert(clients[SITE_3], 2, "z")

    # Sites 1 and 2 take the delete only, so they reach "abd" without having seen the insert.
    _receive_all_from(clients[SITE_1], clients[site_4])
    _receive_all_from(clients[SITE_2], clients[site_4])
    assert _word(clients[SITE_1]) == "abd"
    assert _word(clients[SITE_2]) == "abd"

    _insert(clients[SITE_1], 2, "y")
    _receive_all_from(clients[SITE_2], clients[SITE_1])
    _receive_all_from(clients[site_4], clients[SITE_1])
    assert _word(clients[site_4]) == "abyd"

    _insert(clients[site_4], 2, "x")
    _delete(clients[SITE_2], 2)
    _receive_all_from(clients[SITE_1], clients[SITE_3])

    assert _word(clients[SITE_1]) == "abyzd"
    assert _word(clients[SITE_2]) == "abd"
    assert _word(clients[site_4]) == "abxyd"

    _drain(clients)

    assert _word(clients[SITE_1]) == "abxzd"
    assert _word(clients[SITE_2]) == "abzxd"


if __name__ == "__main__":
    # pytest rewrites asserts to show what was compared; running the file directly does not,
    # so report the line that failed.
    import sys
    import traceback

    tests = (
        test_figure_1_diverging_scenario_converges_under_sdt,
        test_figure_2_dopt_puzzle,
        test_figure_4_example,
        test_oster_counterexample_diverges,
    )
    for test in tests:
        try:
            test()
        except AssertionError:
            frame = traceback.extract_tb(sys.exc_info()[2])[-1]
            print(f"FAIL {test.__name__} (line {frame.lineno}): {frame.line}")
        else:
            print(f"ok   {test.__name__}")
