import random

from algorithm_setup.algorithm_setup import (
    DeviceSetup,
    automerge_setup,
    fugue_setup,
    fuguemax_setup,
    loro_setup,
    rga_setup,
    sync9_setup,
    yjs_setup,
    yjsmod_setup,
)
from device.clientdevice import ClientDevice
from origin_order_checker.origin_order_checker import (
    AFTER,
    BEFORE,
    CELLS,
    anchoring_checker,
    anchoring_of,
    build_trace,
    classify_pair,
    origin_order_checker,
    run_anchoring_scenario,
)


def _client_dict(setup: DeviceSetup, num_of_clients: int) -> dict[int, ClientDevice]:
    _, clients = setup(num_of_clients)
    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client
    return client_dict


# Every algorithm in the family reproduces its declared scheme and key on random traces.
def test_algorithms_match_their_declared_cells():
    for setup in [
        automerge_setup,
        fugue_setup,
        fuguemax_setup,
        loro_setup,
        rga_setup,
        sync9_setup,
        yjs_setup,
        yjsmod_setup,
    ]:
        for seed in range(25):
            random.seed(seed)
            assert origin_order_checker(_client_dict(setup, 3), None, 30)


# The builder delivers everything before reading the settled states.
def test_builder_ends_fully_delivered():
    random.seed(0)
    clients = _client_dict(fugue_setup, 3)
    records, deleted, stream, converged = build_trace(clients, CELLS["FugueClient"], 30)
    assert converged is not None
    assert len(records) != 0
    assert len(deleted) != 0
    assert len(stream) != 0
    for client in clients.values():
        assert client.can_receive_from() == []


# Every coordinate is load bearing on delete carrying traces, the anchoring included.
def test_a_misdeclared_anchoring_is_caught():
    for setup, name in [(fugue_setup, "FugueClient"), (yjs_setup, "YjsClient")]:
        scheme, key, anchoring = CELLS[name]
        flipped = BEFORE if anchoring == AFTER else AFTER
        CELLS[name] = (scheme, key, flipped)
        try:
            caught = 0
            for seed in range(25):
                random.seed(seed)
                if not origin_order_checker(_client_dict(setup, 3), None, 30):
                    caught += 1
        finally:
            CELLS[name] = (scheme, key, anchoring)
        assert caught != 0


# fuguemax and yjsmod share a scheme and differ in the other two, and with tombstones in
# the traces the anchoring is nameable, so it appears beside the key rather than hiding.
def test_fuguemax_vs_yjsmod_divergences_are_the_key_and_the_anchoring():
    outcomes = [classify_pair(fuguemax_setup, yjsmod_setup, seed) for seed in range(1, 101)]
    divergences = [outcome for outcome in outcomes if outcome not in ("identical", "schedule-diverged")]
    assert len(divergences) != 0
    assert all(outcome == "key+anchoring" for outcome in divergences)


# sync9 and fugue implement the same scheme, so every divergence is the sibling key.
def test_sync9_vs_fugue_divergences_are_key_only():
    outcomes = [classify_pair(sync9_setup, fugue_setup, seed) for seed in range(1, 101)]
    divergences = [outcome for outcome in outcomes if outcome not in ("identical", "schedule-diverged")]
    assert len(divergences) != 0
    assert all(outcome == "key" for outcome in divergences)


# fugue and fuguemax share a key, so every divergence is the scheme, and it is rare.
def test_fugue_vs_fuguemax_divergences_are_scheme_only():
    outcomes = [classify_pair(fugue_setup, fuguemax_setup, seed) for seed in range(1, 201)]
    divergences = [outcome for outcome in outcomes if outcome not in ("identical", "schedule-diverged")]
    assert len(divergences) != 0
    assert all(outcome == "scheme" for outcome in divergences)


# Both anchorings are taken by algorithms here, so neither is the one the others get wrong.
def test_both_anchorings_are_declared_and_hold():
    assert anchoring_of(yjs_setup) == AFTER
    assert anchoring_of(fugue_setup) == BEFORE
    for setup in [
        automerge_setup,
        fugue_setup,
        fuguemax_setup,
        loro_setup,
        rga_setup,
        sync9_setup,
        yjs_setup,
        yjsmod_setup,
    ]:
        assert anchoring_checker(setup)


# Reading one scenario alone would misplace an algorithm whose tie break is not the site id,
# which is why the scenario is run under both orders as well as both sides.
def test_the_anchoring_scenario_needs_its_controls():
    site_swapped_only = [run_anchoring_scenario(fugue_setup, False, False, deleter, False) for deleter in (0, 1)]
    assert site_swapped_only == ["yx", "yx"]
    assert anchoring_of(fugue_setup) == BEFORE


if __name__ == "__main__":
    test_algorithms_match_their_declared_cells()
    test_builder_ends_fully_delivered()
    test_a_misdeclared_anchoring_is_caught()
    test_fuguemax_vs_yjsmod_divergences_are_the_key_and_the_anchoring()
    test_sync9_vs_fugue_divergences_are_key_only()
    test_fugue_vs_fuguemax_divergences_are_scheme_only()
    test_both_anchorings_are_declared_and_hold()
    test_the_anchoring_scenario_needs_its_controls()
    print("OK")
