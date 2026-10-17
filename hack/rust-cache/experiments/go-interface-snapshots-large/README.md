# Interface snapshots on the real Go collection listing

This revisits the existing per-pass interface-field snapshot experiment after goroutine samples on the 800-package repository locate contention during client initialization and interface reconciliation. The earlier 64-package complete-command comparisons were mixed.

The same engine binary and final Go module `9eb4c36` are used in both arms; only `/debug/interface-field-snapshots` changes. All commands receive a fresh Go source comment and CLI, with normal GC, telemetry, declaration reuse, metadata batching, attribute decoding and snapshot seeds. Callback reuse, flush coalescing and metadata read-ahead remain off. No cache reset occurs.

Two alternating orders return identical 4,398 rows and exit successfully:

| Order | Original | Interface snapshots |
| --- | ---: | ---: |
| Before, after | 68.38 s | 67.53 s |
| After, before | 69.92 s | 68.00 s |

Median time is 69.15 → 67.76 seconds, engine CPU 311.83 → 300.27 seconds and allocations 44.28 → 43.31 GB. These are reductions on the large case, not an order-of-magnitude command improvement. Current Go ownership and actual test-collection checks also pass with the flag on. The prior complete dagql race suite and smaller-workload evidence remain in `../interface-field-snapshots/`. The option is restored off after measurement; no PR is opened for it.

The next algorithmic experiment should avoid repeatedly sorting the same schema maps within one reconciliation and prune impossible candidate relationships before constructing the full relation graph. It must preserve declared relationships, view-dependent fields and the greatest-fixed-point result for recursive covariance. It has not been implemented or benchmarked.
