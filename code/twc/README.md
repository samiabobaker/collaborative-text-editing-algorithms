# Text without CRDTs

Both implementations follow [Weidner's blog](https://mattweidner.com/2025/05/21/text-without-crdts.html):

- `twc` implements the central-server version from PR #26. The server assigns an
  order to edits, and clients replay pending local edits over the committed state.
- `twc-p2p` implements the Lamport-ordered version in **Decentralized Variants**.
  Each client retains the edits it has received and replays them in increasing
  `(Lamport counter, client id)` order. The counter includes insertions and
  deletions. Vector clocks enforce causal delivery; concurrent messages can arrive
  in either order. There is no server.

Both use the same insert-after and idempotent-delete operations, including
retaining deleted anchors. The shared ID allocator stands in for opaque globally
unique IDs, as in the server implementation; it does not determine operation order.
The peer variant uses Lamport ordering, not the blog's alternative depth-first
ordering. The blog identifies its list order with RGA/Causal Trees.

## Comparison

At seeds 0–999, three clients, and 30 or 100 generated operations per run, the two
variants give the same property classifications. Counts below are failing seeds,
not probabilities over a shared trace space: server and peer-to-peer delivery have
different available steps, so the same seed need not generate the same history.

| Check | `twc`, 30 ops | `twc-p2p`, 30 ops | `twc`, 100 ops | `twc-p2p`, 100 ops |
| --- | ---: | ---: | ---: | ---: |
| Convergence | 0 | 0 | 0 | 0 |
| Weak list | 0 | 0 | 0 | 0 |
| Strong list | 0 | 0 | 0 | 0 |
| Forward non-interleaving | 0 | 0 | 0 | 0 |
| Maximal non-interleaving | 830 | 757 | 988 | 973 |
| Forward non-interleaving with deletes | 0 | 0 | 0 | 0 |

No runs raised exceptions for these checks. These are bounded tests, not proofs
that the passing properties hold for every execution. The peer variant also
passes the origin-order checker in all 2,000 runs, using the RGA scheme, an
operation-counting Lamport key, and a visible left anchor. That checker does not
support the server variant.

The implementations agree on the final text when supplied the same anchored edits
in the same total order. They can choose different orders for concurrent edits.
The differential test checks the peer's state after every edit and delivery against
an independent RGA tree with the same insertion timestamps, then compares the
settled state with the actual server implementation given that total order.
An extended run of 1,000 mixed histories of 100 generated actions found no
mismatches, including while draining the remaining messages.

From `code/`, reproduce a table cell with, for example:

```sh
python -m main.cli interleaving twc-p2p --from-seed 0 --seeds 1000 --clients 3 --ops 100
python -m main.cli origin-order twc-p2p --from-seed 0 --seeds 1000 --clients 3 --ops 100
python -m twc.test_twcpeerclient
python -c 'from twc.test_twcpeerclient import test_matches_rga_and_server_for_same_order; test_matches_rga_and_server_for_same_order(1000, 100)'
```

The interleaving command exits with status 1 because it finds the expected
maximal non-interleaving violations. Use `convergence`, `weak-list-spec`,
`strong-list-spec`, `forward-interleaving` or `forward-interleaving-with-deletes`
for the other rows, and `twc` for the server variant.
