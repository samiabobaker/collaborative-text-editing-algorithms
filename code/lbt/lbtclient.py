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
from lbt.lbtmessage import EffectRelation, LBTDeletionOperation, LBTInsertionOperation, LBTMessage, LBTOperation
from unique_char.uniquechar import UniqueChar


class LBTClient(ClientDevice):
    client_id: int

    vector_clock: dict[int, int]
    state: list[UniqueChar]
    message_buffer: dict[int, list[LBTMessage]]

    history_buffer: list[LBTOperation]

    er: dict[tuple[tuple[int, int], tuple[int, int]], EffectRelation]

    def __reverse_effect(self, r: EffectRelation) -> EffectRelation:
        reverse: dict[EffectRelation, EffectRelation] = {"<": ">", ">": "<", "=": "="}

        return reverse[r]

    def op_id(self, O: LBTOperation) -> tuple[int, int]:
        return (O.client_id, O.vector_clock[O.client_id])

    def er_get(self, O1: LBTOperation, O2: LBTOperation) -> EffectRelation | None:
        return self.er.get((self.op_id(O1), self.op_id(O2)))

    def er_set(self, O1: LBTOperation, O2: LBTOperation, r: EffectRelation):
        self.er[(self.op_id(O1), self.op_id(O2))] = r
        self.er[(self.op_id(O2), self.op_id(O1))] = self.__reverse_effect(r)

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.history_buffer = []
        self.er = {}

    def set_clients(self, clients: list[LBTClient]) -> None:
        self.clients = clients
        self.vector_clock = {}
        self.message_buffer = {}
        for client in clients:
            self.vector_clock[client.client_id] = 0
            self.message_buffer[client.client_id] = []

    def execute_operation(self, O: LBTOperation):
        match O:
            case LBTInsertionOperation(_, position, character):
                self.state.insert(position, character)
            case LBTDeletionOperation(_, position):
                del self.state[position]
        self.history_buffer.append(O)

    def perform_local_insert(self, operation: ClientInsertOperation) -> None:
        self.vector_clock[self.client_id] += 1
        O = LBTInsertionOperation(self.vector_clock.copy(), operation.position, operation.character, self.client_id)
        transformed_O = self.integrate(O, self.history_buffer)
        if transformed_O is not None:
            self.execute_operation(transformed_O)

        # Send message to all other clients
        self.__send_to_other_clients(LBTMessage(self.vector_clock.copy(), O, operation))

    def perform_local_delete(self, operation: ClientDeleteOperation) -> None:
        self.vector_clock[self.client_id] += 1
        O = LBTDeletionOperation(self.vector_clock.copy(), operation.position, self.client_id)
        transformed_O = self.integrate(O, self.history_buffer)
        if transformed_O is not None:
            self.execute_operation(transformed_O)

        # Send message to all other clients
        self.__send_to_other_clients(LBTMessage(self.vector_clock.copy(), O, operation))

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

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        # Check if message from client exists, and is causally ready.
        client_message_buffer = self.message_buffer[client_id]

        if len(client_message_buffer) == 0:
            return []

        if not self.__is_causally_ready(client_message_buffer[0]):
            return []

        message = client_message_buffer.pop(0)

        transformed_op = self.integrate(message.operation, self.history_buffer)
        if transformed_op is not None:
            self.execute_operation(transformed_op)

        self.vector_clock[client_id] += 1

        return [message.causing_operation]

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                client_ids.append(client.client_id)

        return client_ids

    def can_receive_from_server(self) -> bool:
        return False

    def send_message(self, client_id: int, message: LBTMessage):
        self.message_buffer[client_id].append(message)

    def __send_to_other_clients(self, message: LBTMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)

    def __is_causally_ready(self, message: LBTMessage) -> bool:
        for client in self.clients:
            if client.client_id == message.operation.client_id:
                if message.vector_clock[client.client_id] != self.vector_clock[client.client_id] + 1:
                    return False
            elif message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                return False
        return True

    def apply_operation(self, O: LBTOperation):
        transformed_O = self.integrate(O, self.history_buffer)
        if transformed_O is not None:
            self.execute_operation(transformed_O)

    def vector_clock_leq(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return all(v1[client_id] <= v2[client_id] for client_id in v1)

    def vector_clock_concurrent(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return not self.vector_clock_leq(v1, v2) and not self.vector_clock_leq(v2, v1)

    def IT(self, O1: LBTOperation, O2: LBTOperation) -> LBTOperation | None:
        relation = self.get_effect_relation_it(O1, O2)
        if relation == "=":
            return None
        elif relation == ">":
            if isinstance(O2, LBTInsertionOperation):
                match O1:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        return LBTInsertionOperation(vector_clock, position + 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        return LBTDeletionOperation(vector_clock, position + 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)
            else:
                match O1:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        return LBTInsertionOperation(vector_clock, position - 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        return LBTDeletionOperation(vector_clock, position - 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)
        else:
            return O1

    def get_effect_relation_it(self, O1: LBTOperation, O2: LBTOperation) -> EffectRelation:
        cached_er = self.er_get(O1, O2)
        if cached_er is not None:
            return cached_er
        er = ">"
        if O1.position < O2.position:
            er = "<"
        elif O1.position == O2.position:
            if (
                isinstance(O1, LBTInsertionOperation)
                and isinstance(O2, LBTInsertionOperation)
                and O1.client_id < O2.client_id
            ):
                er = "<"
            elif isinstance(O1, LBTDeletionOperation) and isinstance(O2, LBTDeletionOperation):
                er = "="
            elif isinstance(O1, LBTInsertionOperation) and isinstance(O2, LBTDeletionOperation):
                er = "<"

        self.er_set(O1, O2, er)
        return er

    def ET(self, O1: LBTOperation, O2: LBTOperation) -> LBTOperation:
        relation = self.get_effect_relation_et(O1, O2)
        if relation == "=":
            raise ValueError("O1 and O2 are equal during ET")
        elif relation == "<":
            if isinstance(O1, LBTInsertionOperation):
                match O2:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        return LBTInsertionOperation(vector_clock, position - 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        return LBTDeletionOperation(vector_clock, position - 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)
            else:
                match O2:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        return LBTInsertionOperation(vector_clock, position + 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        return LBTDeletionOperation(vector_clock, position + 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)
        else:
            return O2

    def get_effect_relation_et(self, O1: LBTOperation, O2: LBTOperation) -> EffectRelation:
        cached_er = self.er_get(O1, O2)
        if cached_er is not None:
            return cached_er
        if O1.position < O2.position:
            er = "<"
        elif O1.position > O2.position:
            er = ">"
        else:
            match O1, O2:
                case LBTInsertionOperation(), LBTInsertionOperation():
                    er = ">"
                case LBTDeletionOperation(), LBTDeletionOperation():
                    er = "<"
                case LBTDeletionOperation(), LBTInsertionOperation():
                    er = ">"
                case LBTInsertionOperation(), LBTDeletionOperation():
                    er = "="
                case _ as unreachable:
                    assert_never(unreachable)
        self.er_set(O1, O2, er)
        return er

    def ETSQ(self, O: LBTOperation, sequence: list[LBTOperation]) -> LBTOperation:
        transformed_O = O
        broke_at = 0
        for i in range(len(sequence) - 1, -1, -1):
            relation = self.get_effect_relation_et(sequence[i], transformed_O)
            transformed_O = self.ET(sequence[i], transformed_O)
            if relation == "<":
                broke_at = i
                break
        for j in range(broke_at - 1, -1, -1):
            if isinstance(sequence[j], LBTInsertionOperation):
                match transformed_O:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        transformed_O = LBTInsertionOperation(vector_clock, position - 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        transformed_O = LBTDeletionOperation(vector_clock, position - 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)
            else:
                match transformed_O:
                    case LBTInsertionOperation(vector_clock, position, character, client_id):
                        transformed_O = LBTInsertionOperation(vector_clock, position + 1, character, client_id)
                    case LBTDeletionOperation(vector_clock, position, client_id):
                        transformed_O = LBTDeletionOperation(vector_clock, position + 1, client_id)
                    case _ as unreachable:
                        assert_never(unreachable)

        return transformed_O

    def ITSQ(self, O: LBTOperation, sequence: list[LBTOperation]) -> LBTOperation | None:
        transformed_O = O
        for op in sequence:
            transformed_O = self.IT(transformed_O, op)
            if transformed_O is None:
                break
        return transformed_O

    def transpose_prec_con(
        self, O: LBTOperation, sequence: list[LBTOperation]
    ) -> tuple[list[LBTOperation], list[LBTOperation]]:
        sequence_h: list[LBTOperation] = []
        sequence_c: list[LBTOperation] = []

        for op in sequence:
            if self.vector_clock_concurrent(op.vector_clock, O.vector_clock):
                sequence_c.append(op)
            else:
                o_i, sequence_c = self.transpose_OS_q(sequence_c, op)
                sequence_h.append(o_i)
        return sequence_h, sequence_c

    def transpose_OS_q(self, sequence: list[LBTOperation], O: LBTOperation) -> tuple[LBTOperation, list[LBTOperation]]:
        transformed_O = O
        transformed_sequence = list(sequence)

        for i in range(len(sequence) - 1, -1, -1):
            transformed_O, transformed_sequence[i] = self.transpose(transformed_sequence[i], transformed_O)
        return transformed_O, transformed_sequence

    def transpose(self, O2: LBTOperation, O1: LBTOperation) -> tuple[LBTOperation, LBTOperation]:
        relation = self.get_effect_relation_et(O2, O1)
        if relation == "=":
            return O1, O2
        else:
            transformed_O1 = self.ET(O2, O1)
            transformed_O2 = self.IT(O2, transformed_O1)
            assert transformed_O2 is not None
            return transformed_O1, transformed_O2

    def transpose_ins_del(self, sequence: list[LBTOperation]) -> tuple[list[LBTOperation], list[LBTOperation]]:
        sequence_i: list[LBTOperation] = []
        sequence_d: list[LBTOperation] = []

        for op in sequence:
            if isinstance(op, LBTDeletionOperation):
                sequence_d.append(op)
            else:
                o_i, sequence_d = self.transpose_OS_q(sequence_d, op)
                sequence_i.append(o_i)
        return sequence_i, sequence_d

    def build_ETSOS(self, sequence: list[LBTOperation]) -> list[LBTOperation]:
        if len(sequence) < 1:
            return sequence

        transformed_sequence: list[LBTOperation] = [sequence[0]]

        for i in range(1, len(sequence)):
            transformed_O = sequence[i]
            flag = False
            for j in range(len(transformed_sequence) - 1, -1, -1):
                if flag:
                    self.er_set(transformed_sequence[j], transformed_O, "<")
                elif self.get_effect_relation_et(transformed_sequence[j], transformed_O) in ("<", "="):
                    transformed_sequence = (
                        transformed_sequence[: j + 1] + [transformed_O] + transformed_sequence[j + 1 :]
                    )
                    flag = True
                else:
                    transformed_O, transformed_sequence[j] = self.transpose(transformed_sequence[j], transformed_O)
            if not flag:
                transformed_sequence = [transformed_O] + transformed_sequence
        return transformed_sequence

    def integrate(self, O: LBTOperation, history_buffer: list[LBTOperation]) -> LBTOperation | None:
        sequence_h, sequence_c = self.transpose_prec_con(O, history_buffer)
        if sequence_c == []:
            return O
        if isinstance(O, LBTDeletionOperation):
            return self.ITSQ(O, sequence_c)
        else:
            sequence_h2 = self.build_ETSOS(sequence_h)
            _, sequence_hd = self.transpose_ins_del(sequence_h2)
            transformed_O = self.ETSQ(O, sequence_hd)
            sequence = self.build_ETSOS(sequence_hd + sequence_c)
            sequence_i, sequence_d = self.transpose_ins_del(sequence)
            return self.ITSQ(transformed_O, sequence_i + sequence_d)
