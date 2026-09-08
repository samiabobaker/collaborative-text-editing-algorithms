"""Checks the implementation against the intermediate values Li and Li (2008) prints.

The trace tests in test_sdtclient.py check where the sites end up, which a wrong
implementation can still get right by luck. These check the numbers the paper states
along the way: the beta and delta of definitions 3 and 4, the state difference built by
Algorithm 8, and the latest synchronization point of Algorithm 13.
"""

from sdt.sdtclient import SDTClient
from sdt.sdtmessage import SDTDeleteOperation, SDTInsertOperation, SDTOperation
from unique_char.uniquechar import UniqueChar

SITE_1, SITE_2, SITE_3 = 0, 1, 2


def _ins(position: int, chars: str, clock: int, client_id: int = SITE_1) -> SDTInsertOperation:
    characters = [UniqueChar.get_unique_char(char) for char in chars]
    return SDTInsertOperation(client_id, {client_id: clock}, position, characters)


def _del(position: int, character: UniqueChar, clock: int, client_id: int = SITE_1) -> SDTDeleteOperation:
    return SDTDeleteOperation(client_id, {client_id: clock}, position, character)


def _describe(SD: list[SDTOperation]) -> list[str]:
    described: list[str] = []
    for entry in SD:
        if isinstance(entry, SDTInsertOperation):
            described.append(f"insert({''.join(c.char for c in entry.characters)!r},{entry.position})")
        elif isinstance(entry, SDTDeleteOperation):
            described.append(f"delete({entry.character.char!r},{entry.position})")
    return described


def test_definitions_3_and_4() -> None:
    # Section 5.4. s0 = "abcd", then o1 = insert("x", 2) giving "abxcd", o2 = insert("y", 4)
    # giving "abxcyd", o3 = delete("x", 2) giving "abcyd" and o4 = insert("z", 4) giving
    # "abcyzd". The paper states, relative to s0:
    #
    #   beta(o1) = 2, delta(o1) = 0        beta(o2) = 3, delta(o2) = 0
    #   beta(o3) = 2, delta(o3) = 1        beta(o4) = 3, delta(o4) = 1
    #
    # o3 counteracts o1, which is what makes beta(o4) 3 rather than 4: by the time o4 is
    # measured the state difference has compressed the pair away.
    client = SDTClient(SITE_1)

    x = UniqueChar.get_unique_char("x")
    o1 = SDTInsertOperation(SITE_1, {SITE_1: 1}, 2, [x])
    o2 = _ins(4, "y", clock=2)
    o3 = _del(2, x, clock=3)
    o4 = _ins(4, "z", clock=4)

    # The first operation of a sequence is already defined on s0, so its beta is its position.
    assert client.compute_beta_delta(o1, []) == (2, 0)
    assert client.compute_beta_delta(o2, client.build_SD([o1])) == (3, 0)
    assert client.compute_beta_delta(o3, client.build_SD([o1, o2])) == (2, 1)
    assert client.compute_beta_delta(o4, client.build_SD([o1, o2, o3])) == (3, 1)

    # Definition 5 step 2: the counteracting pair is gone and only "y" is left.
    assert _describe(client.build_SD([o1, o2, o3])) == ["insert('y',3)"]

    # Two inserts that share a beta are combined into one stringwise insert, ordered by
    # delta, which is what lets Algorithm 7 recognise a run.
    assert _describe(client.build_SD([o1, _ins(3, "w", clock=5)])) == ["insert('xw',2)"]


def test_section_7_3_lookahead_example() -> None:
    # Section 7.3, the example that motivates lines 5 to 18 of Algorithm 7. s0 = "abcd",
    # SQne = [delete("c", 2), insert("xy", 2)], and o = insert("z", 4) is executed on the
    # resulting state "abxyd". The paper: "There are two possibilities: the character 'z' is
    # inserted either immediately before or after the landmark character 'c'. In the first
    # possibility, beta(o) = 2 and delta(o) = 2, while in the second, beta(o) = 3 and
    # delta(o) = 0."
    #
    # Which one applies is decided by excluding both the insert and the delete and seeing
    # where "z" lands. This is the branch the paper's line 8 tests with a comparison that
    # can never hold, so it is the branch worth pinning hardest.
    client = SDTClient(SITE_1)

    c = UniqueChar.get_unique_char("c")
    # A state difference is ordered by position, with the insert before the delete at the
    # same position, so reversing it gives the paper's SQne.
    SD: list[SDTOperation] = [_ins(2, "xy", clock=1), _del(2, c, clock=2, client_id=SITE_2)]
    o = _ins(4, "z", clock=3, client_id=SITE_3)

    # First possibility. The delete causally precedes o, so Algorithm 6 decides, and section
    # 6.2 says it deliberately does not shift o. "z" joins the inserted string.
    assert client.compute_beta_delta(o, SD) == (2, 2)

    # Second possibility. The delete is concurrent with o and the recorded effects relation
    # puts it to the left, so excluding it shifts o and "z" lands after the deleted "c".
    client.store_effects_relation(SD[1], o, True)
    assert client.compute_beta_delta(o, SD) == (3, 0)


