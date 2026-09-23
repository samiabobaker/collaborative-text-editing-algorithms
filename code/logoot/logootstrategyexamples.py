from __future__ import annotations

from logoot.logootdocument import LogootDocument, LogootIdentifier, LogootPosition, position_less_than

# The coast-team comparisons run the original Java classes. See upstream/README.md.


class SiteOrderingError(ValueError):
    pass


class AlchemyLogootDocument(LogootDocument):
    """Allocation as rudi-c/alchemy-book writes generatePositionBetween.

    It walks p and q down one identifier at a time: allocate here when the digits differ,
    extend p when the digits tie and p's site is lower, otherwise go a level deeper. Once
    p runs out it has nothing to compare against q's next identifier, so it makes one up,
    digit 0 with the inserting site. The digit is below anything real but the site is not,
    and when it sorts above the site in q's identifier the comparison contradicts p < q
    and reaches the error below.
    """

    def generate_line_id(self, p: LogootPosition, q: LogootPosition, N: int, site: int) -> list[LogootPosition]:
        ids: list[LogootPosition] = []
        lower = p
        for _ in range(N):
            self.clock += 1
            lower = self.__between(lower, q, site)
            ids.append(lower)
        return ids

    def __between(self, p: LogootPosition, q: LogootPosition, site: int) -> LogootPosition:
        head_p = p[0] if p else LogootIdentifier(0, site, self.clock)
        head_q = q[0] if q else LogootIdentifier(self.BASE, site, self.clock)

        if head_p.pos != head_q.pos:
            digits_p = [identifier.pos for identifier in p]
            return self.__construct(self.__increment(digits_p, self.__subtract(digits_p, q)), p, q, site)
        if head_p.client_id < head_q.client_id:
            return [head_p, *self.__between(p[1:], [], site)]
        if head_p.client_id == head_q.client_id:
            return [head_p, *self.__between(p[1:], q[1:], site)]
        raise SiteOrderingError("invalid site ordering")

    def __subtract(self, digits_p: list[int], q: LogootPosition) -> list[int]:
        # q - p, with the final borrow dropped, as subtractGreaterThan does.
        digits_q = [identifier.pos for identifier in q]
        result = [0] * max(len(digits_p), len(digits_q))
        borrow = 0
        for index in reversed(range(len(result))):
            left = (digits_q[index] if index < len(digits_q) else 0) - borrow
            right = digits_p[index] if index < len(digits_p) else 0
            borrow = 1 if left < right else 0
            result[index] = left + self.BASE - right if left < right else left - right
        return result

    def __add(self, left: list[int], right: list[int]) -> list[int]:
        result = [0] * max(len(left), len(right))
        carry = 0
        for index in reversed(range(len(result))):
            total = (left[index] if index < len(left) else 0) + (right[index] if index < len(right) else 0) + carry
            carry, result[index] = divmod(total, self.BASE)
        if carry:
            raise ValueError("sum is greater than one, cannot be represented by this type")
        return result

    def __increment(self, digits: list[int], delta: list[int]) -> list[int]:
        # Steps just past p, and never leaves a 0 as the last digit.
        first_nonzero = next((index for index, digit in enumerate(delta) if digit != 0), -1)
        step = [*(delta[:first_nonzero] if first_nonzero >= 0 else delta[:-1]), 0, 1]
        incremented = self.__add(digits, step)
        return self.__add(incremented, step) if incremented[-1] == 0 else incremented

    def __construct(self, digits: list[int], p: LogootPosition, q: LogootPosition, site: int) -> LogootPosition:
        position: LogootPosition = []
        last = len(digits) - 1
        for index, digit in enumerate(digits):
            if index == last:
                position.append(LogootIdentifier(digit, site, self.clock))
            elif index < len(p) and digit == p[index].pos:
                position.append(p[index])
            elif index < len(q) and digit == q[index].pos:
                position.append(q[index])
            else:
                position.append(LogootIdentifier(digit, site, self.clock))
        return position


def __show(position: LogootPosition) -> str:
    return ".".join(f"({identifier.pos},{identifier.client_id})" for identifier in position)


def alchemy_strategy_example():
    """The same p and q allocate or refuse depending on who is inserting.

    q here is what alchemy-book's own allocation returns between two positions that tie
    on the digit 14, so a document needs two inserts to reach a pair it will not
    allocate between.

    There is no sweep for this one. Its identifiers are a digit and a site with no clock,
    and lending them ours lets positions differ on a field the algorithm never reads, so
    counting identifiers outside (p, q) here would be measuring the transplant.
    """
    document = AlchemyLogootDocument(0)
    p = [LogootIdentifier(14, 0, 1)]
    q = document.generate_line_id(p, [LogootIdentifier(14, 5, 1)], 1, 5)[0]
    print(f"  its own allocation between 14 by site 0 and 14 by site 5, at site 5: {__show(q)}")
    for site in (3, 7):
        try:
            print(f"  between 14 and that at site {site}: {__show(document.generate_line_id(p, q, 1, site)[0])}")
        except SiteOrderingError as error:
            print(f"  between 14 and that at site {site}: {type(error).__name__}, {error}")

    shipped = LogootDocument(0)
    for site in (3, 7):
        new_id = shipped.generate_line_id(p, q, 1, site)[0]
        between = position_less_than(p, new_id) and position_less_than(new_id, q)
        print(f"  shipped, between 14 and that at site {site}: {__show(new_id)}, strictly between: {between}")


if __name__ == "__main__":
    print("--- rudi-c/alchemy-book")
    alchemy_strategy_example()
