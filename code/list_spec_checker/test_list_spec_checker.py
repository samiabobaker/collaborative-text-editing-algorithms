from list_spec_checker.client_trace import ClientTrace
from list_spec_checker.list_spec_checker import (
    build_list_order_for_condition1b,
    check_condition2_weak_for_client,
)
from unique_char.uniquechar import UniqueChar


def _trace(*states):
    trace = ClientTrace()
    trace.states_after_events = [list(state) for state in states]
    return trace


# d and x are co-visible in both states and ordered oppositely, but never adjacent.
def test_weak_rejects_conflicting_covisible_order():
    d = UniqueChar("d", 0)
    m = UniqueChar("m", 1)
    x = UniqueChar("x", 2)
    y = UniqueChar("y", 3)

    logs = {0: _trace([d, m, x]), 1: _trace([x, y, d])}
    list_order = build_list_order_for_condition1b(logs)

    assert not all(check_condition2_weak_for_client(logs[c], list_order) for c in logs)


def test_weak_accepts_consistent_order():
    d = UniqueChar("d", 0)
    m = UniqueChar("m", 1)
    x = UniqueChar("x", 2)
    y = UniqueChar("y", 3)

    logs = {0: _trace([d, m, x]), 1: _trace([d, y, x])}
    list_order = build_list_order_for_condition1b(logs)

    assert all(check_condition2_weak_for_client(logs[c], list_order) for c in logs)


if __name__ == "__main__":
    test_weak_rejects_conflicting_covisible_order()
    test_weak_accepts_consistent_order()
    print("OK")
