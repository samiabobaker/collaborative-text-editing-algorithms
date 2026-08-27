from dataclasses import dataclass
from typing import Literal

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar

EasySyncOpcode = Literal["", "=", "+", "-"]


@dataclass
class EasySyncOp:
    opcode: EasySyncOpcode
    chars: int
    inserted_chars: list[UniqueChar] | None


@dataclass
class EasySyncChangeset:
    old_length: int
    new_length: int
    ops: list[EasySyncOp]
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]

    def is_identity(self) -> bool:
        return self.old_length == self.new_length and self.ops == []


def identity(length: int) -> EasySyncChangeset:
    return EasySyncChangeset(length, length, [], [])


def copy_op(op1: EasySyncOp, op2: EasySyncOp | None = None) -> EasySyncOp:
    if op2 is None:
        op2 = EasySyncOp("", 0, None)
    op2.opcode = op1.opcode
    op2.chars = op1.chars
    if op1.inserted_chars is None:
        op2.inserted_chars = None
    else:
        op2.inserted_chars = list(op1.inserted_chars)
    return op2


def slicer_zipper_func(att_op: EasySyncOp, cs_op: EasySyncOp) -> EasySyncOp:
    op_out = EasySyncOp("", 0, None)
    if att_op.opcode == "":
        copy_op(cs_op, op_out)
        cs_op.opcode = ""
    elif cs_op.opcode == "" or att_op.opcode == "-":
        copy_op(att_op, op_out)
        att_op.opcode = ""
    elif cs_op.opcode == "+":
        copy_op(cs_op, op_out)
        cs_op.opcode = ""
    else:
        mappings: dict[EasySyncOpcode, dict[EasySyncOpcode, EasySyncOpcode]] = {
            "+": {"-": "", "=": "+"},
            "=": {"-": "-", "=": "="},
        }
        op_out.opcode = mappings[att_op.opcode][cs_op.opcode]

        if att_op.chars < cs_op.chars:
            fully_consumed_op, partially_consumed_op = att_op, cs_op
        else:
            fully_consumed_op, partially_consumed_op = cs_op, att_op
        op_out.chars = fully_consumed_op.chars
        if att_op.opcode == "+":
            assert att_op.inserted_chars is not None
            if op_out.opcode == "+":
                op_out.inserted_chars = att_op.inserted_chars[: op_out.chars]
            att_op.inserted_chars = att_op.inserted_chars[op_out.chars :]
        partially_consumed_op.chars -= fully_consumed_op.chars
        if partially_consumed_op.chars == 0:
            partially_consumed_op.opcode = ""
        fully_consumed_op.opcode = ""
    return op_out


def follow_zipper(
    op1: EasySyncOp, op2: EasySyncOp, reverse_insert_order: bool, old_pos: int, new_len: int
) -> tuple[EasySyncOp, int, int]:
    op_out = EasySyncOp("", 0, None)

    chars1_index = 0
    chars2_index = 0

    if op1.opcode == "+" or op2.opcode == "+":
        if op2.opcode != "+":
            which_to_do = 1
        elif op1.opcode != "+":
            which_to_do = 2
        else:
            which_to_do = 2 if reverse_insert_order else 1

        if which_to_do == 1:
            chars1_index += op1.chars
            op_out.opcode = "="
            op_out.chars = op1.chars
            op1.opcode = ""
        else:
            chars2_index += op2.chars
            copy_op(op2, op_out)
            op2.opcode = ""

    elif op1.opcode == "-":
        if not op2.opcode:
            op1.opcode = ""
        elif op1.chars <= op2.chars:
            op2.chars -= op1.chars
            op1.opcode = ""
            if op2.chars == 0:
                op2.opcode = ""
        else:
            op1.chars -= op2.chars
            op2.opcode = ""
    elif op2.opcode == "-":
        copy_op(op2, op_out)
        if op1.opcode == "":
            op2.opcode = ""
        elif op2.chars <= op1.chars:
            op1.chars -= op2.chars
            op2.opcode = ""
            if op1.chars == 0:
                op1.opcode = ""
        else:
            op_out.chars = op1.chars
            op2.chars -= op1.chars
            op1.opcode = ""
    elif op1.opcode == "":
        copy_op(op2, op_out)
        op2.opcode = ""
    elif op2.opcode == "":
        op1.opcode = ""
    else:
        op_out.opcode = "="
        if op1.chars <= op2.chars:
            op_out.chars = op1.chars
            op2.chars -= op1.chars
            op1.opcode = ""
            if op2.chars == 0:
                op2.opcode = ""
        else:
            op_out.chars = op2.chars
            op1.chars -= op2.chars
            op2.opcode = ""

    match op_out.opcode:
        case "=":
            old_pos += op_out.chars
            new_len += op_out.chars
        case "-":
            old_pos += op_out.chars
        case "+":
            new_len += op_out.chars
        case "":
            pass

    return op_out, old_pos, new_len


