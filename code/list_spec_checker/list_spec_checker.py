from typing import assert_never

from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation
from device.serverdevice import ServerDevice
from list_spec_checker.random_trace import ClientTrace, build_random_trace
from unique_char.uniquechar import UniqueChar


def strong_list_specification_checker(
    clients: dict[int, ClientDevice],
    server: ServerDevice | None = None,
    num_of_operations: int = 30,
    print_ops: bool = False,
) -> bool:
    try:
        client_log = build_random_trace(clients, server, num_of_operations, print_ops)
    # The algorithm produced an operation that cannot be applied, e.g. a transformed delete past the end of the state.
    except (IndexError, ValueError) as e:
        print(
            f"This algorithm does not satisfy the list specification ({type(e).__name__} while applying an operation: {e})."
        )
        return False

    for client_id in clients:
        if not check_condition1a(client_log[client_id]):
            return False
        if not check_condition1c(client_log[client_id]):
            return False

    list_order = build_list_order_for_condition1b(client_log)
    if not check_condition2_strong(list_order):
        """for client_id in clients:
            print(f"CLIENT {client_id}")
            for state in client_log[client_id].states_after_events:
                print(*state, sep="")
            print()"""
        return False

    return True


def strong_list_specification_checker_for_client_log(client_log: dict[int, ClientTrace]) -> bool:
    for client_id in client_log:
        if not check_condition1a(client_log[client_id]):
            return False
        if not check_condition1c(client_log[client_id]):
            return False

    list_order = build_list_order_for_condition1b(client_log)
    if not check_condition2_strong(list_order):
        for client_id in client_log:
            print(f"CLIENT {client_id}")
            for state in client_log[client_id].states_after_events:
                print(*state, sep="")
            print()
        return False

    return True


def weak_list_specification_checker(
    clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_ops: int = 30
) -> bool:
    try:
        client_log = build_random_trace(clients, server, num_of_ops)
    # The algorithm produced an operation that cannot be applied, e.g. a transformed delete past the end of the state.
    except (IndexError, ValueError) as e:
        print(
            f"This algorithm does not satisfy the list specification ({type(e).__name__} while applying an operation: {e})."
        )
        return False

    list_order = build_list_order_for_condition1b(client_log)

    for client_id in clients:
        if not check_condition1a(client_log[client_id]):
            return False
        if not check_condition1c(client_log[client_id]):
            return False
        if not check_condition2_weak_for_client(client_log[client_id], list_order):
            for client_id in clients:
                print(f"CLIENT {client_id}")
                for state in client_log[client_id].states_after_events:
                    print(*state, sep="")
                print()
            return False

    return True


# Check at each point in the client log, the set of characters in the state = set of characters inserted - set of characters deleted.
def check_condition1a(client_log: ClientTrace) -> bool:
    inserted_characters: set[UniqueChar] = set()

    deleted_characters: set[UniqueChar] = set()

    for i in range(len(client_log.events_seen)):
        event = client_log.events_seen[i]

        for operation in event.operation:
            match operation:
                case ClientInsertOperation(_, _, character):
                    inserted_characters.add(character)
                case ClientDeleteOperation(_, _, character):
                    deleted_characters.add(character)
                case _ as unreachable:
                    assert_never(unreachable)

        state = client_log.states_after_events[i]

        if set(state) != inserted_characters.difference(deleted_characters):
            return False

    return True


# Records every pair of each state, not just adjacent pairs, as condition 1b requires.
# The weak check restricts this order to a state's characters before taking the transitive
# closure, so a pair related only through a character absent from that state would be lost.
def build_list_order_for_condition1b(client_logs: dict[int, ClientTrace]) -> set[tuple[UniqueChar, UniqueChar]]:
    list_order: set[tuple[UniqueChar, UniqueChar]] = set()

    for client in client_logs:
        client_log = client_logs[client]

        for state in client_log.states_after_events:
            for i in range(len(state)):
                for j in range(i + 1, len(state)):
                    list_order.add((state[i], state[j]))

    return list_order


# Check after each insert event, the inserted character is at the specified position.
def check_condition1c(client_log: ClientTrace) -> bool:
    for i in range(len(client_log.events_seen)):
        event = client_log.events_seen[i]

        if isinstance(event.operation[0], ClientInsertOperation) and event.performed_locally:
            state = client_log.states_after_events[i]
            if state[event.operation[0].position] != event.operation[0].character:
                return False

    return True


# Need to check that there exists a list order that is transitive, irreflexive and total,
# and that the inputted list_order is a subset of this list order (so this list order still satisfies condition 1b).
# Apply transitive closure to make it transitive.
# Check it is irreflexive.
# It can then be extended to be made total (e.g. by toposort)
def check_condition2_strong(list_order: set[tuple[UniqueChar, UniqueChar]]):
    # Apply transitive closure.
    transitive_closure_of_order: set[tuple[UniqueChar, UniqueChar]] = set()

    changed = True

    while changed:
        changed = False
        for x1, y1 in list_order:
            if (x1, y1) not in transitive_closure_of_order:
                transitive_closure_of_order.add((x1, y1))

            for x2, y2 in list_order:
                if y1 == x2 and (x1, y2) not in transitive_closure_of_order:
                    changed = True
                    transitive_closure_of_order.add((x1, y2))
        list_order = set(transitive_closure_of_order)

    # Check for irreflexivity
    return all(x != y for x, y in transitive_closure_of_order)


# Same as for strong, but do it at every step.
# Also remove the deleted and not inserted characters at each step.
# Then, build a transitive, irreflexive, total order for each.
def check_condition2_weak_for_client(client_log: ClientTrace, list_order: set[tuple[UniqueChar, UniqueChar]]):
    # Apply transitive closure.
    for state in client_log.states_after_events:
        list_order_without_deleted: set[tuple[UniqueChar, UniqueChar]] = set()

        for x, y in list_order:
            if x in state and y in state:
                list_order_without_deleted.add((x, y))

        transitive_closure_of_order: set[tuple[UniqueChar, UniqueChar]] = set()

        changed = True

        while changed:
            changed = False
            for x1, y1 in list_order_without_deleted:
                if (x1, y1) not in transitive_closure_of_order:
                    transitive_closure_of_order.add((x1, y1))

                for x2, y2 in list_order_without_deleted:
                    if y1 == x2 and (x1, y2) not in transitive_closure_of_order:
                        changed = True
                        transitive_closure_of_order.add((x1, y2))
            list_order_without_deleted = set(transitive_closure_of_order)

        # Check for irreflexivity
        for x, y in transitive_closure_of_order:
            if x == y:
                return False
    return True
