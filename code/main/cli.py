# Command line front end for the property checkers.
#
#    python -m main.cli --list
#    python -m main.cli convergence tibot2
#    python -m main.cli convergence tibot2 --seeds 1000 --clients 3 --ops 50
#    python -m main.cli strong-list-spec --all --seeds 200
#    python -m main.cli convergence tibot2 --seed 22
#    python -m main.cli convergence tibot2 --forever
#    python -m main.cli strong-list-spec rga --exhaustive --depth 6
#    python -m main.cli weak-list-spec --all --exhaustive --depth 5 --clients 2
#
# Exits 1 if any case failed, so it can be used from a script or from CI.

import argparse
import contextlib
import io
import random
import signal
import sys
import time
import traceback
from collections.abc import Callable, Iterable

from adopted.adoptedtransform import EllisTransform, IMORTransform, ResselTransform, SuleimanTransform, TM11Transform
from algorithm_setup.algorithm_setup import (
    DeviceSetup,
    SOCT2_setup,
    abt_setup,
    adopted_randolph_setup,
    adopted_setup,
    adopted_tm11_setup,
    adopted_tombstone_setup,
    automerge_setup,
    collabs_setup,
    cot_setup,
    diamondtypes_setup,
    diffsync_setup,
    dOPT_setup,
    easysync_setup,
    fugue_setup,
    fuguemax_setup,
    got_setup,
    got_tombstone_setup,
    jupiter_setup,
    lbt_setup,
    logoot_setup,
    logoot_split_setup,
    loro_setup,
    lseq_setup,
    markandretrace_setup,
    pot_setup,
    pps_setup,
    prosemirror_setup,
    rga_setup,
    rgas4_setup,
    sdt_setup,
    sharedb_setup,
    soct3_setup,
    soct4_setup,
    sync7_setup,
    sync9_setup,
    tibot2_setup,
    tibot_setup,
    treedoc_setup,
    twc_peer_setup,
    twc_setup,
    woot_setup,
    wooto_setup,
    yjs_setup,
    yjsmod_setup,
)
from main.convergence import convergence_with_seed
from main.exhaustive import EXHAUSTIVE_CHECKS
from main.interleaving import (
    forward_interleaving_with_deletes_with_seed,
    forward_interleaving_with_seed,
    interleaving_with_seed,
)
from main.originorder import origin_order_with_seed
from main.stronglistspec import stronglistspec_with_seed
from main.weaklistspec import weaklistspec_with_seed

# Every algorithm the checkers can be pointed at. Adding an algorithm means adding a line
# here, which is also what makes it show up in --list and in --all.
ALGORITHMS: dict[str, DeviceSetup] = {
    "abt": abt_setup,
    "adopted-ellis": adopted_setup(EllisTransform),
    "adopted-imor": adopted_setup(IMORTransform),
    "adopted-randolph": adopted_randolph_setup,
    "adopted-ressel": adopted_setup(ResselTransform),
    "adopted-suleiman": adopted_setup(SuleimanTransform),
    "adopted-tm11-transform": adopted_setup(TM11Transform),
    "adopted-tm11": adopted_tm11_setup,
    "adopted-tombstone": adopted_tombstone_setup,
    "automerge": automerge_setup,
    "collabs": collabs_setup,
    "cot": cot_setup,
    "diamondtypes": diamondtypes_setup,
    "diffsync": diffsync_setup,
    "dopt": dOPT_setup,
    "easysync": easysync_setup,
    "fugue": fugue_setup,
    "fuguemax": fuguemax_setup,
    "got": got_setup,
    "got-tombstone": got_tombstone_setup,
    "jupiter": jupiter_setup,
    "lbt": lbt_setup,
    "logoot": logoot_setup,
    "logoot-split": logoot_split_setup,
    "loro": loro_setup,
    "lseq": lseq_setup,
    "markandretrace": markandretrace_setup,
    "pot": pot_setup,
    "pps": pps_setup,
    "prosemirror": prosemirror_setup,
    "rga": rga_setup,
    "rga-s4": rgas4_setup,
    "sdt": sdt_setup,
    "sharedb": sharedb_setup,
    "soct2": SOCT2_setup,
    "soct3": soct3_setup,
    "soct4": soct4_setup,
    "sync7": sync7_setup,
    "sync9": sync9_setup,
    "tibot": tibot_setup,
    "tibot2": tibot2_setup,
    "treedoc": treedoc_setup,
    "twc": twc_setup,
    "twc-p2p": twc_peer_setup,
    "woot": woot_setup,
    "wooto": wooto_setup,
    "yjs": yjs_setup,
    "yjsmod": yjsmod_setup,
}

