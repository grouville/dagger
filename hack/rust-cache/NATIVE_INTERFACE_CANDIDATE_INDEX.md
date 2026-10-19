# Index structural interface candidates

A standalone engine candidate reduces fresh schema construction from **51.99 to 8.74 ms** for 512 objects and 16 interfaces, with allocated bytes falling **98.80 to 9.13 MB**. A control modeled on core's few shared interfaces improves **18.92 to 17.43 ms**. Both improve in all four alternating pairs. These are component results; complete Go listing, Rust commands and cold-engine performance are unmeasured with this candidate. It is not installed in the retained engines, and no PR is open.

The engine currently starts with every object/interface pair and repeatedly removes invalid relationships. The candidate builds a temporary index of visible field names and starts each interface from types exposing its least common required field. The original type, argument and recursive compatibility rules still decide which relationships survive. Explicit declarations remain facts, including declarations without matching fields. Empty interfaces still consider every eligible type.

Required-field lists are reused only within one reconciliation pass. Objects with many fields use individual lookups for the few required names; sparse objects use one field scan. A private field-count method reads the existing class map under its existing lock, then releases it before any lookup. Fully declared objects need no index construction, and a single interface retains direct candidate seeding. There is no global cache, new lock, public API or persistence-format change.

| Fresh schema fixture | Original | Candidate | Allocated bytes, original → candidate | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 1 object / 1 interface | 15.88 µs | 17.79 µs | 21.0 → 21.3 kB | 0/4 |
| 128 objects / 8 interfaces, grouped matches | 7.18 ms | 1.81 ms | 12.88 → 2.19 MB | 4/4 |
| 512 objects / 16 interfaces, grouped matches | 51.99 ms | 8.74 ms | 98.80 → 9.13 MB | 4/4 |
| 128 objects / 8 interfaces, all matches | 6.68 ms | 4.27 ms | 11.86 → 3.22 MB | 4/4 |
| 128 objects / 1 interface, declared | 0.824 ms | 0.826 ms | 0.771 → 0.769 MB | 2/4 |
| 128 objects / 8 interfaces, all declared | 2.03 ms | 1.74 ms | 1.72 → 1.20 MB | 4/4 |
| 128 objects / 3 interfaces, 64 unrelated fields | 4.76 ms | 4.39 ms | 4.83 → 4.55 MB | 4/4 |
| 512 objects / 3 interfaces, 64 unrelated fields | 18.92 ms | 17.43 ms | 19.30 → 18.17 MB | 4/4 |

The tiny fixture costs an additional **1.92 µs, 336 bytes and two allocations**. The one-interface declared fixture is effectively flat. This constant overhead and the added indexing logic are explicit tradeoffs, and the component gains do not establish a useful complete-command gain.

Four fresh-process pairs per shape use Go 1.26.6, GOMAXPROCS=8 and 150 ms per benchmark. Every iteration constructs a fresh schema, with construction included in the timer; compiled code is warm. Order alternates between pairs, pressure observations are recorded, and every attempt is retained. This is neither first-use CLI timing nor an empty-cache engine measurement.

The final full DagQL race suite passes in **66.065 seconds**. Focused regressions cover recursive relationships and their removal, explicit declarations as evidence, empty interfaces, sparse candidate work and avoiding full field-table copies. Existing tests cover views, variance, installation order and concurrent registration. The sparse probe records **4,160 compatibility `FieldSpec` calls on unchanged code and 64 with the candidate**, with all intended matches preserved. Index construction still reads field metadata, which is included in the benchmarks. Its compatibility-call bound fails on unchanged code. The declared, empty-interface and recursive cases also pass unchanged code. The baseline reconciliation body exactly matches the function sampled in the retained engine's CPU profile, so this targets an active path.

The first index regressed dense and already-declared shapes. Per-pass field-list reuse and direct seeding for one interface address those costs. A later control exposed a more relevant regression: scanning every field changes the 512-object core-shaped fixture **18.87 → 25.38 ms** and nearly doubles allocation. Adaptive name lookups fix that measured regression. All intermediate sources, failed fixture compilation, race runs and benchmark cohorts remain in the evidence; their results are not pooled with the final cohort.

The follow-up Go ownership confirmation remains unselected: its 12 complete commands all return correct rows and exit successfully, but medians are **15.12 → 19.74 seconds** under variable CPU pressure, despite three of four paired differences favoring the candidate. Quiet admission does not guarantee quiet execution. This is additional evidence against claiming a stable test-edit gain from that separate module change.

[Standalone source branch](https://github.com/grouville/dagger/tree/experiment/interface-candidate-index), [review description](PR_INTERFACE_CANDIDATE_INDEX.md), [patch, exact sources, all measurements and checks](experiments/interface-candidate-index/). All four retained engine binaries are unchanged and their cache volumes are retained; workspace files and diagnostic switches are restored and no client remains active. The next gate is a controlled engine comparison of complete Go listing and the Rust module's normal selection, execution and native-cache behavior.
