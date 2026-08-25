from device.clientdevice import ClientDevice
from device.serverdevice import ServerDevice
from interleaving_checker.client_trace import Character, ClientTrace
from interleaving_checker.random_trace import build_random_trace
from unique_char.uniquechar import UniqueChar


def forward_non_interleaving(
    clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_ops: int = 30, print_ops: bool = False
):
    # Assume algorithm satisfies the strong list spec

    # Build a trace of a random execution.
    # Need state at each point of execution.
    # For each character, need its:
    #  left-origin,
    # list of characters for which it is a left origin of,
    # right-origin
    # list of characters for which it is a right origin
    client_logs, characters = build_random_trace(clients, server, num_of_ops, print_ops)

    # For all states
    for client_id in client_logs:
        client_log = client_logs[client_id]
        for state in client_log.states_after_events:
            for A in state:
                for B in state:
                    # To check 1 (forward non-interleaving)
                    if not check_condition_1(state, characters, A, B):
                        if print_ops:
                            print(f"Failed forward interleaving at {A} {B}.")
                            for client_id in clients:
                                print(f"CLIENT {client_id}")
                                for state in client_logs[client_id].states_after_events:
                                    print(*state, sep="")
                                print()
                            for character_id in characters:
                                character = characters[character_id]
                                if print_ops:
                                    print(character)
                        return False
    return True


def maximally_non_interleaving(
    clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_ops: int = 30, print_ops: bool = False
):
    # Assume algorithm satisfies the strong list spec

    # Build a trace of a random execution.
    # Need state at each point of execution.
    # For each character, need its:
    #  left-origin,
    # list of characters for which it is a left origin of,
    # right-origin
    # list of characters for which it is a right origin
    client_logs, characters = build_random_trace(clients, server, num_of_ops, print_ops)

    # For all states
    for client_id in client_logs:
        client_log = client_logs[client_id]
        for state in client_log.states_after_events:
            # The traces contain no deletes, so an origin can only be missing from a
            # state when the algorithm lost the element. That violates the strong list
            # spec assumed above, so it counts as a failure rather than an error when
            # the conditions look the missing element up.
            lost = find_lost_origin(state, characters)
            if lost is not None:
                origin, element = lost
                if print_ops:
                    print(f"Origin {origin} of element {element} is missing from the state.")
                    for client_id in clients:
                        print(f"CLIENT {client_id}")
                        for state in client_logs[client_id].states_after_events:
                            print(*state, sep="")
                        print()
                return False
            for A in state:
                for B in state:
                    # To check 1 (forward non-interleaving)
                    if not check_condition_1(state, characters, A, B):
                        if print_ops:
                            print(f"Failed forward interleaving at {A} {B}.")
                            for client_id in clients:
                                print(f"CLIENT {client_id}")
                                for state in client_logs[client_id].states_after_events:
                                    print(*state, sep="")
                                print()
                            for character_id in characters:
                                character = characters[character_id]
                                if print_ops:
                                    print(character)
                        return False

                    # To check 2(backward non-interleaving)
                    if not check_condition_2(state, characters, A, B):
                        if print_ops:
                            print(f"Failed backward interleaving at {A} {B}")
                            for client_id in clients:
                                print(f"CLIENT {client_id}")
                                for state in client_logs[client_id].states_after_events:
                                    print(*state, sep="")
                                print()
                            for character_id in characters:
                                character = characters[character_id]
                                if print_ops:
                                    print(character)
                        return False

                    # Algorithm is free to choose how to handle the case in condition 3, so this does not need to be checked.

    return True


