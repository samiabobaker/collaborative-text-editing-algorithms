import random
from itertools import permutations

from adopted.adoptedtransform import IMORTransform, SuleimanTransform
from algorithm_setup.algorithm_setup import DeviceSetup, adopted_setup, fugue_setup, woot_setup, yjs_setup, yjsmod_setup
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
    forward_non_interleaving_for_client_log,
    forward_non_interleaving_with_deletes_from_client_logs,
    has_common_forward_order,
    maximally_non_interleaving,
    transitive_closure,
)
from interleaving_checker.random_trace import build_random_trace
from list_spec_checker.client_trace import ClientTrace as ListClientTrace
from list_spec_checker.client_trace import Event as ListEvent
from list_spec_checker.list_spec_checker import strong_list_specification_checker_for_client_log
from unique_char.uniquechar import UniqueChar


def assert_strong_list_precondition(logs: dict[int, ClientTrace]) -> None:
    list_logs = {i: ListClientTrace() for i in logs}
    for client_id, log in logs.items():
        for event, state in zip(log.events_seen, log.states_after_events, strict=True):
            list_logs[client_id].add_event(ListEvent(event.operation, event.performed_locally), state)
    assert strong_list_specification_checker_for_client_log(list_logs)


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


def test_delete_checker_preserves_insert_only_verdicts():
    saw_failure = False
    for setup in (yjs_setup, woot_setup):
        for seed in range(30):
            random.seed(seed)
            server, clients = setup(3)
            logs, characters = build_random_trace({client.client_id: client for client in clients}, server, 30)
            assert all(
                not isinstance(operation, ClientDeleteOperation)
                for log in logs.values()
                for event in log.events_seen
                for operation in event.operation
            )
            expected = forward_non_interleaving_for_client_log(logs, characters)
            assert forward_non_interleaving_with_deletes_from_client_logs(logs, characters) == expected
            saw_failure |= not expected
    assert saw_failure


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
    assert check_condition_1_with_deletes([a, c, x, y], characters, list_order, {a, b, c, x, y}, a, x) is True
    assert forward_non_interleaving_with_deletes_from_client_logs({0: trace}, characters) is True


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

    assert check_condition_1_with_deletes([a, x, b], characters, set(), {a, b, c, x}, a, b) is True


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

    observed_characters = {a, b, c, x, z}
    assert check_condition_1_with_deletes([a, z, b], characters, observed_order, observed_characters, a, b) is True
    assert (
        check_condition_1_with_deletes(
            [a, z, b], characters, transitive_closure(observed_order), observed_characters, a, b
        )
        is False
    )


def test_future_sibling_does_not_hide_an_earlier_violation():
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

    trace = ClientTrace()
    trace.states_after_events = [[a, x, b], [a, c, x, b]]

    assert forward_non_interleaving_with_deletes_from_client_logs({0: trace}, characters) is False


def test_sibling_observed_by_another_client_does_not_rewrite_a_state():
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

    first_client = ClientTrace()
    first_client.states_after_events = [[a, x, b]]
    second_client = ClientTrace()
    second_client.states_after_events = [[a, c, b]]

    assert (
        forward_non_interleaving_with_deletes_from_client_logs({0: first_client, 1: second_client}, characters) is False
    )


def test_inserted_and_deleted_in_one_event_still_counts_as_observed():
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

    first_client = ClientTrace()
    first_client.add_event(
        Event(
            [ClientInsertOperation(1, 1, c), ClientDeleteOperation(1, 1, c)],
            performed_locally=False,
        ),
        [a, x, b],
    )
    second_client = ClientTrace()
    second_client.states_after_events = [[a, c, b]]

    assert (
        forward_non_interleaving_with_deletes_from_client_logs({0: first_client, 1: second_client}, characters) is True
    )


