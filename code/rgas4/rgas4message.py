from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass(frozen=True)
class S4Vector:
    ssn: int
    sid: int
    sum: int
    seq: int

    def less_than(self, other: S4Vector) -> bool:
        return (
            self.ssn < other.ssn
            or (self.ssn == other.ssn and self.sum < other.sum)
            or (self.ssn == other.ssn and self.sum == other.sum and self.sid < other.sid)
        )


@dataclass
class RGAS4Node:
    obj: UniqueChar | None
    s_k: S4Vector
    s_p: S4Vector
    link: RGAS4Node | None


@dataclass
class RGAS4InsertionOperation:
    position: S4Vector | None
    character: UniqueChar


@dataclass
class RGAS4DeletionOperation:
    position: S4Vector


RGAS4Operation = RGAS4InsertionOperation | RGAS4DeletionOperation


@dataclass
class RGAS4Message:
    client_id: int
    vector_clock: dict[int, int]
    operation: RGAS4Operation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