# Signature shared by every *_with_seed driver: (seed, setup, clients, ops) -> passed.
Check = Callable[..., bool]

CHECKS: dict[str, Check] = {
    "convergence": convergence_with_seed,
    "strong-list-spec": stronglistspec_with_seed,
    "weak-list-spec": weaklistspec_with_seed,
    "interleaving": interleaving_with_seed,
    "forward-interleaving": forward_interleaving_with_seed,
    "forward-interleaving-with-deletes": forward_interleaving_with_deletes_with_seed,
    "origin-order": origin_order_with_seed,
}


@contextlib.contextmanager
def case_timeout(seconds: float):
    # Some implementations can loop forever rather than finish, e.g. Logoot when two
    # concurrent inserts land on adjacent identifiers, so a sweep needs to be able to give
    # up on a case. SIGALRM only interrupts the main thread on POSIX, which is all we need.
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def on_alarm(signal_number: int, frame: object) -> None:
        raise TimeoutError(f"case did not finish within {seconds}s")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def run_case(
    check: Check, setup: DeviceSetup, seed: int, num_of_clients: int, num_of_ops: int, verbose: bool, timeout: float = 0
) -> str:
    # Runs one case and reports "passed", "failed" or the name of the exception it raised.
    # Some implementations raise rather than diverge, and one broken algorithm must not
    # bring down a sweep over all of them.
    # The checkers print the diverging states themselves, which is far too much output for
    # a sweep, so it is captured and only replayed when it is wanted.
    captured = io.StringIO()
    try:
        with case_timeout(timeout):
            if verbose:
                passed = check(seed, setup, num_of_clients, num_of_ops, pause_on_failure=False)
            else:
                with contextlib.redirect_stdout(captured):
                    passed = check(seed, setup, num_of_clients, num_of_ops, pause_on_failure=False)
    except Exception as exception:
        if verbose:
            traceback.print_exc()
        return type(exception).__name__
    return "passed" if passed else "failed"


def run_seeds(
    check: Check,
    setup: DeviceSetup,
    seeds: Iterable[int],
    num_of_clients: int,
    num_of_ops: int,
    stop_early: bool,
    verbose: bool,
    timeout: float,
) -> tuple[list[int], list[int], str]:
    # Runs one algorithm over the given seeds. Returns the seeds that failed, the seeds that
    # raised, and the name of the first exception seen.
    failures: list[int] = []
    errors: list[int] = []
    first_exception = ""
    for seed in seeds:
        outcome = run_case(check, setup, seed, num_of_clients, num_of_ops, verbose, timeout)
        if outcome == "passed":
            continue
        if outcome == "failed":
            failures.append(seed)
        else:
            errors.append(seed)
            first_exception = first_exception or outcome
        if stop_early:
            break
    return failures, errors, first_exception


def run_exhaustive_case(
    check_name: str,
    setup: DeviceSetup,
    num_of_clients: int,
    depth: int,
    verbose: bool,
    timeout: float = 0,
    randomised: bool = False,
    depth_first: bool = False,
) -> tuple[str, int]:
    # The exhaustive counterpart of run_case. Returns the outcome and how many traces were
    # checked, so that a pass can report the size of the space it covered and a timeout can
    # report how far it got. Unlike run_case the timeout bounds the whole search rather than
    # one trace, so the drivers catch it themselves and report the count.
    captured = io.StringIO()
    check = EXHAUSTIVE_CHECKS[check_name]
    try:
        with case_timeout(timeout):
            if verbose:
                outcome, checked = check(setup, num_of_clients, depth, randomised, depth_first)
            else:
                with contextlib.redirect_stdout(captured):
                    outcome, checked = check(setup, num_of_clients, depth, randomised, depth_first)
    except Exception as exception:
        if verbose:
            traceback.print_exc()
        return type(exception).__name__, 0
    return "passed" if outcome else "failed", checked


