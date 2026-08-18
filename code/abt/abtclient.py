from dataclasses import dataclass, replace
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
from unique_char.uniquechar import UniqueChar


@dataclass
class ABTInsertOperation:
    character: UniqueChar
    position: int
    client_id: int

@dataclass
class ABTDeleteOperation:
    position: int
    client_id: int

ABTOperation = ABTInsertOperation | ABTDeleteOperation

@dataclass
class ABTSequenceEntry:
    vector_clock: dict[int, int]
    operation: ABTOperation

@dataclass
class ABTMessage:
    vector_clock: dict[int, int]
    operation: ABTOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation

ABTSequence = list[ABTSequenceEntry]

class ABTClient(ClientDevice):
    client_id: int
    vector_clock: dict[int, int]
    state: list[UniqueChar]

    Hi: ABTSequence
    Hd: ABTSequence


    H: list[ABTOperation]

    message_buffer: dict[int, list[ABTMessage]]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self.Hi = []
        self.Hd = []

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from(self) -> list[int]:
            client_ids: list[int] = []
            for client in self.clients:
                client_message_buffer = self.message_buffer[client.client_id]
                if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0]):
                    client_ids.append(client.client_id)
            
            return client_ids
    
    def can_receive_from_server(self) -> bool:
        return False

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
            match operation:
                case ClientInsertOperation(client_id, position, character):
                    self.integrate_local(ABTInsertOperation(character, position, client_id), operation)
                    return [operation]
                case ClientDeleteOperation(client_id, position, character):
                    self.integrate_local(ABTDeleteOperation(position, client_id), operation)
                    return [operation]
                case ClientReceiveFromServerOperation():
                    return []
                case ClientReceiveFromClientOperation(_, sender_client_id):
                    return self.receive_from_client(sender_client_id)
                case ClientTimestepOperation():
                    return []
                case _ as unreachable:
                    assert_never(unreachable)


    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
    
            if len(client_message_buffer) == 0:
                return []
            
            if not self.__is_causally_ready(client_message_buffer[0]):
                return []
            
            message = client_message_buffer.pop(0)
    
            self.integrate_remote(ABTSequenceEntry(message.vector_clock, message.operation))
    
            return [message.causing_operation]

    def __is_causally_ready(self, message: ABTMessage) -> bool:
            sender = message.operation.client_id
            if message.vector_clock[sender] != self.vector_clock[sender] + 1:
                return False
            for client in self.clients:
                if client.client_id != sender and message.vector_clock[client.client_id] > self.vector_clock[client.client_id]:
                    return False
            return True
    
    

    def set_clients(self, clients: list[ABTClient]) -> None:
            self.clients = clients
            self.vector_clock = {}
            self.message_buffer = {}
            for client in clients:
                self.vector_clock[client.client_id] = 0
                self.message_buffer[client.client_id] = []

    def __send_to_other_clients(self, message: ABTMessage) -> None:
            for client in self.clients:
                if client.client_id == self.client_id:
                    continue
                client.send_message(self.client_id, message)


    def send_message(self, client_id: int, message: ABTMessage):
        self.message_buffer[client_id].append(message)


    def __execute(self, operation: ABTOperation):
        match operation:
            case ABTInsertOperation(character, position):
                self.state.insert(position, character)
            case ABTDeleteOperation(position):
                del self.state[position]
            case _ as unreachable:
                assert_never(unreachable)

    def integrate_local(self, O: ABTOperation, causing_operation: ClientInsertOperation | ClientDeleteOperation):
        self.__execute(O)
        self.vector_clock[self.client_id] += 1
        entry = ABTSequenceEntry(self.vector_clock.copy(), O)
        transformed_O, self.Hi, self.Hd = self.update_HL(entry, self.Hi, self.Hd)
        self.__send_to_other_clients(ABTMessage(transformed_O.vector_clock, transformed_O.operation, causing_operation))


    def integrate_remote(self, O: ABTSequenceEntry):
        transformed_O, self.Hi, self.Hd = self.update_HR(O, self.Hi, self.Hd)
        if transformed_O is not None:
            self.__execute(transformed_O)
        self.vector_clock[O.operation.client_id] += 1

    def swap(self, O1: ABTOperation, O2: ABTOperation) -> tuple[ABTOperation, ABTOperation]:
        transformed_O1 = replace(O1)
        transformed_O2 = replace(O2)
        if transformed_O1.position > transformed_O2.position:
            if isinstance(transformed_O2, ABTInsertOperation):
                transformed_O1 = replace(transformed_O1, position=transformed_O1.position - 1)
            else:
                transformed_O1 = replace(transformed_O1, position=transformed_O1.position + 1)
        elif transformed_O1.position == transformed_O2.position:
            if isinstance(transformed_O1, ABTDeleteOperation) and isinstance(transformed_O2, ABTDeleteOperation):
                transformed_O1 = replace(transformed_O1, position=transformed_O1.position + 1)
            elif isinstance(transformed_O1, ABTDeleteOperation) and isinstance(transformed_O2, ABTInsertOperation):
                raise ValueError("O1 depends on O2")
            elif isinstance(transformed_O1, ABTInsertOperation) and isinstance(transformed_O2, ABTInsertOperation):
                transformed_O2 = replace(transformed_O2, position=transformed_O2.position+1)
            else:
                transformed_O2 = replace(transformed_O2, position=transformed_O2.position+1)
        else:
            if isinstance(transformed_O1, ABTInsertOperation):
                transformed_O2 = replace(transformed_O2, position=transformed_O2.position+1)
            else:
                transformed_O2 = replace(transformed_O2, position=transformed_O2.position-1)
        return transformed_O1, transformed_O2


    def ET(self, O1: ABTOperation, O2: ABTOperation) -> ABTOperation:
        if O2.position < O1.position:
            if isinstance(O2, ABTInsertOperation):
                return replace(O1, position=O1.position-1)
            else:
                return replace(O1, position=O1.position+1)
        elif O2.position == O1.position:
            if isinstance(O2, ABTDeleteOperation) and isinstance(O1, ABTDeleteOperation):
                return replace(O1, position=O1.position+1)
            elif isinstance(O1, ABTDeleteOperation) and isinstance(O2, ABTInsertOperation):
                raise ValueError("O1 depends on O2")
        return O1

    def IT(self, O1: ABTOperation, O2: ABTOperation) -> ABTOperation | None:
        if O2.position < O1.position:
            if isinstance(O2, ABTInsertOperation):
                return replace(O1, position=O1.position+1)
            else:
                return replace(O1, position=O1.position-1)
        elif O2.position == O1.position:
            if isinstance(O2, ABTInsertOperation) and isinstance(O1, ABTDeleteOperation) or isinstance(O2, ABTInsertOperation) and isinstance(O1, ABTInsertOperation) and O2.client_id < O1.client_id:
                return replace(O1, position=O1.position+1)
            elif isinstance(O2, ABTDeleteOperation) and isinstance(O1, ABTDeleteOperation):
                return None
        return replace(O1)

    def vector_clock_leq(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return all(v1[client_id] <= v2[client_id] for client_id in v1)
    
    def happened_before(self, entry: ABTSequenceEntry, vector_clock: dict[int, int]) -> bool:
        site = entry.operation.client_id
        return vector_clock[site] >= entry.vector_clock[site]

    def is_concurrent(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        return not self.vector_clock_leq(v1, v2) and not self.vector_clock_leq(v2, v1)


    def convert_to_HC(self, O: ABTOperation, vector_clock: dict[int, int], sequence: ABTSequence) -> tuple[ABTSequence, ABTSequence]:
        sequence_h : ABTSequence = []
        sequence_c : ABTSequence = []

        sequence = [replace(e) for e in sequence]

        for i in range(len(sequence)):
            if not self.happened_before(sequence[i], vector_clock):
                sequence_c.append(sequence[i])
            else:
                for k in range(len(sequence_c) - 1, -1, -1):
                    sequence[i].operation, sequence_c[k].operation = self.swap(sequence[i].operation, sequence_c[k].operation)
                sequence_h.append(sequence[i])
        return sequence_h, sequence_c

    def update_HL(self, O: ABTSequenceEntry, Hi: ABTSequence, Hd: ABTSequence) -> tuple[ABTSequenceEntry, ABTSequence, ABTSequence]:
        transformed_O = replace(O)
        transformed_Hi = list(Hi)
        transformed_Hd = [replace(e) for e in Hd]
        for i in range(len(Hd) - 1, -1, -1):
            transformed_O.operation, transformed_Hd[i].operation = self.swap(transformed_O.operation, transformed_Hd[i].operation)
        if isinstance(O.operation, ABTDeleteOperation):
            transformed_Hd = list(Hd) + [O]
        else:
            transformed_Hi = transformed_Hi + [transformed_O]
        return transformed_O, transformed_Hi, transformed_Hd

    def ITSQ(self, O: ABTOperation, sequence: ABTSequence) -> ABTOperation | None:
        transformed_O = O
        for entry in sequence:
            transformed_O = self.IT(transformed_O, entry.operation)
            if transformed_O is None:
                break
        return transformed_O


    def update_HR(self, O: ABTSequenceEntry, Hi: ABTSequence, Hd: ABTSequence) -> tuple[ABTSequenceEntry, ABTSequence, ABTSequence]:
        transformed_Hd = [replace(e) for e in Hd]
        transformed_Hi = list(Hi)

        _, Hic = self.convert_to_HC(O.operation, O.vector_clock, Hi)
        Opp = self.ITSQ(O.operation, Hic)
        Op = self.ITSQ(Opp, Hd)
        if Op is None:
            return Op, Hi, Hd
        elif isinstance(Op, ABTDeleteOperation):
            transformed_Hd.append(ABTSequenceEntry(O.vector_clock, Op))
        else:
            Ox = Opp
            for k in range(len(Hd)):
                Oy = Ox
                Ox = self.IT(Ox, Hd[k].operation)
                transformed_Hd[k].operation = self.IT(transformed_Hd[k].operation, Oy)
            transformed_Hi.append(ABTSequenceEntry(O.vector_clock, Opp))
        return Op, transformed_Hi, transformed_Hd