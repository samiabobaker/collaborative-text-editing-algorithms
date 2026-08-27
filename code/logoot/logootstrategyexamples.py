from __future__ import annotations

import contextlib
import io
import random

from algorithm_setup.algorithm_setup import DeviceSetup, make_setup
from convergence_checker.convergence_checker import convergence_checker
from device.clientdevice import ClientDevice
from logoot.logootclient import LogootClient
from logoot.logootdocument import LogootDocument, LogootIdentifier, LogootPosition, position_less_than
from main.cli import case_timeout

# The benchmarker caps how wide an interval it will pick from. The cap never binds at the
# bases used here, it is kept so the ported code reads like the original.
BOUND = 10**9

# A strategy can hand back an identifier outside (p, q) long before the clients visibly
# disagree, so every allocation is adjudicated as it is made.
allocations = {"total": 0, "outside": 0}


def digit_at(position: LogootPosition, index: int) -> int:
    # Digits past the end of a position read as 0, as they do in prefix().
    return position[index].pos if index < len(position) else 0


def record(p: LogootPosition, q: LogootPosition, new_id: LogootPosition) -> LogootPosition:
    allocations["total"] += 1
    if not (position_less_than(p, new_id) and position_less_than(new_id, q)):
        allocations["outside"] += 1
    return new_id


def plus(digits: list[int], separation: int, base: int) -> None:
    # Adds to the last digit, carrying up through the earlier ones.
    index = len(digits) - 1
    if base - 1 - digits[index] < separation:
        carry, digits[index] = divmod(digits[index] + separation, base)
        while carry != 0:
            index -= 1
            carry, digits[index] = divmod(digits[index] + carry, base)
    else:
        digits[index] += separation


def construct_identifier(
    digits: list[int], p: LogootPosition, q: LogootPosition, site: int, clock: int
) -> LogootPosition:
    # Digits matching p keep p's identifiers, then digits at or above q's keep q's, and
    # whatever is left is minted here.
    position: LogootPosition = []
    last = len(digits) - 1
    index = 0
    while index < last and index < len(p) and digits[index] == digit_at(p, index):
        position.append(p[index])
        index += 1
    while index < last and index < len(q) and digits[index] >= digit_at(q, index):
        position.append(q[index])
        index += 1
    while index <= last:
        position.append(LogootIdentifier(digits[index], site, clock))
        index += 1
    return position


class BoundaryLogootDocument(LogootDocument):
    """Allocation as coast-team's BoundaryStrategy writes it.

    This is the attempted fix Sun mention in 4.4.3. When no digit interval opens between
    p and q it widens the search by counting the space that wraps around past q, so the
    identifiers it hands back can in principle land after q. Two guards keep it in range:
    it skips through a 0 digit of q once p is exhausted, and it lifts the ordinary same
    digit tie from -1 back up to 0 before widening.
    """

    # Small enough that concurrent inserts collide on a digit often.
    BASE: int = 2**2

    def generate_line_id(self, p: LogootPosition, q: LogootPosition, N: int, site: int) -> list[LogootPosition]:
        index = 0
        while (index < min(len(p), len(q)) and p[index] == q[index]) or (
            len(p) <= index < len(q) and digit_at(q, index) == 0
        ):
            index += 1

        d = digit_at(q, index) - digit_at(p, index) - 1
        if d >= N:
            interval = min(d // N, BOUND)
        else:
            diff = 0 if d == -1 else d
            while diff < N:
                index += 1
                diff = diff * self.BASE + (self.BASE - 1 - digit_at(p, index)) + digit_at(q, index)
            interval = min(diff // N, BOUND)

        digits = [digit_at(p, i) for i in range(index + 1)]
        ids: list[LogootPosition] = []
        for _ in range(N):
            plus(digits, random.randint(1, interval), self.BASE)
            self.clock += 1
            ids.append(record(p, q, construct_identifier(digits, p, q, site, self.clock)))
        return ids


class BoundaryListLogootDocument(LogootDocument):
    """Allocation as coast-team's BoundaryListStrategy writes it.

    The same widening, but it compares digits alone rather than whole identifiers, and it
    has neither guard. Two positions that share every digit and differ only by site send
    the skip loop past the end of both, reading 0 against 0, and it never comes back.
    """

    BASE: int = 2**2

    def generate_line_id(self, p: LogootPosition, q: LogootPosition, N: int, site: int) -> list[LogootPosition]:
        index = 0
        while digit_at(p, index) == digit_at(q, index):
            index += 1

        d = digit_at(q, index) - digit_at(p, index) - 1
        if d >= N:
            interval = min(d // N, BOUND)
        else:
            while d < N:
                index += 1
                d = d * self.BASE + (self.BASE - 1 - digit_at(p, index)) + digit_at(q, index)
            interval = min(d // N, BOUND)

        digits = [digit_at(p, i) for i in range(index + 1)]
        ids: list[LogootPosition] = []
        for _ in range(N):
            plus(digits, random.randint(1, interval), self.BASE)
            self.clock += 1
            ids.append(record(p, q, construct_identifier(digits, p, q, site, self.clock)))
        return ids


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


class BoundaryLogootClient(LogootClient):
    def __init__(self, client_id: int):
        super().__init__(client_id)
        self.document = BoundaryLogootDocument(client_id)


class BoundaryListLogootClient(LogootClient):
    def __init__(self, client_id: int):
        super().__init__(client_id)
        self.document = BoundaryListLogootDocument(client_id)


boundary_setup = make_setup(BoundaryLogootClient)
boundary_list_setup = make_setup(BoundaryListLogootClient)


def __show(position: LogootPosition) -> str:
    return ".".join(f"({identifier.pos},{identifier.client_id})" for identifier in position)


def __sweep(name: str, setup: DeviceSetup, base: int, num_of_seeds: int, num_of_ops: int) -> None:
    allocations["total"] = 0
    allocations["outside"] = 0
    outcomes: dict[str, list[int]] = {"converged": [], "diverged": [], "never finished": [], "raised": []}
    for seed in range(num_of_seeds):
        random.seed(seed)
        server, clients = setup(3)
        client_dict: dict[int, ClientDevice] = {}
        for client in clients:
            client_dict[client.client_id] = client
        try:
            with case_timeout(5), contextlib.redirect_stdout(io.StringIO()):
                converged = convergence_checker(client_dict, server, num_of_ops)
            outcomes["converged" if converged else "diverged"].append(seed)
        except TimeoutError:
            outcomes["never finished"].append(seed)
        except ValueError, IndexError:
            outcomes["raised"].append(seed)

    print(f"{name}, base {base}, {num_of_seeds} seeds of {num_of_ops} operations")
    for outcome, seeds in outcomes.items():
        if seeds:
            print(f"  {outcome}: {len(seeds)} (first {seeds[0]})")
    print(f"  identifiers outside (p, q): {allocations['outside']} of {allocations['total']}")


def boundary_strategy_example():
    """BoundaryStrategy keeps every identifier inside (p, q) on our traces."""
    __sweep("coast-team BoundaryStrategy", boundary_setup, BoundaryLogootDocument.BASE, 100, 100)


def boundary_list_strategy_example():
    """BoundaryListStrategy hangs instead, and never allocates past q on the way there."""
    __sweep("coast-team BoundaryListStrategy", boundary_list_setup, BoundaryListLogootDocument.BASE, 100, 100)


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
    print("--- coast-team BoundaryStrategy")
    boundary_strategy_example()
    print("--- coast-team BoundaryListStrategy")
    boundary_list_strategy_example()
    print("--- rudi-c/alchemy-book")
    alchemy_strategy_example()
