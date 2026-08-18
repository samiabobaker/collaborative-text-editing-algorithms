from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


# eq=False keeps the default identity-based __hash__: a dataclass-generated
# __eq__ sets __hash__ to None, making these operations unhashable, so
# SuleimanTransform's av/ap sets (b1.union({O2}) in adoptedtransform.py)
# raise TypeError. Identity semantics is what those sets need — each
# transform step reuses the memoised operation objects from the
# interaction model.
@dataclass(eq=False)
class AdOPTedInsertionOperation:
    position: int
    character: UniqueChar
    priority: int
    b: set[AdOPTedOperation]
    a: set[AdOPTedOperation]
    vector_clock: dict[int, int]


@dataclass(eq=False)
class AdOPTedDeletionOperation:
    position: int
    priority: int
    vector_clock: dict[int, int]


class AdOPTedNoOperation:
    vector_clock: dict[int, int]


AdOPTedOperation = AdOPTedInsertionOperation | AdOPTedDeletionOperation | AdOPTedNoOperation


@dataclass
class AdOPTedMessage:
    client_id: int
    vector_clock: dict[int, int]
    operation: AdOPTedOperation
    causing_operation: (
        ClientInsertOperation | ClientDeleteOperation
    )  # The client operation that triggered this message to be sent.
