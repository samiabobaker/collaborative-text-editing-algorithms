from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from loro.lorodocument import LoroId
from unique_char.uniquechar import UniqueChar


@dataclass
class LoroInsertOperation:
    """`ListOp::Insert` carrying a single character slice.

    Loro's insert records nothing but the slice and the plain visible index
    the insert was made at (container/list/list_op.rs, lines 20-24; the
    handler that builds it is handler.rs `insert_with_txn`, around line 2194).
    No origins go on the wire: `pos` is read against the originator's state at
    generation time and every replica derives the origins itself.
    """

    op_id: LoroId
    pos: int
    char: UniqueChar


@dataclass
class LoroDeleteOperation:
    """`ListOp::Delete(DeleteSpanWithId)` for a single character.

    A text delete is emitted as `DeleteSpanWithId::new(id_start, pos, len)`
    (handler.rs `TextHandler::delete_with_txn`, which starts at line 2214 and
    builds the span at line 2276), so it carries both the id of the leftmost
    element removed and the visible index it sat at in the originator's state
    (list_op.rs, lines 25 and 132-141, with `DeleteSpan` at lines 288-291).
    A delete draws from the same per peer counter as an insert, so it has an
    id of its own as well.
    """

    op_id: LoroId
    target_id: LoroId
    pos: int


LoroOperation = LoroInsertOperation | LoroDeleteOperation


@dataclass
class LoroMessage:
    """A causally broadcast message.

    Real Loro records the dependency frontiers of each change and replays a
    DAG. Following the repo convention (fugue/fuguemessage.py) the causal past
    is written here as a vector clock snapshot taken when the operation was
    generated, which for full mesh replication is the same past in a different
    encoding. The clock is not only for delivery order: it is the version the
    receiving rope is checked out to before the operation is integrated, which
    is what Loro's diff calculator does when it hands an operation to the
    tracker (diff_calc.rs `calc_diff_internal`, lines 270-300, which passes
    the accumulated version vector to `tracker.checkout` before applying).
    """

    vector_clock: dict[int, int]
    operation: LoroOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
