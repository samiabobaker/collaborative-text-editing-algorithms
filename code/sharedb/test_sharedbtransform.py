import random
from itertools import product

from algorithm_setup.algorithm_setup import sharedb_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from sharedb.sharedbmessage import ShareDBDelete, ShareDBInsert, ShareDBOperation, ShareDBSkip
from sharedb.sharedbtransform import apply, compose, normalise, transform
from unique_char.uniquechar import UniqueChar


def _document(word: str) -> list[UniqueChar]:
    return [UniqueChar(character, index) for index, character in enumerate(word)]


def _word(state: list[UniqueChar]) -> str:
    return "".join(character.char for character in state)


def _insert(position: int, characters: str) -> ShareDBOperation:
    return normalise([ShareDBSkip(position), ShareDBInsert([UniqueChar(c, 100 + i) for i, c in enumerate(characters)])])


def _delete(position: int, count: int) -> ShareDBOperation:
    return normalise([ShareDBSkip(position), ShareDBDelete(count)])


def _every_operation(length: int) -> list[ShareDBOperation]:
    operations = [_insert(position, "X") for position in range(length + 1)]
    operations += [_insert(position, "XY") for position in range(length + 1)]
    operations += [_delete(position, count) for position in range(length) for count in range(1, length - position + 1)]
    operations += [
        normalise(
            [ShareDBSkip(position), ShareDBInsert([UniqueChar("Z", 200 + position)]), ShareDBSkip(1), ShareDBDelete(1)]
        )
        for position in range(length - 1)
    ]
    return operations


# The server transforms whatever is submitted against what it has already committed, and
# the client transforms what it is holding against what arrives, and the two ends never
# compare notes. Both are sound only if applying one operation and then the other
# transformed reaches the same document whichever way round it is done.
def test_applying_either_operation_first_reaches_the_same_document():
    state = _document("abcd")
    for first, second in product(_every_operation(len(state)), repeat=2):
        one_way = apply(apply(state, first), transform(second, first, "right"))
        other_way = apply(apply(state, second), transform(first, second, "left"))
        assert _word(one_way) == _word(other_way)


# Where both insert at one position the left one goes first, which is what makes the two
# ends agree: whoever is submitting is the left one.
def test_concurrent_inserts_are_ordered_by_side():
    state = _document("ab")
    mine = _insert(1, "L")
    theirs = _insert(1, "R")

    assert _word(apply(apply(state, mine), transform(theirs, mine, "right"))) == "aLRb"
    assert _word(apply(apply(state, theirs), transform(mine, theirs, "left"))) == "aLRb"


# A delete of characters someone else has already deleted has nothing left to do.
def test_concurrent_deletes_of_the_same_characters():
    state = _document("abcd")
    mine = _delete(1, 2)
    theirs = _delete(2, 2)

    assert transform(mine, theirs, "left") == _delete(1, 1)
    assert _word(apply(apply(state, theirs), transform(mine, theirs, "left"))) == "a"


# A run of typing that is composed while an earlier operation is with the server has to
# do what the operations did one after another.
def test_compose_matches_applying_in_turn():
    state = _document("ab")
    first = _insert(1, "x")
    second = _insert(2, "y")

    composed = compose(first, second)

    assert _word(apply(apply(state, first), second)) == _word(apply(state, composed))
    # The two inserts became one, which is what stops a run of typing being split up.
    assert composed[0] == ShareDBSkip(1)
    assert isinstance(composed[1], ShareDBInsert)
    assert _word(composed[1].characters) == "xy"
    assert len(composed) == 2


# Composing a delete with a later insert keeps the delete and converts the skip,
# and deleting what the first operation had just inserted leaves nothing at all.
def test_compose_cancels_and_converts_deletes():
    assert compose(_insert(0, "x"), _delete(0, 1)) == []

    composed = compose(_delete(0, 1), _insert(1, "x"))
    assert composed[0] == ShareDBDelete(1)
    assert composed[1] == ShareDBSkip(1)
    assert isinstance(composed[2], ShareDBInsert)
    assert _word(composed[2].characters) == "x"
    assert len(composed) == 3


# An operation never carries a trailing skip, so transforming against an
# operation that changed nothing it walks over gives the same operation back.
def test_transformed_operations_stay_canonical():
    operation = _insert(0, "X")
    assert transform(operation, _delete(0, 1), "left") == operation
    assert transform([], _insert(0, "X"), "left") == []


# The two lines that register the algorithm, exercised the way the checker will reach it.
def test_registered_algorithm_converges():
    random.seed(1)
    server, clients = sharedb_setup(3)

    client_dict: dict[int, ClientDevice] = {}
    for client in clients:
        client_dict[client.client_id] = client

    assert convergence_checker(client_dict, server, 30) is True


if __name__ == "__main__":
    test_applying_either_operation_first_reaches_the_same_document()
    test_concurrent_inserts_are_ordered_by_side()
    test_concurrent_deletes_of_the_same_characters()
    test_compose_matches_applying_in_turn()
    test_compose_cancels_and_converts_deletes()
    test_transformed_operations_stay_canonical()
    test_registered_algorithm_converges()
    print("OK")