def maximally_non_interleaving_from_client_logs(
    client_logs: dict[int, ClientTrace], characters: dict[int, Character], print_ops: bool = False
):
    # Assume algorithm satisfies the strong list spec

    # Build a trace of a random execution.
    # Need state at each point of execution.
    # For each character, need its:
    #  left-origin,
    # list of characters for which it is a left origin of,
    # right-origin
    # list of characters for which it is a right origin
    # For all states
    for client_id in client_logs:
        client_log = client_logs[client_id]
        for state in client_log.states_after_events:
            for A in state:
                for B in state:
                    # To check 1 (forward non-interleaving)
                    if not check_condition_1(state, characters, A, B):
                        if print_ops:
                            print(f"Failed forward interleaving at {A} {B}.")
                            for client_id in client_logs:
                                print(f"CLIENT {client_id}")
                                for state in client_logs[client_id].states_after_events:
                                    print(*state, sep="")
                                print()
                            for character_id in characters:
                                character = characters[character_id]
                                print(character)
                        return False

                    # To check 2(backward non-interleaving)
                    if not check_condition_2(state, characters, A, B):
                        if print_ops:
                            print(f"Failed backward interleaving at {A} {B}")
                            for client_id in client_logs:
                                print(f"CLIENT {client_id}")
                                for state in client_logs[client_id].states_after_events:
                                    print(*state, sep="")
                                print()
                            for character_id in characters:
                                character = characters[character_id]
                                print(character)
                        return False

                    # Algorithm is free to choose how to handle the case in condition 3, so this does not need to be checked.

    return True


# Returns an origin that is missing from the state together with the element that
# recorded it, or None when every origin is present.
def find_lost_origin(state: list[UniqueChar], characters: dict[int, Character]) -> tuple[UniqueChar, UniqueChar] | None:
    for element in state:
        character = characters[element.id]
        left_origin = character.left_origin
        if left_origin != "start" and left_origin not in state:
            return left_origin, element
        right_origin = character.right_origin
        if right_origin != "end" and right_origin not in state:
            return right_origin, element
    return None


def check_condition_1(state: list[UniqueChar], characters: dict[int, Character], A: UniqueChar, B: UniqueChar) -> bool:
    # Does this condition apply?
    # Is A the left origin of B?
    B_character = characters[B.id]
    if B_character.left_origin != A:
        return True
    # For all elements that A is the left origin of, is B the earliest one in the state.
    A_character = characters[A.id]
    for character in A_character.left_origin_of:
        if character in state and state.index(character) < state.index(B):
            return True

    # If this condition applies, check that A and B are consecutive.
    A_index = state.index(A)
    B_index = state.index(B)
    return A_index + 1 == B_index


def check_condition_2(state: list[UniqueChar], characters: dict[int, Character], A: UniqueChar, B: UniqueChar) -> bool:
    # Does this condition apply?
    # Is B the right origin of A?
    A_character = characters[A.id]
    if A_character.right_origin != B:
        return True

    # For all elements that has B as right origin, A appears latest in the list.
    B_character = characters[B.id]
    for character in B_character.right_origin_of:
        if character in state and state.index(A) < state.index(character):
            return True
    # Does Theorem 5 apply?
    if theorem_5_applies(state, characters, A, B):
        return True

    # If condition applies and theorem 5 does not, check that A and B are consecutive.
    A_index = state.index(A)
    B_index = state.index(B)

    return A_index + 1 == B_index


# Assuming B is the right origin of A?
# Assuming A appears later in the list than other elements that have B as right origin.
def theorem_5_applies(state: list[UniqueChar], characters: dict[int, Character], A: UniqueChar, B: UniqueChar) -> bool:
    # Do A and B have different left origins?
    A_character = characters[A.id]
    B_character = characters[B.id]

    A_left_origin = A_character.left_origin
    B_left_origin = B_character.left_origin

    if A_left_origin == B_left_origin:
        return False
    # There exists a C such that A.leftOrign < C < B in the list state.

    if A_left_origin != "start":
        A_left_origin_index = state.index(A_left_origin)
        B_index = state.index(B)
        for i in range(A_left_origin_index + 1, B_index):
            C = state[i]
            if not is_a_descendent_in_the_left_origin_tree(characters, C, A_left_origin):
                return True
    return False


def is_a_descendent_in_the_left_origin_tree(characters: dict[int, Character], child: UniqueChar, parent: UniqueChar):
    current = child

    while current != parent and current != "start":
        current_character = characters[current.id]
        parent_of_current = current_character.left_origin
        current = parent_of_current

    return current != "start"
