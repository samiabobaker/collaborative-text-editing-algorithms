import random

from adopted.adoptedtransform import IMORTransform, SuleimanTransform
from algorithm_setup.algorithm_setup import DeviceSetup, adopted_setup, fugue_setup, yjs_setup, yjsmod_setup
from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
)
from interleaving_checker.client_trace import Character, ClientTrace, Event
from interleaving_checker.interleaving_checker import (
    build_observed_list_order,
    check_condition_1,
    check_condition_1_with_deletes,
    forward_non_interleaving_with_deletes_from_client_logs,
    maximally_non_interleaving,
    transitive_closure,
)
from unique_char.uniquechar import UniqueChar


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


def test_deleted_earlier_sibling_still_exempts_a_later_sibling():
    a = UniqueChar("a", 0)
    b = UniqueChar("b", 1)
    c = UniqueChar("c", 2)
    x = UniqueChar("x", 3)
    y = UniqueChar("y", 4)

    characters = {
        a.id: Character(a, "start", "end"),
        b.id: Character(b, a, "end"),
        c.id: Character(c, b, "end"),
        x.id: Character(x, a, "end"),
        y.id: Character(y, x, "end"),
    }
    characters[a.id].add_to_left_origin_of(b)
    characters[a.id].add_to_left_origin_of(x)

    trace = ClientTrace()
    trace.states_after_events = [[a, b, c, x, y], [a, c, x, y]]
    list_order = transitive_closure(build_observed_list_order({0: trace}))

    assert check_condition_1([a, c, x, y], characters, a, x) is False
    assert check_condition_1_with_deletes([a, c, x, y], characters, list_order, a, x) is True


def test_unresolved_sibling_order_is_conservatively_accepted():
    a = UniqueChar("a", 0)
    b = UniqueChar("b", 1)
    c = UniqueChar("c", 2)
    x = UniqueChar("x", 3)
    characters = {
        a.id: Character(a, "start", "end"),
        b.id: Character(b, a, "end"),
        c.id: Character(c, a, "end"),
        x.id: Character(x, "start", "end"),
    }
    characters[a.id].add_to_left_origin_of(b)
    characters[a.id].add_to_left_origin_of(c)

    assert check_condition_1_with_deletes([a, x, b], characters, set(), a, b) is True


def test_transitive_order_can_make_a_violation_certain():
    a = UniqueChar("a", 0)
    b = UniqueChar("b", 1)
    c = UniqueChar("c", 2)
    x = UniqueChar("x", 3)
    z = UniqueChar("z", 4)
    characters = {
        a.id: Character(a, "start", "end"),
        b.id: Character(b, a, "end"),
        c.id: Character(c, a, "end"),
        x.id: Character(x, "start", "end"),
        z.id: Character(z, "start", "end"),
    }
    characters[a.id].add_to_left_origin_of(b)
    characters[a.id].add_to_left_origin_of(c)
    trace = ClientTrace()
    trace.states_after_events = [[b, x], [x, c], [a, z, b]]
    observed_order = build_observed_list_order({0: trace})

    assert check_condition_1_with_deletes([a, z, b], characters, observed_order, a, b) is True
    assert check_condition_1_with_deletes([a, z, b], characters, transitive_closure(observed_order), a, b) is False


def replay_yjs_family_counterexample(setup: DeviceSetup, with_delete: bool):
    _, clients = setup(2)
    traces = {client.client_id: ClientTrace() for client in clients}
    characters: dict[int, Character] = {}
    l = UniqueChar("l", 1)
    r = UniqueChar("r", 5)
    s = UniqueChar("s", 6)
    v = UniqueChar("v", 8)

    operations: list[ClientOperation] = [
        ClientInsertOperation(0, 0, l),
        ClientReceiveFromClientOperation(1, 0),
    ]
    if with_delete:
        operations.append(ClientDeleteOperation(0, 0, l))
    operations.extend(
        [
            ClientInsertOperation(0, 0, r),
            ClientInsertOperation(1, 0, s),
        ]
    )
    if with_delete:
        operations.append(ClientReceiveFromClientOperation(1, 0))
    operations.extend(
        [
            ClientInsertOperation(1, 1, v),
            ClientReceiveFromClientOperation(0, 1),
            ClientReceiveFromClientOperation(0, 1),
        ]
    )

    for operation in operations:
        client = clients[operation.client_id]
        seen = client.perform_operation(operation)
        state = list(client.read_state())
        if isinstance(operation, ClientInsertOperation):
            left_origin = state[operation.position - 1] if operation.position > 0 else "start"
            right_origin = state[operation.position + 1] if operation.position < len(state) - 1 else "end"
            if left_origin != "start":
                characters[left_origin.id].add_to_left_origin_of(operation.character)
            if right_origin != "end":
                characters[right_origin.id].add_to_right_origin_of(operation.character)
            characters[operation.character.id] = Character(operation.character, left_origin, right_origin)
        if seen:
            performed_locally = isinstance(operation, (ClientInsertOperation, ClientDeleteOperation))
            traces[operation.client_id].add_event(Event(seen, performed_locally), state)

    client_0_state_when_v_arrives = list(clients[0].read_state())

    progress = True
    while progress:
        progress = False
        for client in clients:
            senders = client.can_receive_from()
            if not senders:
                continue
            progress = True
            seen = client.perform_operation(ClientReceiveFromClientOperation(client.client_id, min(senders)))
            if seen:
                traces[client.client_id].add_event(Event(seen, False), list(client.read_state()))

    return clients, traces, characters, (l, r, s, v), client_0_state_when_v_arrives


def test_yjs_family_delete_trace_really_interleaves_consecutive_insertions():
    for setup in (yjs_setup, yjsmod_setup):
        clients, traces, characters, (_, r, s, v), state_when_v_arrives = replay_yjs_family_counterexample(
            setup, with_delete=True
        )

        assert state_when_v_arrives == [s, r, v]
        assert all(client.read_state() == [s, r, v] for client in clients)
        assert forward_non_interleaving_with_deletes_from_client_logs(traces, characters) is False


def test_same_yjs_family_trace_without_delete_does_not_interleave():
    for setup in (yjs_setup, yjsmod_setup):
        clients, traces, characters, (l, r, s, v), state_when_v_arrives = replay_yjs_family_counterexample(
            setup, with_delete=False
        )

        assert state_when_v_arrives == [r, s, v, l]
        assert all(client.read_state() == [r, s, v, l] for client in clients)
        assert forward_non_interleaving_with_deletes_from_client_logs(traces, characters) is True


if __name__ == "__main__":
    test_lost_origin_is_reported_for_imor()
    test_lost_origin_is_reported_for_suleiman()
    test_fugue_still_passes()
    test_deleted_earlier_sibling_still_exempts_a_later_sibling()
    test_unresolved_sibling_order_is_conservatively_accepted()
    test_transitive_order_can_make_a_violation_certain()
    test_yjs_family_delete_trace_really_interleaves_consecutive_insertions()
    test_same_yjs_family_trace_without_delete_does_not_interleave()
    print("OK")
