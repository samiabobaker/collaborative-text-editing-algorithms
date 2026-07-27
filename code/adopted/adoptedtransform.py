from abc import ABC, abstractmethod
from adopted.adoptedmessage import AdOPTedOperation, AdOPTedDeletionOperation, AdOPTedInsertionOperation, AdOPTedNoOperation
from unique_char.uniquechar import UniqueChar
from dataclasses import dataclass
from typing import assert_never

class AdOPTedTransform(ABC):
    @abstractmethod
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        pass

    @abstractmethod
    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        pass

    @abstractmethod
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        pass



class EllisTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)
    
    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)
    
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i > j:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif x == y:
                    return AdOPTedNoOperation()
                elif pr1 > pr2:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                 if i < j:
                     return AdOPTedDeletionOperation(i, pr1, {})
                 else:
                     return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)

class ResselTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)
    
    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)
    
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if (i < j) or (i == j and pr1 < pr2):
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                 if i < j:
                     return AdOPTedDeletionOperation(i, pr1, {})
                 else:
                     return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i <= j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)

class IMORTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)
    
    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, position, set(), set(), vector_clock)
    
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, position, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedInsertionOperation(j, y, pr2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i > j:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif pr1 < pr2:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif pr1 > pr2:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                elif x.char < y.char:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif x.char > y.char:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y):
                 if i < j:
                     return AdOPTedDeletionOperation(i, pr1, {})
                 else:
                     return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1), AdOPTedDeletionOperation(j, pr2):
                if i > j:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)

class SuleimanTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)
    
    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)
    
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedInsertionOperation(j, y, pr2, b2, a2):
                if i < j:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1, {})
                elif i > j:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, b1, a1, {})
                elif len(b1.intersection(a2)) != 0:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, b1, a1, {})
                elif len(a1.intersection(b2)) != 0:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1, {})
                elif x.char < y.char:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1, {})
                elif x.char > y.char:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, b1, a1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y, b2, a2):
                 if i < j:
                     return AdOPTedDeletionOperation(i, pr1, {})
                 else:
                     return AdOPTedDeletionOperation(i + 1, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedDeletionOperation(j, pr2):
                if i > j:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, b1.union({O2}), a1, {})
                else:
                    return AdOPTedInsertionOperation(i, x, pr1, b1, a1.union({O2}), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i < j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i - 1, pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)



class TombstoneTransform(AdOPTedTransform):
    state: list[tuple[UniqueChar, bool]]

    def view_to_model(self, view_pos: int) -> int:
        n = 1
        j = 1
        while j <= len(self.state) and (n < view_pos or not self.state[j][1]):
            if self.state[j][1]:
                n += 1
            j += 1
        return j