def test_deleted_sibling_exemptions_need_one_common_order():
    a, b, c, x = [UniqueChar(char, index) for index, char in enumerate("abcx")]
    characters = {
        a.id: Character(a, "start", "end"),
        b.id: Character(b, a, "end"),
        c.id: Character(c, a, "end"),
        x.id: Character(x, "start", "end"),
    }
    characters[a.id].left_origin_of = [b, c]
    insert_a = ClientInsertOperation(0, 0, a)
    insert_b = ClientInsertOperation(0, 1, b)
    insert_c = ClientInsertOperation(1, 1, c)
    insert_x = ClientInsertOperation(2, 0, x)
    delete_b = ClientDeleteOperation(0, 1, b)
    delete_c = ClientDeleteOperation(1, 1, c)

    # Sources create and delete b/c. Two observers retain opposite siblings and
    # receive the other sibling's insert/delete in one event, so b/c never co-occur.
    for conflicting in (False, True):
        logs = {i: ClientTrace() for i in range(5)}

        def add(
            client_id: int,
            operations: list[ClientInsertOperation | ClientDeleteOperation],
            local: bool,
            state: list[UniqueChar],
            client_logs: dict[int, ClientTrace] = logs,
        ) -> None:
            client_logs[client_id].add_event(Event(operations, local), state)

        add(0, [insert_a], True, [a])
        add(0, [insert_b], True, [a, b])
        add(0, [delete_b], True, [a])
        add(1, [insert_a], False, [a])
        add(1, [insert_c], True, [a, c])
        add(1, [delete_c], True, [a])
        add(2, [insert_x], True, [x])
        add(3, [insert_a], False, [a])
        add(3, [insert_b], False, [a, b])
        add(3, [insert_c, delete_c], False, [a, b])
        add(3, [insert_x], False, [a, x, b])
        add(4, [insert_a], False, [a])
        add(4, [insert_c], False, [a, c])
        add(4, [insert_b, delete_b], False, [a, c])
        add(4, [insert_x], False, [a, x, c] if conflicting else [a, c, x])
        add(0, [insert_c, delete_c, insert_x], False, [a, x])
        add(1, [insert_b, delete_b, insert_x], False, [a, x])
        add(2, [insert_a, insert_b, delete_b, insert_c, delete_c], False, [a, x])
        add(3, [delete_b], False, [a, x])
        add(4, [delete_c], False, [a, x])

        assert_strong_list_precondition(logs)

        # axb requires c<b; axc requires b<c. The old per-pair checks accept both.
        order = transitive_closure(build_observed_list_order(logs))
        assert check_condition_1_with_deletes([a, x, b], characters, order, {a, b, c, x}, a, b)
        if conflicting:
            assert check_condition_1_with_deletes([a, x, c], characters, order, {a, b, c, x}, a, c)
        assert forward_non_interleaving_with_deletes_from_client_logs(logs, characters) is not conflicting


def test_common_order_keeps_sibling_alternatives_and_combines_requirements():
    a, b, c = [UniqueChar(char, index) for index, char in enumerate("abc")]
    # Choosing b<a would create a cycle, but c<a<b satisfies both requirements.
    assert has_common_forward_order(set(), {a: {frozenset({b, c})}, b: {frozenset({a})}})
    # Requirements from separate states are conjunctive: both b<a and c<a.
    assert not has_common_forward_order(set(), {a: {frozenset({b}), frozenset({c})}, b: {frozenset({a})}})
    assert not has_common_forward_order(set(), {a: {frozenset()}})


def test_common_order_matches_exhaustive_total_orders():
    rng = random.Random(36)
    for size in range(1, 6):
        elements = [UniqueChar(str(index), index) for index in range(size)]
        for _ in range(100):
            order = {(a, b) for a in elements for b in elements if a != b and rng.random() < 0.15}
            requirements = {
                element: {
                    frozenset(other for other in elements if other != element and rng.random() < 0.5)
                    for _ in range(rng.randrange(3))
                }
                for element in elements
            }
            expected = False
            for candidate in permutations(elements):
                rank = {element: index for index, element in enumerate(candidate)}
                if all(rank[a] < rank[b] for a, b in order) and all(
                    any(rank[sibling] < rank[element] for sibling in alternatives)
                    for element, clauses in requirements.items()
                    for alternatives in clauses
                ):
                    expected = True
                    break
            assert has_common_forward_order(order, requirements) == expected


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
        assert_strong_list_precondition(traces)
        assert forward_non_interleaving_with_deletes_from_client_logs(traces, characters) is False


def test_same_yjs_family_trace_without_delete_does_not_interleave():
    for setup in (yjs_setup, yjsmod_setup):
        clients, traces, characters, (l, r, s, v), state_when_v_arrives = replay_yjs_family_counterexample(
            setup, with_delete=False
        )

        assert state_when_v_arrives == [r, s, v, l]
        assert all(client.read_state() == [r, s, v, l] for client in clients)
        assert_strong_list_precondition(traces)
        assert forward_non_interleaving_with_deletes_from_client_logs(traces, characters) is True


if __name__ == "__main__":
    test_lost_origin_is_reported_for_imor()
    test_lost_origin_is_reported_for_suleiman()
    test_fugue_still_passes()
    test_delete_checker_preserves_insert_only_verdicts()
    test_deleted_earlier_sibling_still_exempts_a_later_sibling()
    test_unresolved_sibling_order_is_conservatively_accepted()
    test_transitive_order_can_make_a_violation_certain()
    test_future_sibling_does_not_hide_an_earlier_violation()
    test_sibling_observed_by_another_client_does_not_rewrite_a_state()
    test_inserted_and_deleted_in_one_event_still_counts_as_observed()
    test_deleted_sibling_exemptions_need_one_common_order()
    test_common_order_keeps_sibling_alternatives_and_combines_requirements()
    test_common_order_matches_exhaustive_total_orders()
    test_yjs_family_delete_trace_really_interleaves_consecutive_insertions()
    test_same_yjs_family_trace_without_delete_does_not_interleave()
    print("OK")
