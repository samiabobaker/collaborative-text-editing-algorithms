from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from diamondtypes.diamondtypesdocument import DiamondTypesId, DiamondTypesOperation


@dataclass
class DiamondTypesMessage:
    """One operation on the wire, exactly as its sender recorded it.

    There is no separate wire format here and no vector clock. An eg-walker
    operation already names its own parents, so the operation is both what the
    sender stored in its oplog and what the receiver needs to place it in the event
    graph, and those parents are what says whether it is ready to be applied.
    """

    id: DiamondTypesId
    operation: DiamondTypesOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
