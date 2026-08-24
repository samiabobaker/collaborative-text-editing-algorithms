from __future__ import annotations

from typing import Literal, assert_never

from sharedb.sharedbmessage import (
    ShareDBComponent,
    ShareDBDelete,
    ShareDBInsert,
    ShareDBOperation,
    ShareDBSkip,
)
from unique_char.uniquechar import UniqueChar

# Which of two concurrent operations goes first where they both insert at one position.
Side = Literal["left", "right"]

# Which kind of component the caller needs handed over whole rather than split.
Indivisible = Literal["insert", "delete"]


def component_length(component: ShareDBComponent) -> int:
    match component:
        case ShareDBSkip(count):
            return count
        case ShareDBInsert(characters):
            return len(characters)
        case ShareDBDelete(count):
            return count
        case _ as unreachable:
            assert_never(unreachable)


def append(operation: ShareDBOperation, component: ShareDBComponent | None) -> None:
    # Drops components that do nothing and merges a component into the previous one when
    # the two are the same kind, so an operation never holds two adjacent skips.
    if component is None or component_length(component) == 0:
        return

    if len(operation) == 0:
        operation.append(component)
        return

    match operation[-1], component:
        case ShareDBSkip(last), ShareDBSkip(count):
            operation[-1] = ShareDBSkip(last + count)
        case ShareDBInsert(last), ShareDBInsert(characters):
            operation[-1] = ShareDBInsert(last + characters)
        case ShareDBDelete(last), ShareDBDelete(count):
            operation[-1] = ShareDBDelete(last + count)
        case _:
            operation.append(component)


def trim(operation: ShareDBOperation) -> ShareDBOperation:
    # An operation does not have to reach the end of the document, so a skip at the end
    # says nothing. There can only be one, because the operation was built with append.
    if len(operation) > 0 and isinstance(operation[-1], ShareDBSkip):
        operation.pop()
    return operation


def normalise(operation: ShareDBOperation) -> ShareDBOperation:
    normalised: ShareDBOperation = []
    for component in operation:
        append(normalised, component)
    return trim(normalised)


class Take:
    """Hands out the components of an operation, splitting one when only part is wanted.

    Past the end of the operation the document is skipped over forever, so take answers
    with a skip of whatever length was asked for, and take_rest answers with nothing.
    """

    operation: ShareDBOperation
    index: int
    offset: int

    def __init__(self, operation: ShareDBOperation):
        self.operation = operation
        self.index = 0
        self.offset = 0

    def peek(self) -> ShareDBComponent | None:
        if self.index == len(self.operation):
            return None
        return self.operation[self.index]

    # indivisible says which kind of component must not be split up.
    def take(self, count: int, indivisible: Indivisible | None = None) -> ShareDBComponent:
        if self.index == len(self.operation):
            return ShareDBSkip(count)

        match self.operation[self.index]:
            case ShareDBSkip(length):
                if length - self.offset <= count:
                    return self.__whole(ShareDBSkip(length - self.offset))
                self.offset += count
                return ShareDBSkip(count)
            case ShareDBInsert(characters):
                if indivisible == "insert" or len(characters) - self.offset <= count:
                    return self.__whole(ShareDBInsert(characters[self.offset :]))
                part = characters[self.offset : self.offset + count]
                self.offset += count
                return ShareDBInsert(part)
            case ShareDBDelete(length):
                if indivisible == "delete" or length - self.offset <= count:
                    return self.__whole(ShareDBDelete(length - self.offset))
                self.offset += count
                return ShareDBDelete(count)
            case _ as unreachable:
                assert_never(unreachable)

    def take_rest(self) -> ShareDBComponent | None:
        if self.index == len(self.operation):
            return None

        match self.operation[self.index]:
            case ShareDBSkip(length):
                return self.__whole(ShareDBSkip(length - self.offset))
            case ShareDBInsert(characters):
                return self.__whole(ShareDBInsert(characters[self.offset :]))
            case ShareDBDelete(length):
                return self.__whole(ShareDBDelete(length - self.offset))
            case _ as unreachable:
                assert_never(unreachable)

    def __whole(self, component: ShareDBComponent) -> ShareDBComponent:
        self.index += 1
        self.offset = 0
        return component


def apply(state: list[UniqueChar], operation: ShareDBOperation) -> list[UniqueChar]:
    document: list[UniqueChar] = []
    rest = state

    for component in operation:
        match component:
            case ShareDBSkip(count):
                if count > len(rest):
                    raise IndexError("Operation skips past the end of the document")
                document += rest[:count]
                rest = rest[count:]
            case ShareDBInsert(characters):
                document += characters
            case ShareDBDelete(count):
                if count > len(rest):
                    raise IndexError("Operation deletes past the end of the document")
                rest = rest[count:]
            case _ as unreachable:
                assert_never(unreachable)

    return document + rest


def transform(operation: ShareDBOperation, other_operation: ShareDBOperation, side: Side) -> ShareDBOperation:
    # Rewrites operation so that it can be applied after other_operation, which was made
    # against the same document. Where both insert at one position the left one goes
    # first, which is how the two ends of the protocol agree without talking to each
    # other: whoever is submitting is always the left one.
    transformed: ShareDBOperation = []
    take = Take(operation)

    for component in other_operation:
        match component:
            case ShareDBSkip(count):
                length = count
                while length > 0:
                    chunk = take.take(length, "insert")
                    append(transformed, chunk)
                    if not isinstance(chunk, ShareDBInsert):
                        length -= component_length(chunk)
            case ShareDBInsert(characters):
                if side == "left" and isinstance(take.peek(), ShareDBInsert):
                    append(transformed, take.take_rest())
                # Otherwise skip over the characters the other operation inserted.
                append(transformed, ShareDBSkip(len(characters)))
            case ShareDBDelete(count):
                length = count
                while length > 0:
                    chunk = take.take(length, "insert")
                    match chunk:
                        case ShareDBSkip(skipped):
                            length -= skipped
                        case ShareDBInsert():
                            append(transformed, chunk)
                        case ShareDBDelete(deleted):
                            # The characters are gone already, so this delete has nothing left to do.
                            length -= deleted
                        case _ as unreachable:
                            assert_never(unreachable)
            case _ as unreachable:
                assert_never(unreachable)

    rest = take.take_rest()
    while rest is not None:
        append(transformed, rest)
        rest = take.take_rest()

    return trim(transformed)


def compose(operation: ShareDBOperation, other_operation: ShareDBOperation) -> ShareDBOperation:
    # The single operation that does what operation and then other_operation do.
    composed: ShareDBOperation = []
    take = Take(operation)

    for component in other_operation:
        match component:
            case ShareDBSkip(count):
                length = count
                while length > 0:
                    chunk = take.take(length, "delete")
                    append(composed, chunk)
                    if not isinstance(chunk, ShareDBDelete):
                        length -= component_length(chunk)
            case ShareDBInsert():
                append(composed, component)
            case ShareDBDelete(count):
                length = count
                while length > 0:
                    chunk = take.take(length, "delete")
                    match chunk:
                        case ShareDBSkip(skipped):
                            append(composed, ShareDBDelete(skipped))
                            length -= skipped
                        case ShareDBInsert(characters):
                            # Deleting characters the first operation had just inserted.
                            length -= len(characters)
                        case ShareDBDelete():
                            append(composed, chunk)
                        case _ as unreachable:
                            assert_never(unreachable)
            case _ as unreachable:
                assert_never(unreachable)

    rest = take.take_rest()
    while rest is not None:
        append(composed, rest)
        rest = take.take_rest()

    return trim(composed)