def apply_zip_follow(ops1: list[EasySyncOp], ops2: list[EasySyncOp], reverse_insert_order: bool):
    ops1 = [copy_op(op) for op in ops1]
    ops2 = [copy_op(op) for op in ops2]

    old_pos = 0
    new_len = 0

    assem: list[EasySyncOp] = []
    ops1_index = 0
    ops2_index = 0
    while ops1_index < len(ops1) or ops2_index < len(ops2):
        if ops1_index < len(ops1) and ops1[ops1_index].opcode == "":
            ops1_index += 1
        if ops2_index < len(ops2) and ops2[ops2_index].opcode == "":
            ops2_index += 1
        ops1_value = ops1[ops1_index] if ops1_index < len(ops1) else EasySyncOp("", 0, None)
        ops2_value = ops2[ops2_index] if ops2_index < len(ops2) else EasySyncOp("", 0, None)
        op_out, old_pos, new_len = follow_zipper(ops1_value, ops2_value, reverse_insert_order, old_pos, new_len)
        if op_out.opcode != "":
            assem.append(op_out)
    return assem, old_pos, new_len


def apply_zip(ops1: list[EasySyncOp], ops2: list[EasySyncOp]):
    ops1 = [copy_op(op) for op in ops1]
    ops2 = [copy_op(op) for op in ops2]

    assem: list[EasySyncOp] = []
    ops1_index = 0
    ops2_index = 0
    while ops1_index < len(ops1) or ops2_index < len(ops2):
        if ops1_index < len(ops1) and ops1[ops1_index].opcode == "":
            ops1_index += 1
        if ops2_index < len(ops2) and ops2[ops2_index].opcode == "":
            ops2_index += 1
        ops1_value = ops1[ops1_index] if ops1_index < len(ops1) else EasySyncOp("", 0, None)
        ops2_value = ops2[ops2_index] if ops2_index < len(ops2) else EasySyncOp("", 0, None)
        op_out = slicer_zipper_func(ops1_value, ops2_value)
        if op_out.opcode != "":
            assem.append(op_out)
    return assem


def follow(cs1: EasySyncChangeset, cs2: EasySyncChangeset, reverse_insert_order: bool) -> EasySyncChangeset:
    len1 = cs1.old_length
    len2 = cs2.old_length
    assert len1 == len2

    old_len = cs1.new_length

    new_ops, old_pos, new_len = apply_zip_follow(cs1.ops, cs2.ops, reverse_insert_order)

    new_len += old_len - old_pos

    return EasySyncChangeset(old_len, new_len, new_ops, cs2.causing_operations)


def compose(cs1: EasySyncChangeset, cs2: EasySyncChangeset) -> EasySyncChangeset:
    len1 = cs1.old_length
    len2 = cs2.old_length
    assert len2 == cs2.old_length
    len3 = cs2.new_length

    new_ops = apply_zip(cs1.ops, cs2.ops)

    return EasySyncChangeset(len1, len3, new_ops, cs1.causing_operations + cs2.causing_operations)


def apply_to_text(state: list[UniqueChar], cs: EasySyncChangeset):
    new_state: list[UniqueChar] = []

    assert len(state) == cs.old_length
    index = 0
    for op in cs.ops:
        match op.opcode:
            case "":
                pass
            case "+":
                assert op.inserted_chars is not None
                new_state.extend(op.inserted_chars)
            case "-":
                index += op.chars
            case "=":
                new_state.extend(state[index : index + op.chars])
                index += op.chars
    new_state.extend(state[index:])
    assert len(new_state) == cs.new_length
    return new_state
