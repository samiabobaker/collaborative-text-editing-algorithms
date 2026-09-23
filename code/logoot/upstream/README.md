# Boundary allocator comparisons

These examples run the original Java allocator and identifier classes from
[coast-team/replication-benchmarker](https://github.com/coast-team/replication-benchmarker/tree/e3f6f534cd0d37f2c9e7b3288cd6f92b3b4784cc).
They replace the supplementary Python Boundary ports added in
[PR #12](https://github.com/samiabobaker/collaborative-text-editing-algorithms/pull/12).
The repaired Logoot implementation used by Darner is unchanged.

## Run

With Python and a JDK installed (tested with Java 17), from the repository root:

```sh
git clone https://github.com/coast-team/replication-benchmarker.git /tmp/replication-benchmarker
git -C /tmp/replication-benchmarker checkout e3f6f534cd0d37f2c9e7b3288cd6f92b3b4784cc
python code/logoot/upstream/check_boundary.py /tmp/replication-benchmarker
```

The runner checks the revision and that the tracked Java sources are unchanged,
compiles into a temporary directory, and stops the intentional infinite loop in a
separate process. Set `JAVA_HOME` if the JDK is not on `PATH`. The harness only
supplies a site/clock adapter, test states and deterministic random seeds; it uses
upstream allocation and comparison code unchanged.

## BoundaryListStrategy

The old port compared composite positions by their primary digits alone, padding
with zero. Equal digits with different sites therefore sent its equality scan past
both endpoints forever. Upstream instead packs the site and clock into the digit
array and pads with the signed minimum. Its scan sees the different site metadata.
The fixture checks 1,000 allocations between such endpoints at each supported
width (8, 16 and 32 bits). All are strictly inside the interval.

The old port's hangs do not establish an upstream BoundaryListStrategy failure.
These bounded checks do not establish that the strategy has no other failures.

## BoundaryStrategy

The old port also used `base - 1` where this upstream class uses
`2^(nbBit-1) - 1`. With `nbBit=4`, the original class has base 16 but max 7.
The fixture constructs a short two-client history using only upstream allocations,
local deletions and causal delivery. Each successful allocation is checked against
its current neighbours. The upstream random generator is seeded once with 80,
making this a deterministic example, not a frequency estimate.

The final neighbouring identifiers are `<5,1,1><10,1,4>` and `<6,2,1>`, where each
triple is `(digit, site, clock)`. The initial digit interval is zero. Widening it
produces -3, followed by the recurrence `d_next = 16*d + 7`, since all remaining
digits are zero. For every negative integer `d`, this stays negative and decreases;
the loop requires `d >= 1`. Thus it cannot terminate, independently of the timeout
used to stop the process.

This is nontermination in the original allocator at a small bit width. It is not
a divergence result, and does not demonstrate a failure at the default 64-bit
configuration or in Darner's repaired Logoot implementation.
