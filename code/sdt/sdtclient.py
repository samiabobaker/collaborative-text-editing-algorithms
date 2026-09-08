from dataclasses import replace
from typing import assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from sdt.sdtmessage import (
    SYNTHETIC_CLIENT_ID,
    SDTDeleteOperation,
    SDTIdentityOperation,
    SDTInsertOperation,
    SDTMessage,
    SDTOperation,
)
from unique_char.uniquechar import UniqueChar

# An operation is identified by the site that generated it and that site's own component of
# its timestamp, which is what lets the recorded effects relation survive transformation.
OperationKey = tuple[int, int]


# State difference based transformation, from Li and Li (2008), "An Approach to Ensuring
# Consistency in Peer-to-Peer Real-Time Group Editors". Algorithm numbers in the comments
# below refer to that paper.
#
# The transformation functions decide the effects relation between two operations by
# comparing where their effects fall in an earlier common state, the latest synchronization
# point, rather than by comparing their position parameters in the current state. The
# effect of an operation on an earlier state is a <beta, delta> pair, computed by excluding
# a state difference: the net effect of everything executed in between, compressed so that
# an insert and the delete that counteracts it disappear together.
#
# Operations are timestamped the way the paper does it, with the state vector of the state
# that results from their generation, so V(O)[ID(O)] counts O itself.
#
# SDT was later shown not to converge, see Oster et al. (2005), "Proving correctness of
# transformation functions in collaborative editing systems"; this is a faithful
# implementation of the paper rather than a corrected one.
class SDTClient(ClientDevice):
    client_id: int

    clients: list[SDTClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[SDTMessage]]

    state: list[UniqueChar]
    history_buffer: list[SDTOperation]

    # The effects relation recorded by SQIT for every pair of concurrent operations it
    # transforms, keyed both ways round. Section 6.2: an exclusion transformation between
    # two concurrent operations cannot recover the relation from their positions, so the
    # relation established when they were inclusively transformed is looked up instead.
    effects_relation: dict[tuple[OperationKey, OperationKey], bool]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.history_buffer = []
        self.effects_relation = {}

    def set_clients(self, clients: list[SDTClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                self.perform_local_insert(operation)
                return [operation]
            case ClientDeleteOperation():
                self.perform_local_delete(operation)
                return [operation]
            case ClientReceiveFromServerOperation():
                return []
            case ClientReceiveFromClientOperation(_, sender_client_id):
                return self.receive_from_client(sender_client_id)
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    # Local operations are generated on the current state, so they are executed as they are.
    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.vector_clock[self.client_id] += 1
        op = SDTInsertOperation(self.client_id, self.vector_clock.copy(), operation.position, [operation.character])
        self.__execute(op)
        self.__send_to_other_clients(SDTMessage(self.client_id, op.vector_clock.copy(), op, operation))

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.vector_clock[self.client_id] += 1
        op = SDTDeleteOperation(self.client_id, self.vector_clock.copy(), operation.position, operation.character)
        self.__execute(op)
        self.__send_to_other_clients(SDTMessage(self.client_id, op.vector_clock.copy(), op, operation))

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        executable = self.integrate(message.operation, self.history_buffer)

        # Section 8: an identity operation is neither executed nor appended to the history
        # buffer. IT returns one when two concurrent deletes remove the same character.
        # Keeping it in the buffer instead, as the GOTO and SOCT2 control algorithms this
        # one is modelled on do, makes no difference to any execution measured here: either
        # way the buffer holds no delete of that character, because the delete that actually
        # happened at this site was the concurrent one.
        if not isinstance(executable, SDTIdentityOperation):
            self.__execute(executable)

        self.vector_clock[client_id] += 1

        return [message.causing_operation]

    def send_message(self, client_id: int, message: SDTMessage) -> None:
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: SDTMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def __is_causally_ready(self, message: SDTMessage) -> bool:
        # Timestamps count the operation they belong to, so the sender's own component has
        # to be exactly one ahead of what this site has seen from it.
        for client in self.clients:
            if client.client_id == message.client_id:
                if message.vector_clock[client.client_id] != self.vector_clock[client.client_id] + 1:
                    return False
            elif message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True

    def __execute(self, operation: SDTOperation) -> None:
        self.__apply_operation(operation)
        self.history_buffer.append(operation)

    def __apply_operation(self, operation: SDTOperation) -> None:
        match operation:
            case SDTInsertOperation(_, _, position, characters):
                self.state[position:position] = characters
            case SDTDeleteOperation(_, _, position, _):
                del self.state[position]
            case SDTIdentityOperation():
                pass
            case _ as unreachable:
                assert_never(unreachable)

    # Timestamps and operation relations.

    def vector_clock_leq(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return all(v1[client_id] <= v2[client_id] for client_id in v1)

    def happened_before(self, O1: SDTOperation, O2: SDTOperation) -> bool:
        return self.vector_clock_leq(O1.vector_clock, O2.vector_clock) and O1.vector_clock != O2.vector_clock

    def is_concurrent(self, O1: SDTOperation, O2: SDTOperation) -> bool:
        return not self.happened_before(O1, O2) and not self.happened_before(O2, O1)

    def __operation_key(self, O: SDTOperation) -> OperationKey | None:
        # Synthesised inserts in a state difference carry no timestamp, so they have no key.
        if O.client_id == SYNTHETIC_CLIENT_ID:
            return None
        return (O.client_id, O.vector_clock[O.client_id])

    def store_effects_relation(self, O1: SDTOperation, O2: SDTOperation, first_precedes: bool) -> None:
        key1 = self.__operation_key(O1)
        key2 = self.__operation_key(O2)
        if key1 is None or key2 is None:
            return
        self.effects_relation[(key1, key2)] = first_precedes
        self.effects_relation[(key2, key1)] = not first_precedes

    def stored_effects_relation(self, O1: SDTOperation, O2: SDTOperation) -> bool | None:
        # Whether O1 precedes O2, if that has been recorded.
        key1 = self.__operation_key(O1)
        key2 = self.__operation_key(O2)
        if key1 is None or key2 is None:
            return None
        return self.effects_relation.get((key1, key2))

    # Transformation functions.

    # Algorithm 3. Whether the effect of O1 is to the left of the effect of O2, decided by
    # where the two fall in their latest synchronization point and, when that ties, by their
    # positions in the current state, their types and their site ids.
    def precedes(self, O1: SDTOperation, O2: SDTOperation, beta1: int, beta2: int) -> bool:
        if isinstance(O1, SDTIdentityOperation) or isinstance(O2, SDTIdentityOperation):
            # An identity operation has no effect to relate, and shifting by its length of
            # zero would be a no-op anyway.
            return False
        if beta1 < beta2:
            return True
        if beta1 == beta2:
            if O1.position < O2.position:
                return True
            if O1.position == O2.position:
                if isinstance(O1, SDTInsertOperation) and isinstance(O2, SDTDeleteOperation):
                    return True
                if (
                    isinstance(O1, SDTInsertOperation)
                    and isinstance(O2, SDTInsertOperation)
                    and O1.client_id < O2.client_id
                ):
                    return True
        return False

    # Algorithm 6. The effects relation used by ET when the two operations are contextually
    # serialized, where only their position parameters are available. Oi is defined on the
    # state before O.
    def precedes_et(self, Oi: SDTOperation, O: SDTOperation) -> bool:
        if isinstance(Oi, SDTIdentityOperation) or isinstance(O, SDTIdentityOperation):
            return False
        if Oi.position < O.position:
            return True
        # At equal positions only delete against delete is true. An insert by O at the
        # position Oi deleted from is deliberately resolved the other way round, so that one
        # of the two acceptable results is picked deterministically, and insert then insert
        # and insert then delete are false as well.
        return Oi.position == O.position and isinstance(Oi, SDTDeleteOperation) and isinstance(O, SDTDeleteOperation)

    # Algorithm 2 and Algorithm 4. Include the effect of O2 in O1, where both are defined on
    # the same state.
    def IT(
        self, O1: SDTOperation, O2: SDTOperation, beta1: int | None = None, beta2: int | None = None
    ) -> SDTOperation:
        if isinstance(O1, SDTDeleteOperation) and isinstance(O2, SDTDeleteOperation) and O1.character is O2.character:
            # Two concurrent deletes of the same character; the second has nothing left to
            # do, so an identity operation is returned as in Ellis and Gibbs (1989).
            return SDTIdentityOperation(O1.client_id, O1.vector_clock, O1.position)

        if beta1 is not None and beta2 is not None:
            second_precedes = self.precedes(O2, O1, beta2, beta1)
        else:
            # Called from a transposition, where the two operations are concurrent and their
            # relation was recorded when SQIT transformed them. Section 8.1 argues this is
            # always the case; comparing positions is only a fallback.
            stored = self.stored_effects_relation(O2, O1)
            second_precedes = stored if stored is not None else self.precedes(O2, O1, 0, 0)

        if not second_precedes:
            return O1

        shift = O2.length if isinstance(O2, SDTInsertOperation) else -O2.length
        return replace(O1, position=O1.position + shift)

    # Algorithm 5. Exclude the effect of Oi from O, where Oi is defined on the state that O's
    # definition state was reached from.
    def ET(self, O: SDTOperation, Oi: SDTOperation) -> SDTOperation:
        stored = self.stored_effects_relation(Oi, O)
        precedes = stored if stored is not None else self.precedes_et(Oi, O)

        if not precedes:
            return O

        shift = -Oi.length if isinstance(Oi, SDTInsertOperation) else Oi.length
        return replace(O, position=O.position + shift)

    # State differences.

    # Algorithm 7. The effect of O relative to the state the given state difference starts
    # from, as a <beta, delta> pair: beta is the position in that earlier state and delta
    # distinguishes operations that share a beta.
    def compute_beta_delta(self, O: SDTOperation, SD: list[SDTOperation]) -> tuple[int, int]:
        # A state difference is ordered by position; reversing it gives the negative order
        # sequence of Definition 7, which is contextually serialized and can be excluded
        # from right to left without hitting the ambiguities of section 6.2.
        SQ_ne = list(reversed(SD))

        # The paper's Algorithm 7 shifts O in place as it excludes; the parameter is left
        # alone here and the running form is kept beside it.
        O_current = O

        beta: int | None = None
        delta = 0

        i = len(SQ_ne) - 1
        while i >= 0:
            current = SQ_ne[i]

            if O_current.position < current.position:
                # O is to the left of everything left in the sequence, which therefore
                # cannot shift it any further.
                beta = O_current.position
                delta = 0
                break

            if (
                isinstance(current, SDTInsertOperation)
                and isinstance(O_current, SDTInsertOperation)
                and O_current.position == current.position + current.length
            ):
                # O inserts immediately after the string current inserted. Whether it belongs
                # to that string, or goes after the character the string was inserted before,
                # can only be told by looking at the next element of the sequence.
                previous = SQ_ne[i - 1] if i - 1 >= 0 else None
                if (
                    previous is not None
                    and isinstance(previous, SDTDeleteOperation)
                    and current.position == previous.position
                ):
                    O_t = self.ET(self.ET(O_current, current), previous)
                    # Lines 8 to 10 of Algorithm 7 compare P(Ot) with P(O), which can never
                    # hold: two exclusions can only move an insert to the left. The
                    # comparison meant is the one the surrounding prose describes, against
                    # P(SQne[i]). O joins the inserted string when the exclusions leave it at
                    # the same position, and goes after the deleted character otherwise.
                    if O_t.position > current.position:
                        O_current = replace(O_current, position=O_t.position)
                        i -= 1  # The delete has been excluded too, so skip over it.
                    else:
                        beta = current.position
                        delta = O_current.position - current.position
                        break
                else:
                    beta = current.position
                    delta = O_current.position - current.position
                    break
            elif (
                isinstance(current, SDTInsertOperation)
                and current.position <= O_current.position < current.position + current.length
            ):
                # O falls inside the string current inserted, so it shares its beta.
                beta = current.position
                delta = O_current.position - current.position + (1 if isinstance(O_current, SDTDeleteOperation) else 0)
                break
            else:
                O_current = self.ET(O_current, current)

            i -= 1

        if beta is None:
            beta = O_current.position
            delta = 0

        return beta, delta

    # Algorithm 8. The net effect of SQ relative to the state it starts from, built up one
    # operation at a time.
    def build_SD(self, SQ: list[SDTOperation]) -> list[SDTOperation]:
        # A state difference is the net effect of the sequence, and an identity operation
        # contributes none, so it takes no part in one.
        SQ_net = [operation for operation in SQ if not isinstance(operation, SDTIdentityOperation)]

        if len(SQ_net) == 0:
            return []

        # SQ[1] is defined on that state already, so its position is its beta.
        SD: list[SDTOperation] = [self.__as_state_difference_entry(SQ_net[0], SQ_net[0].position)]

        for i in range(1, len(SQ_net)):
            beta, delta = self.compute_beta_delta(SQ_net[i], SD)
            self.__merge_into_SD(SD, SQ_net[i], beta, delta)

        return SD

    def __as_state_difference_entry(self, O: SDTOperation, beta: int) -> SDTOperation:
        # Position parameters in a state difference are reset to beta. Inserts lose their
        # identity because BuildSD combines the ones that share a beta; deletes keep theirs,
        # so that the recorded effects relation can still be looked up for them.
        match O:
            case SDTInsertOperation(_, _, _, characters):
                return SDTInsertOperation(SYNTHETIC_CLIENT_ID, {}, beta, list(characters))
            case SDTDeleteOperation(client_id, vector_clock, _, character):
                return SDTDeleteOperation(client_id, vector_clock, beta, character)
            case SDTIdentityOperation():
                raise AssertionError("identity operations are filtered out before a state difference is built")
            case _ as unreachable:
                assert_never(unreachable)

    def __merge_into_SD(self, SD: list[SDTOperation], O: SDTOperation, beta: int, delta: int) -> None:
        run = self.__insert_at(SD, beta)

        if run is not None and isinstance(O, SDTInsertOperation):
            # Combined into one stringwise insert, with the characters ordered by delta.
            run.characters.insert(delta, O.characters[0])
            return

        if run is not None and isinstance(O, SDTDeleteOperation) and delta >= 1:
            # O deletes a character that run inserted; the two counteract and both go.
            del run.characters[delta - 1]
            if len(run.characters) == 0:
                SD.remove(run)
            return

        entry = self.__as_state_difference_entry(O, beta)
        SD.insert(self.__position_order_index(SD, entry), entry)

    def __insert_at(self, SD: list[SDTOperation], beta: int) -> SDTInsertOperation | None:
        for entry in SD:
            if isinstance(entry, SDTInsertOperation) and entry.position == beta:
                return entry
        return None

    def __position_order_index(self, SD: list[SDTOperation], entry: SDTOperation) -> int:
        # Definition 5: ordered by position, with an insert before a delete at the same
        # position.
        index = 0
        while index < len(SD):
            existing = SD[index]
            if existing.position > entry.position:
                break
            if existing.position == entry.position and not (
                isinstance(existing, SDTInsertOperation) and isinstance(entry, SDTDeleteOperation)
            ):
                break
            index += 1
        return index

    # The integration procedure.

    # Algorithm 9. The executable form of a causally ready operation O.
    def integrate(self, O: SDTOperation, history_buffer: list[SDTOperation]) -> SDTOperation:
        HB_c = list(history_buffer)
        n = len(HB_c)

        # The first operation in the history buffer that is concurrent with O, one based.
        i = n + 1
        for index in range(n):
            if self.is_concurrent(HB_c[index], O):
                i = index + 1
                break

        if i > n:
            # Nothing concurrent, so O is already defined on the current state.
            return O

        SQ_t, p = self.transpose_r2l(O, HB_c[i - 1 :])
        HB_c = HB_c[: i - 1] + SQ_t

        k = (i - 1) + p  # Points at the leftmost operation concurrent with O.
        return self.SQIT(O, HB_c, k)

    # Algorithm 10. Reorder SQ so that everything causally preceding O comes before
    # everything concurrent with it. Returns the sequence and the one based position of the
    # leftmost operation concurrent with O.
    def transpose_r2l(self, O: SDTOperation, SQ: list[SDTOperation]) -> tuple[list[SDTOperation], int]:
        SQ_r = list(SQ)
        p = 1

        for i in range(1, len(SQ) + 1):
            if self.happened_before(SQ_r[i - 1], O):
                SQ_t = self.R2LIT(SQ_r[p - 1 : i])
                SQ_r = SQ_r[: p - 1] + SQ_t + SQ_r[i:]
                p += 1

        return SQ_r, p

    # Algorithm 11. Transpose the rightmost operation of SQ to the leftmost position.
    def R2LIT(self, SQ: list[SDTOperation]) -> list[SDTOperation]:
        SQ_new = list(SQ)
        n = len(SQ_new)

        if n == 0:
            return SQ_new

        next_O = SQ_new[n - 1]
        for i in range(n - 1, 0, -1):
            next_O = self.ET(next_O, SQ_new[i - 1])
            current_O = self.IT(SQ_new[i - 1], next_O)
            SQ_new = SQ_new[: i - 1] + [next_O, current_O] + SQ_new[i + 1 :]

        return SQ_new

    # Algorithm 14. Reorder SQ so that everything with a timestamp at or before SV comes
    # before everything else. Returns the sequence and the one based position of the
    # rightmost operation with a timestamp at or before SV.
    def transpose_l2r(self, SV: dict[int, int], SQ: list[SDTOperation]) -> tuple[list[SDTOperation], int]:
        SQ_r = list(SQ)
        n = len(SQ_r)
        r = n

        for i in range(n - 1, 0, -1):
            if not self.vector_clock_leq(SQ_r[i - 1].vector_clock, SV):
                SQ_t = self.L2RIT(SQ_r[i - 1 : r])
                SQ_r = SQ_r[: i - 1] + SQ_t + SQ_r[r:]
                r -= 1

        return SQ_r, r

    # Algorithm 15. Transpose the leftmost operation of SQ to the rightmost position.
    def L2RIT(self, SQ: list[SDTOperation]) -> list[SDTOperation]:
        SQ_new = list(SQ)
        n = len(SQ_new)

        if n == 0:
            return SQ_new

        previous_O = SQ_new[0]
        for i in range(2, n + 1):
            current_O = self.ET(SQ_new[i - 1], previous_O)
            previous_O = self.IT(previous_O, current_O)
            SQ_new = SQ_new[: i - 2] + [current_O, previous_O] + SQ_new[i:]

        return SQ_new

    # Algorithm 12. Inclusively transform O against SQ[p,n], all of which is concurrent
    # with it.
    def SQIT(self, O: SDTOperation, SQ: list[SDTOperation], p: int) -> SDTOperation:
        O_current = O

        for i in range(p, len(SQ) + 1):
            SQ_lsp = self.compute_lsp(O_current, i, SQ)
            SD = self.build_SD(SQ_lsp)

            beta_1, _ = self.compute_beta_delta(O_current, SD)
            beta_2, _ = self.compute_beta_delta(SQ[i - 1], SD)

            # Recorded before the transformation, so that a later ET between the same two
            # operations can recover the relation. IT is decided by the same two betas.
            self.store_effects_relation(O_current, SQ[i - 1], self.precedes(O_current, SQ[i - 1], beta_1, beta_2))

            O_current = self.IT(O_current, SQ[i - 1], beta_1, beta_2)

        return O_current

    # Algorithm 13. The subsequence of SQ whose net effect separates the latest
    # synchronization point of O and SQ[j] from the state SQ[j] is defined on.
    def compute_lsp(self, O: SDTOperation, j: int, SQ: list[SDTOperation]) -> list[SDTOperation]:
        SV_lsp: dict[int, int] = {}
        for client_id in O.vector_clock:
            SV_lsp[client_id] = min(O.vector_clock[client_id], SQ[j - 1].vector_clock[client_id])

        # The rightmost operation that contributed to the latest synchronization point.
        r: int | None = None
        for index in range(len(SQ) - 1, -1, -1):
            if self.vector_clock_leq(SQ[index].vector_clock, SV_lsp):
                r = index + 1
                break

        if r is None:
            # Nothing in SQ contributed to it, so the latest synchronization point is the
            # state SQ itself starts from.
            return SQ[: j - 1]

        SQ_t, i = self.transpose_l2r(SV_lsp, SQ[:r])
        SQ_t = SQ_t + SQ[r:]

        return SQ_t[i : j - 1]
