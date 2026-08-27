from __future__ import annotations

import hashlib
from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar

# An op id: (counter, actor_index). Python tuple ordering matches the derived Ord on the
# Rust OpId(u32, u32) (rust/automerge/src/types.rs): counter first, then actor index. An
# actor index is a position in the document's sorted actor table (automerge.rs
# `put_actor_ref` inserts by binary search), so for the client ids 0..n-1 used here the
# actor index is the client id.
OpId = tuple[int, int]

# The head of every sequence: ElemId::head() == OpId(0, 0) (types.rs).
HEAD: OpId = (0, 0)


@dataclass(frozen=True)
class AutomergeChangeOp:
    """One op inside a change (simplified ChangeOp, op_set2/op.rs OpBuilder).

    An insert carries the elem id it was inserted after in `key` (HEAD at index 0);
    a delete carries the target elem in `key` and the ids it removes in `pred`. Only
    an insert is ever stored in the op columns, since op_set2/columns.rs `splice`
    filters Action::Delete out; a delete op just adds a succ pointer to its target.
    There is no `obj` field: this port has a single text object at the root.
    """

    id: OpId
    key: OpId
    insert: bool
    action: str  # "set" (insert a character) or "del" (op_set2::types::Action)
    value: UniqueChar | None  # the inserted character; None for deletes
    pred: tuple[OpId, ...]


@dataclass
class AutomergeChange:
    """A committed change (rust/automerge/src/change.rs).

    Upstream a change can hold any number of ops. Here it holds exactly one, which is
    what AutoCommit produces when a client types a character at a time, so `start_op`
    is that op's counter. Every change takes the next counter, deletes as well as
    inserts, which is why the ids here drift away from the ones the rga module hands
    out for the same trace.

    `causing_operation` is not part of Automerge: it is the local operation that
    produced this change, carried along so that a receiving client can report what it
    just saw, which is what every other client in this repository does with
    `message.causing_operation`.
    """

    hash: bytes
    actor: int
    seq: int  # per actor sequence number
    start_op: int  # counter of the first op in the change
    deps: tuple[bytes, ...]  # hashes of the changes this one depends on
    ops: tuple[AutomergeChangeOp, ...]
    causing_operation: ClientInsertOperation | ClientDeleteOperation


def change_hash(
    actor: int,
    seq: int,
    start_op: int,
    deps: tuple[bytes, ...],
    ops: tuple[AutomergeChangeOp, ...],
) -> bytes:
    """SHA-256 over a canonical serialization of the change.

    Automerge hashes the binary columnar encoding of the change
    (rust/automerge/src/storage/change.rs), which is not replicated here; hashing a
    canonical Python form of the same fields gives every replica in this model the same
    bytes for the same change, which is all the sync protocol needs.
    """
    payload = repr(
        (
            actor,
            seq,
            start_op,
            deps,
            tuple(
                (
                    o.id,
                    o.key,
                    o.insert,
                    o.action,
                    (o.value.char, o.value.id) if o.value is not None else None,
                    o.pred,
                )
                for o in ops
            ),
        )
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()
