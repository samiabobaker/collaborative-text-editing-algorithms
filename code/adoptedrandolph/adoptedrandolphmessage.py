from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


# We need a total order on the characters. Easiest way to provide this is to attach client_id and site counter to the characters.
@dataclass
class AdOPTedRandolphCharacter:
    character: UniqueChar
    client_id: int
    counter: int

    def less_than(self, other: AdOPTedRandolphCharacter) -> bool:
        return (
            (self.character.char < other.character.char)
            or (self.character.char == other.character.char and self.client_id < other.client_id)
            or (
                self.character.char == other.character.char
                and self.client_id == other.client_id
                and self.counter < other.counter
            )
        )


# eq=False keeps the default identity-based __hash__: a dataclass-generated
# __eq__ sets __hash__ to None, making these operations unhashable, so
# SuleimanTransform's av/ap sets (b1.union({O2}) in adoptedtransform.py)
# raise TypeError. Identity semantics is what those sets need — each
# transform step reuses the memoised operation objects from the
# interaction model.
@dataclass(eq=False)
class AdOPTedRandolphInsertionOperation:
    position: int
    character: AdOPTedRandolphCharacter
    nd: int
    vector_clock: dict[int, int]


@dataclass(eq=False)
class AdOPTedRandolphDeletionOperation:
    position: int
    vector_clock: dict[int, int]


class AdOPTedRandolphNoOperation:
    vector_clock: dict[int, int]


AdOPTedRandolphOperation = (
    AdOPTedRandolphInsertionOperation | AdOPTedRandolphDeletionOperation | AdOPTedRandolphNoOperation
)


@dataclass
class AdOPTedRandolphMessage:
    client_id: int
    vector_clock: dict[int, int]
    operation: AdOPTedRandolphOperation
    causing_operation: (
        ClientInsertOperation | ClientDeleteOperation
    )  # The client operation that triggered this message to be sent.