class TM11Transform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.__transform(O1, O2), self.__transform(O2, O1)

    def get_insert_with_priority(self, position: int, character: UniqueChar, client_id: int, vector_clock: dict[int, int]) -> AdOPTedInsertionOperation:
        return AdOPTedInsertionOperation(position, character, client_id, set(), set(), vector_clock)
    
    def get_delete_with_priority(self, position: int, client_id: int, vector_clock: dict[int, int]) -> AdOPTedDeletionOperation:
        return AdOPTedDeletionOperation(position, client_id, vector_clock)

    def __transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        match O1, O2:
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedInsertionOperation(j, y, pr2, b2, a2):
                if i < j or (i == j and pr1 > pr2):
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                else:
                    return AdOPTedInsertionOperation(i + 1, x, pr1, set(), set(), {})
            case AdOPTedDeletionOperation(i, pr1), AdOPTedInsertionOperation(j, y, b2, a2):
                if i + 1 <= j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i > j:
                    return AdOPTedDeletionOperation(i + 1, pr1, {})
                else:
                    return AdOPTedDeletionOperation(i, pr1, {})
            case AdOPTedInsertionOperation(i, x, pr1, b1, a1), AdOPTedDeletionOperation(j, pr2):
                if i <= j:
                    return AdOPTedInsertionOperation(i, x, pr1, set(), set(), {})
                elif i >= j + 1:
                    return AdOPTedInsertionOperation(i - 1, x, pr1, set(), set(), {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedDeletionOperation(i, pr1), AdOPTedDeletionOperation(j, pr2):
                if i + 1 <= j:
                    return AdOPTedDeletionOperation(i, pr1, {})
                elif i >= j + 1:
                    return AdOPTedDeletionOperation(i-1,pr1, {})
                else:
                    return AdOPTedNoOperation()
            case AdOPTedNoOperation(), _:
                return AdOPTedNoOperation()
            case oper, AdOPTedNoOperation():
                return oper
            case _ as unreachable:
                assert_never(unreachable)

#State difference can be string-wise
@dataclass
class SDInsert:
    position: int
    string: list[UniqueChar]

@dataclass
class SDDelete:
    position: int

SD = list[SDInsert | SDDelete]

class SDTTransform(AdOPTedTransform):
    def apply_transform(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> tuple[AdOPTedOperation, AdOPTedOperation]:
        return self.IT(O1, O2), self.IT(O2, O1)

    def IT(self, O1: AdOPTedOperation, O2: AdOPTedOperation) -> AdOPTedOperation:
        if isinstance(O1, AdOPTedNoOperation):
            return AdOPTedNoOperation()
        if isinstance(O2, AdOPTedNoOperation):
            return O1
        if self.compare_ops_for_IT(O2, O1): #Is O2 < O1?
            match O1:
                case AdOPTedInsertionOperation(i, x, pr1):
                    return AdOPTedInsertionOperation(i+1, x, pr1, set(), set())
                case AdOPTedDeletionOperation(i, pr1):
                    return AdOPTedDeletionOperation(i - 1, pr1)
                case _ as unreachable:
                    assert_never(unreachable)
        else:
            return O1

    def compare_ops_for_IT(self, O1: AdOPTedInsertionOperation | AdOPTedDeletionOperation, O2: AdOPTedInsertionOperation | AdOPTedDeletionOperation) -> bool:
        beta_O1 = self.beta_lsp(O1)
        beta_O2 = self.beta_lsp(O2)

        if beta_O1 < beta_O2:
            return True
        elif beta_O1 == beta_O2:
            if O1.position < O2.position:
                return True
            elif O1.position == O2.position:
                if isinstance(O1, AdOPTedInsertionOperation) and isinstance(O2, AdOPTedDeletionOperation):
                    return True
                elif isinstance(O1, AdOPTedInsertionOperation) and isinstance(O2, AdOPTedInsertionOperation) and O1.priority < O2.priority:
                    return True
        return False
    
    def compare_ops_for_ET(self, O1: SDInsert | SDDelete, O2: AdOPTedInsertionOperation | AdOPTedDeletionOperation) -> bool:
        if O1.position < O2.position:
            return True
        if O1.position == O2.position:
            if isinstance(O1, SDInsert) and isinstance(O2, AdOPTedInsertionOperation):
                return False
            elif isinstance(O1, SDDelete) and isinstance(O2, AdOPTedDeletionOperation):
                return True 
            elif isinstance(O1, SDDelete) and isinstance(O2, AdOPTedInsertionOperation):
                return False
        return False
    

    #Compute beta_S0(O)
    def compute_beta_delta(self, O: AdOPTedInsertionOperation | AdOPTedDeletionOperation, SD: SD) -> tuple[int, int]:
        SQ_ne = self.build_SQ_ne(SD)
        i = len(SQ_ne) - 1
        while i >= 1:
            SQ_ne_i = SQ_ne[i]
            if O.position < SQ_ne_i.position:
                return (O.position, 0)
            elif isinstance(SQ_ne_i, SDInsert) and isinstance(O, AdOPTedInsertionOperation) and O.position == SQ_ne_i.position + len(SQ_ne_i.string):
                if isinstance(SQ_ne[i-1], SDDelete) and SQ_ne[i].position == SQ_ne[i-1]:
                    O_t = self.ET(self.ET(O, SQ_ne[i]), SQ_ne[i-1])
                    if O_t.position > O.position:
                        O = AdOPTedInsertionOperation(O_t.position, O.character, O.priority, O.b, O.a)
                        i -= 1
                    else:
                        return (SQ_ne[i].position, O.position - SQ_ne[i].position)
                else:
                    return (SQ_ne[i].position, O.position - SQ_ne[i].position)
            elif isinstance(SQ_ne_i, SDInsert) and SQ_ne_i.position <= O.position and O.position < SQ_ne_i.position + len(SQ_ne_i.string):
                if isinstance(O, AdOPTedInsertionOperation):
                    return (SQ_ne_i.position, O.position - SQ_ne_i.position)
                else:
                    return (SQ_ne_i.position, O.position - SQ_ne_i.position + 1)
            else:
                O = self.ET(O, SQ_ne[i])
            i-=1
        return (O.position, 0)
                    
    def ET(self, O1: AdOPTedInsertionOperation | AdOPTedDeletionOperation, O2: SDInsert | SDDelete) -> AdOPTedInsertionOperation | AdOPTedDeletionOperation:
        if self.compare_ops_for_ET(O2, O1):
            match O1,O2:
                case AdOPTedInsertionOperation(i, x,pr1), SDInsert():
                    return AdOPTedInsertionOperation(i-1,x,pr1,set(),set())
                case AdOPTedDeletionOperation(i, x), SDInsert():
                    return AdOPTedDeletionOperation(i-1,x)
                case AdOPTedInsertionOperation(i, x,pr1), SDDelete():
                    return AdOPTedInsertionOperation(i+1,x,pr1,set(),set())
                case AdOPTedDeletionOperation(i, x), SDDelete():
                    return AdOPTedDeletionOperation(i+1,x)
                case _ as unreachable:
                    assert_never(unreachable)
    def build_SQ_ne(self, SD: SD) -> SD:
        pass

    def build_SD(self, SQ: list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]) -> SD:
        SD: SD = []

        betas: list[int] = []

        match SQ[0]:
            case AdOPTedInsertionOperation(i, x):
                SD.append(SDInsert(i, [x]))
            case AdOPTedDeletionOperation(i):
                SD.append(SDDelete(i))
        betas.append(SQ[0].position)

        for i in range(1, len(SQ)):
            beta, delta = self.compute_beta_delta(SQ[i], SD)

            betas.append(beta)

            for index, O_j in enumerate(SD):
                if not isinstance(O_j, SDInsert):
                    continue
                if O_j.position != beta:
                    continue
                
                match SQ[i]:
                    case AdOPTedInsertionOperation(i, x):
                        O_j.string.insert(delta, x)
                    case AdOPTedDeletionOperation(i):
                        del O_j.string[delta]

            index = 0
            while index < len(SD) and SD[index].position < SQ[i].position:
                index += 1
            
            match SQ[i]:
                case AdOPTedInsertionOperation(i, x):
                    SD.insert(index, SDInsert(i, [x]))
                case AdOPTedDeletionOperation(i):
                    SD.insert(index, SDDelete(i))
        return SD
    

    def compare_vector_clocks(self, v1: dict[int, int], v2: dict[int, int]) -> bool:
        for i in v1:
            if v1[i] > v2[i]:
                return False
        return True

    def compute_lsp(self, O: AdOPTedOperation, j: int, SQ: list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]) -> list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]:
        SV_lsp: dict[int, int] = {}
        for i in O.vector_clock:
            SV_lsp[i] = min(O.vector_clock[i], SQ[j].vector_clock[i])


        for r in range(len(SQ)):
            if not self.compare_vector_clocks(SQ[r].vector_clock, SV_lsp):
                continue
            satisfies = True
            for s in range(r+1, len(SQ)):
                O_s = SQ[s]
                if self.compare_vector_clocks(O_s.vector_clock, SV_lsp):
                    satisfies = False
                    break
            if not satisfies:
                continue
            
            SQ_t, i = self.transposeL2R(SV_lsp, SQ[:r])
            SQ_t += SQ[r:]
            return list(SQ_t[i+1:j])
    
        return list(SQ[:j])

    def transposeL2R(self, SV: dict[int, int], SQ: list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]) -> tuple[list[AdOPTedInsertionOperation | AdOPTedDeletionOperation], int]:
        SQ_r = list(SQ)
        r = len(SQ) - 1
        for i in range(len(SQ),-1,-1):
            if not self.compare_vector_clocks(SQ_r[i].vector_clock,SV):
                SQ_t = self.L2RIT(SQ_r[i:r+1])
                SQ_r = SQ_r[:i] + SQ_t + SQ_r[r+1:]
                r -= 1
        return SQ_r, r

    def L2RIT(self, SQ: list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]) -> list[AdOPTedInsertionOperation | AdOPTedDeletionOperation]:
        SQ = list(SQ)
        prev = SQ[0]
        for i in range(1,len(SQ)):
            match prev:
                case AdOPTedInsertionOperation(i, x):
                    current = self.ET(SQ[i], SDInsert(i, [x]))
                case AdOPTedDeletionOperation(i):
                    current = self.ET(SQ[i], SDDelete(i))
                case _ as unreachable:
                    assert_never(unreachable)
            prev = self.IT(prev, current)
            assert isinstance(prev, AdOPTedInsertionOperation | AdOPTedDeletionOperation)
            SQ = SQ[:i-1] + [current,prev] + SQ[i+1:]
        return SQ


