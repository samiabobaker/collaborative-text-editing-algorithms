from __future__ import annotations

import bisect

from automerge.automergemessage import (
    HEAD,
    AutomergeChange,
    AutomergeChangeOp,
    OpId,
    change_hash,
)
from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


class AutomergeOp:
    """One element in the op columns (rust/automerge/src/op_set2/op.rs `Op`).

    For text every element has exactly one op, its insert op. A delete only adds a succ
    pointer, so it never becomes a stored op of its own.
    """

    __slots__ = ("id", "key", "succ", "value")

    id: OpId
    key: OpId
    value: UniqueChar
    succ: list[OpId]

    def __init__(self, op_id: OpId, key: OpId, value: UniqueChar):
        self.id = op_id
        self.key = key
        self.value = value
        self.succ = []

    def visible(self) -> bool:
        return len(self.succ) == 0  # op_set2/op.rs Op::visible


class AutomergeDocument:
    """The op columns and the change graph of one replica (a cut down `Automerge`).

    Ported from the Automerge Rust source, crate version 0.7.4, the op_set2 era, cut down
    to a single text object and to one op per change. The list is a flat run of elements
    in document order, and an element's identity is the id of the operation that created
    it: an insert op with an id of (counter, actor index) and a `key` naming the element
    it went in after, HEAD at the start. A delete only puts a succ pointer on its target,
    so a deleted character stays in the columns as a tombstone and still anchors later
    inserts. That puts Automerge in the RGA family.

    Concurrent siblings, the elements sharing one predecessor, end up in descending
    (counter, actor index) order, newest insert first. That is the RGA rule, and it is
    what op_set2/change/batch.rs `Untangler` implements. The counter advances on deletes
    as well as inserts, since every change takes the next one (automerge.rs
    `transaction_args`), so the tie values here drift away from the rga module, whose
    counter only advances on inserts.
    """

    client_id: int
    actors: list[int]  # sorted; the index of an actor is its ActorIdx
    ops: list[AutomergeOp]  # every element ever inserted, in document order
    changes: dict[bytes, AutomergeChange]
    heads: set[bytes]
    max_op: int
    actor_seq: dict[int, int]
    actor_last_change: dict[int, bytes]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.actors = []
        self.ops = []
        self.changes = {}
        self.heads = set()
        self.max_op = 0
        self.actor_seq = {}
        self.actor_last_change = {}

    # ---- actors ---------------------------------------------------------

    def register_actor(self, actor: int) -> None:
        """automerge.rs put_actor_ref: the actor table is sorted, and an actor's index
        is its position in it.

        Every client is told about every peer at setup, so the index is the client id.
        The binary search insertion upstream reaches the same table whatever order
        actors arrive in.
        """
        if actor not in self.actors:
            bisect.insort(self.actors, actor)

    def actor_idx(self, actor: int) -> int:
        return self.actors.index(actor)

    # ---- reading --------------------------------------------------------

    def visible_op(self, position: int) -> AutomergeOp:
        n = 0
        for op in self.ops:
            if op.visible():
                if n == position:
                    return op
                n += 1
        raise IndexError("past end of the document")

    def traverse(self) -> list[UniqueChar]:
        return [op.value for op in self.ops if op.visible()]

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        return [op.value for op in self.ops]

    def find_op(self, op_id: OpId) -> AutomergeOp:
        for op in self.ops:
            if op.id == op_id:
                return op
        raise IndexError("Could not find op")

    # ---- local changes --------------------------------------------------

    def build_local_change(
        self,
        spec: AutomergeChangeOp,
        causing: ClientInsertOperation | ClientDeleteOperation,
    ) -> AutomergeChange:
        """Build the change for a local op (automerge.rs transaction_args)."""
        actor = self.client_id
        self.register_actor(actor)
        seq = self.actor_seq.get(actor, 0) + 1
        start_op = self.max_op + 1
        ops = (
            AutomergeChangeOp(
                id=(start_op, self.actor_idx(actor)),
                key=spec.key,
                insert=spec.insert,
                action=spec.action,
                value=spec.value,
                pred=spec.pred,
            ),
        )
        deps = set(self.heads)
        if seq > 1:
            last = self.actor_last_change[actor]
            if last not in deps:
                deps.add(last)
        deps_tuple = tuple(sorted(deps))
        hash_ = change_hash(actor, seq, start_op, deps_tuple, ops)
        self.actor_seq[actor] = seq
        self.actor_last_change[actor] = hash_
        return AutomergeChange(hash_, actor, seq, start_op, deps_tuple, ops, causing)

    def integrate_insert(self, key: OpId, op_id: OpId, value: UniqueChar) -> None:
        """Place a new element: before the first element after `key` in column order,
        tombstones included, whose id is not greater than op_id, and at the end if there
        is no such element.

        This is the position the Untangler assigns, since the op is popped from the
        pending stack at the first doc element whose id does not exceed its own
        (op_set2/change/batch.rs `untangle_inserts`). Children of one predecessor
        therefore end up in descending (counter, actor) order.
        """
        start = 0
        if key != HEAD:
            for i, op in enumerate(self.ops):
                if op.id == key:
                    start = i + 1
                    break
            else:
                # Causal readiness guarantees the predecessor's change was applied first.
                raise IndexError("Could not find predecessor")
        for i in range(start, len(self.ops)):
            if self.ops[i].id <= op_id:
                self.ops.insert(i, AutomergeOp(op_id, key, value))
                return
        self.ops.append(AutomergeOp(op_id, key, value))

    def add_succ(self, target: AutomergeOp, op_id: OpId) -> None:
        """A delete: append the op id to the target's succ list, which op_set2/op_set.rs
        add_succ keeps sorted ascending by id."""
        bisect.insort(target.succ, op_id)

    def record_change(self, change: AutomergeChange) -> None:
        """Bookkeeping for an applied change (batch.rs apply, automerge.rs
        update_history and update_deps)."""
        self.changes[change.hash] = change
        self.max_op = max(self.max_op, change.start_op + len(change.ops) - 1)
        for dep in change.deps:
            self.heads.discard(dep)
        self.heads.add(change.hash)

    # ---- remote changes -------------------------------------------------

    def is_causally_ready(self, change: AutomergeChange) -> bool:
        return all(dep in self.changes for dep in change.deps)  # batch.rs is_causally_ready

    def apply_change(self, change: AutomergeChange) -> list[ClientInsertOperation | ClientDeleteOperation]:
        if change.hash in self.changes:
            return []
        for spec in change.ops:
            if spec.insert:
                # Only an insert carries a character, so the value is set by construction.
                assert spec.value is not None
                self.integrate_insert(spec.key, spec.id, spec.value)
            else:
                self.add_succ(self.find_op(spec.key), spec.id)
        self.register_actor(change.actor)
        self.actor_seq[change.actor] = max(self.actor_seq.get(change.actor, 0), change.seq)
        self.record_change(change)
        return [change.causing_operation]