def test_figure_4_latest_synchronization_point() -> None:
    # Section 9, figure 4, the case the paper works through in full. Integrating o5 at site 1
    # transforms it against o4, and the paper states every intermediate value:
    #
    #   SVlsp = (0,0,1), the latest synchronization point is "a1bcd"
    #   the sequence between it and the definition state of o4 is [o1, o2]
    #   SD = {delete("b", 2), insert("2", 3)}
    #   beta45(o4) = 3 and beta45(o5) = 3, so the site ids break the tie
    #
    # Vector timestamps here are offset from the paper's by the four inserts site 1 needs to
    # type the initial state "abcd", which the paper starts from for free. That moves site
    # 1's component of SVlsp from 0 to 4 and leaves the state it identifies unchanged.
    from device.operations import ClientDeleteOperation, ClientInsertOperation

    lsp_vectors: list[dict[int, int]] = []
    state_differences: list[list[SDTOperation]] = []
    betas: list[tuple[int, int]] = []

    class RecordingSDTClient(SDTClient):
        def compute_lsp(self, O: SDTOperation, j: int, SQ: list[SDTOperation]) -> list[SDTOperation]:
            result = super().compute_lsp(O, j, SQ)
            lsp_vectors.append({k: min(O.vector_clock[k], SQ[j - 1].vector_clock[k]) for k in O.vector_clock})
            return result

        def build_SD(self, SQ: list[SDTOperation]) -> list[SDTOperation]:
            result = super().build_SD(SQ)
            state_differences.append(result)
            return result

        def compute_beta_delta(self, O: SDTOperation, SD: list[SDTOperation]) -> tuple[int, int]:
            result = super().compute_beta_delta(O, SD)
            betas.append(result)
            return result

    clients = [RecordingSDTClient(n) for n in range(3)]
    for client in clients:
        client.set_clients(clients)  # pyright: ignore[reportArgumentType]

    def insert(client: RecordingSDTClient, position: int, char: str) -> None:
        client.perform_local_insert(ClientInsertOperation(client.client_id, position, UniqueChar.get_unique_char(char)))

    def delete(client: RecordingSDTClient, position: int) -> None:
        client.perform_local_delete(ClientDeleteOperation(client.client_id, position, client.read_state()[position]))

    def receive(client: RecordingSDTClient, sender: RecordingSDTClient) -> None:
        while sender.client_id in client.can_receive_from():
            client.receive_from_client(sender.client_id)

    for position, char in enumerate("abcd"):
        insert(clients[SITE_1], position, char)
    for client in clients:
        for sender in clients:
            if sender is not client:
                receive(client, sender)

    insert(clients[SITE_1], 2, "2")
    delete(clients[SITE_2], 1)
    insert(clients[SITE_3], 1, "1")

    receive(clients[SITE_1], clients[SITE_2])
    receive(clients[SITE_1], clients[SITE_3])
    insert(clients[SITE_1], 3, "4")
    insert(clients[SITE_3], 3, "3")

    # Everything above is setup; only the integration of o5 at site 1 is measured.
    lsp_vectors.clear()
    state_differences.clear()
    betas.clear()
    receive(clients[SITE_1], clients[SITE_3])

    assert "".join(c.char for c in clients[SITE_1].read_state()) == "a1243cd"

    # The paper's SVlsp = (0,0,1), shifted by the four inserts that build "abcd".
    assert {SITE_1: 4, SITE_2: 0, SITE_3: 1} in lsp_vectors

    # SD = {delete("b", 2), insert("2", 3)}, ordered by position as definition 5 requires.
    assert ["delete('b',2)", "insert('2',3)"] in [_describe(SD) for SD in state_differences]

    # beta45(o4) = beta45(o5) = 3. The paper does not state their deltas, which come out
    # equal too, so Algorithm 3 falls through beta, then position, and the site ids decide.
    assert [beta for beta, _ in betas[-2:]] == [3, 3]
    assert betas[-1] == betas[-2]


if __name__ == "__main__":
    # pytest rewrites asserts to show what was compared; running the file directly does not,
    # so report the line that failed.
    import sys
    import traceback

    tests = (
        test_definitions_3_and_4,
        test_section_7_3_lookahead_example,
        test_figure_4_latest_synchronization_point,
    )
    for test in tests:
        try:
            test()
        except AssertionError:
            frame = traceback.extract_tb(sys.exc_info()[2])[-1]
            print(f"FAIL {test.__name__} (line {frame.lineno}): {frame.line}")
        else:
            print(f"ok   {test.__name__}")