def seed_list(seeds: list[int], limit: int = 10) -> str:
    # The first few failing seeds, each of which --seed will reproduce on its own.
    shown = " ".join(str(seed) for seed in seeds[:limit])
    return shown + (" ..." if len(seeds) > limit else "")


def run_forever(check: Check, setup: DeviceSetup, first_seed: int, num_of_clients: int, num_of_ops: int) -> int:
    # Mirrors the old drivers: keep going until something fails. Returns the failing seed.
    seed = first_seed - 1
    while True:
        seed += 1
        if seed % 1000 == 0:
            print(f"{seed} cases checked.")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            passed = check(seed, setup, num_of_clients, num_of_ops, pause_on_failure=False)
        if not passed:
            print(captured.getvalue(), end="")
            return seed


def run_exhaustive(
    check_name: str,
    names: list[str],
    num_of_clients: int,
    depth: int,
    verbose: bool,
    timeout: float,
    randomised: bool,
    depth_first: bool,
    seed: int,
) -> int:
    # One sweep per algorithm. A plain exhaustive search is fully determined by the depth
    # and the client count, so there is nothing to reproduce a failure with and none is
    # needed. A randomised one is not, so it is seeded here and the seed is reported: that
    # is the only handle on replaying a violation it turns up.
    #
    # Each algorithm is reseeded with the same value rather than sharing one stream, so a
    # failure in a --all sweep can be replayed on its own algorithm with the seed printed.
    total_failures = 0
    if randomised:
        print(f"randomised search order, seed {seed} (replay this run with --seed {seed})")

    for name in names:
        if randomised:
            random.seed(seed)

        started = time.time()
        outcome, checked = run_exhaustive_case(
            check_name, ALGORITHMS[name], num_of_clients, depth, verbose, timeout, randomised, depth_first
        )
        elapsed = time.time() - started

        if outcome == "passed":
            print(f"{name:24s} {'ok':>7s}  {checked} traces to depth {depth}  ({elapsed:5.1f}s)")
        elif outcome == "failed":
            total_failures += 1
            # The seed is repeated on the failing line so it survives being grepped out of a
            # long --all sweep, where the header is thousands of lines away.
            replay = f"  (--seed {seed})" if randomised else ""
            print(f"{name:24s} {'failed':>7s}  after {checked} traces to depth {depth}  ({elapsed:5.1f}s){replay}")
        elif outcome == "timeout":
            # Not a pass and not a violation: the search was cut short, so it says nothing
            # about the property. Counted as a non-pass so a sweep does not read as clean.
            total_failures += 1
            print(
                f"{name:24s} {'timeout':>7s}  after {checked} traces, depth {depth} not covered"
                f"  ({elapsed:5.1f}s, raise --timeout)"
            )
        else:
            total_failures += 1
            print(f"{name:24s} {'raised':>7s}  {outcome} at depth {depth}  ({elapsed:5.1f}s)")

    return 1 if total_failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m main.cli",
        description="Run a property checker over one or more algorithms.",
    )
    parser.add_argument("check", nargs="?", choices=sorted(CHECKS), help="property to check")
    parser.add_argument("algorithm", nargs="?", choices=sorted(ALGORITHMS), help="algorithm to check")
    parser.add_argument("--all", action="store_true", help="run every algorithm")
    parser.add_argument("--list", action="store_true", help="list the checks and algorithms")
    parser.add_argument("--seeds", type=int, default=1000, help="how many seeds to run (default 1000)")
    parser.add_argument("--from-seed", type=int, default=1, help="first seed (default 1)")
    parser.add_argument(
        "--seed",
        type=int,
        help="run this single seed, e.g. to reproduce a failure; "
        "with --randomised-exhaustive it seeds the search order instead",
    )
    parser.add_argument("--clients", type=int, default=3, help="clients per case (default 3)")
    parser.add_argument("--ops", type=int, default=30, help="operations per case (default 30)")
    parser.add_argument(
        "--exhaustive",
        action="store_true",
        help="enumerate every execution up to --depth instead of sampling random ones (defaults to breadth first search)",
    )
    parser.add_argument("--depth", type=int, default=5, help="operations per execution when --exhaustive (default 5)")
    parser.add_argument("--forever", action="store_true", help="keep going until a case fails")
    parser.add_argument("--stop-early", action="store_true", help="stop an algorithm at its first failure")
    parser.add_argument("--verbose", action="store_true", help="show each failing case in full")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="seconds before a case is given up on, 0 for no limit "
        "(default 10 per random case, 600 for a whole exhaustive search)",
    )
    parser.add_argument(
        "--depth-first",
        action="store_true",
        help="performs a depth-first search, instead of a breadth-first search when doing an exhaustive search",
    )
    parser.add_argument(
        "--randomised-exhaustive",
        action="store_true",
        help="when doing an exhaustive search, randomises the search order",
    )
    args = parser.parse_args(argv)

    # A random case is one trace, where 10s catches an implementation that loops rather
    # than finishing. An exhaustive case is the entire search, where 10s would cut off
    # every depth worth running, so the two modes need different budgets.
    timeout = args.timeout if args.timeout is not None else (600.0 if args.exhaustive else 10.0)

    if args.list:
        print("checks:")
        for name in sorted(CHECKS):
            exhaustive = " (also --exhaustive)" if name in EXHAUSTIVE_CHECKS else ""
            print(f"    {name}{exhaustive}")
        print("algorithms:")
        for name in sorted(ALGORITHMS):
            print(f"    {name}")
        return 0

    if args.check is None:
        parser.error("a check is required (or use --list)")
    if args.algorithm is None and not args.all:
        parser.error("an algorithm is required (or use --all)")

    check_name = str(args.check)
    names: list[str] = sorted(ALGORITHMS) if args.all else [str(args.algorithm)]

    if args.exhaustive:
        if check_name not in EXHAUSTIVE_CHECKS:
            parser.error(f"--exhaustive does not support {check_name}, only {', '.join(sorted(EXHAUSTIVE_CHECKS))}")
        if args.forever:
            parser.error("--exhaustive and --forever are alternatives: an exhaustive search is already finite")
        if args.seed is not None and not args.randomised_exhaustive:
            parser.error(
                "--seed only affects an exhaustive search when --randomised-exhaustive is used: "
                "without it the search order is already fixed by --depth and --clients"
            )

        # A run with no seed still gets one, so that a violation found by chance can be
        # replayed; picking it here rather than per algorithm keeps one --all sweep to a
        # single seed.
        seed = args.seed if args.seed is not None else random.randrange(2**31)

        return run_exhaustive(
            check_name,
            names,
            args.clients,
            args.depth,
            args.verbose,
            timeout,
            args.randomised_exhaustive,
            args.depth_first,
            seed,
        )

    check = CHECKS[check_name]
    seeds = [args.seed] if args.seed is not None else range(args.from_seed, args.from_seed + args.seeds)

    if args.forever:
        if args.all:
            parser.error("--forever runs a single algorithm")
        name = names[0]
        print(f"{args.check} on {name}, seeds from {args.from_seed}, until failure")
        seed = run_forever(check, ALGORITHMS[name], args.from_seed, args.clients, args.ops)
        print(f"FAILED at seed {seed}")
        return 1

    count = len(list(seeds))
    total_failures = 0
    for name in names:
        started = time.time()
        failures, errors, exception = run_seeds(
            check, ALGORITHMS[name], seeds, args.clients, args.ops, args.stop_early, args.verbose, timeout
        )
        total_failures += len(failures) + len(errors)
        elapsed = time.time() - started

        if not failures and not errors:
            print(f"{name:24s} {'ok':>5s}/{count} passed  ({elapsed:5.1f}s)")
            continue

        parts: list[str] = []
        if failures:
            parts.append(f"seeds: {seed_list(failures)}")
        if errors:
            parts.append(f"[{len(errors)} raised {exception}, seeds: {seed_list(errors)}]")
        print(f"{name:24s} {len(failures):>5d}/{count} failed  ({elapsed:5.1f}s)  " + "  ".join(parts))

    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())
