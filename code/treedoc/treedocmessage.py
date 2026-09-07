from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from treedoc.treedoctree import TreedocPosID
from unique_char.uniquechar import UniqueChar


# The two edit operations of section 2.2. Both of them name the atom by its PosID, which
# never changes and means the same thing at every replica, so they commute.
@dataclass
class TreedocInsertionOperation:
    pos_id: TreedocPosID
    char: UniqueChar


@dataclass
class TreedocDeletionOperation:
    pos_id: TreedocPosID


TreedocOperation = TreedocInsertionOperation | TreedocDeletionOperation


@dataclass
class TreedocMessage:
    vector_clock: dict[int, int]
    operation: TreedocOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
