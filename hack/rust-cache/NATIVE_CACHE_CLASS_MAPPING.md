# Renumber cache classes without hash tables or sorting

The compact bit index makes compaction faster in all **12 symbolic-index comparisons** and all **8 populated-cache comparisons**. The standalone branch is [perf/compact-cache-class-mapping](https://github.com/grouville/dagger/tree/perf/compact-cache-class-mapping), based on upstream `ff0b029a`. It remains uninstalled in the retained engine. This establishes a maintenance improvement, not a faster complete Go listing.

## Work removed

Compaction keeps the live equivalence classes, gives them consecutive IDs and updates their references. Previously it discovered live IDs with a hash set, sorted them, then built a second hash table mapping old IDs to new IDs. IDs already index the parent table, so their range is known.

The candidate marks live IDs in a bitmap. Scanning its set bits produces the same ascending order as the old sort. One prefix count per 64 IDs records how many earlier IDs are live. That count plus a population count within the current word gives exactly the same new ID, with zero reserved. Only live-root discovery and remapping change; digest-set copies, term-input copies and the remaining table rebuild stay on their original paths.

For this mapping stage, sorting `L` live roots is replaced by scanning `S/64` words and `L` set bits, where `S` is the allocated ID range. Lookup uses the standard library's `math/bits`. There is no new lock, cache, dependency or persistence format. The existing graph lock still covers the operation.

## Symbolic-index screen

Four balanced triples compare the original, a plain array and the compact bit index. Each process builds a new fixture and compacts it once. Both bitmap construction and prefix construction are timed: there is no warm index. Ordinary GC stays enabled, with construction and validation outside the timer.

| Live / dead classes | Original | Plain array | Bit index |
| --- | ---: | ---: | ---: |
| 1,000 / 1,000 | 3.510 ms | 3.060 ms | 3.215 ms |
| 200,000 / 40,000 | 1.143 s | 0.970 s | 0.938 s |
| 2,000 / 1,000,000 | 5.418 ms | 7.787 ms | 4.742 ms |

The bit index is faster in all four comparisons for every shape. Large-fixture allocation decreases **299.52 → 285.40 MB**. The sparse fixture allocates **3.473 → 3.513 MB**, about 40 kB more: bitmap storage follows the allocated ID range rather than just the live population. This is the measured memory tradeoff. It needs roughly a quarter byte per allocated slot for the bitmap and prefix table, alongside the existing live-root list.

The plain array is rejected: its sparse case is slower in every pair and allocates **11.27 MB**, about 7.8 MB more than the original. Its lower code complexity does not justify that regression. Symbolic-fixture host pressure peaks at 3.0% CPU and 0.09% I/O, with no recorded memory pressure.

## Populated-cache check

A separate benchmark creates **50,000 real persisted scalar results** through `GetOrInitCall`, either independently or sharing a receiver, then adds 5,000 unused class slots. It checks derived indexes before and after compaction, preserves all result and term counts, and requires an existing result to hit the cache afterward. Setup and validation are outside the timer. No GC is forced.

| Cache shape | Original | Bit index | Allocation before → after |
| --- | ---: | ---: | ---: |
| Independent results | 139.51 ms | 119.88 ms | 65.00 → 61.46 MB |
| Shared dependency | 160.79 ms | 139.66 ms | 67.76 → 64.23 MB |

All eight alternating pairs improve. Median paired savings are **19.81 ms** and **21.84 ms** respectively. Each cache retains 50,000 results and 50,000 terms while class slots shrink from 55,000 to 50,000. The measured graph-lock hold decreases with compaction time. Host pressure peaks at 1.5% CPU and 0.13% I/O.

These fixtures test actual cache operations, not containers or a complete CLI command. They do not show how often compaction runs in a production engine or how much a particular listing saves.

## Correctness and review

The new regression compares logical contents across sparse IDs, including IDs around 64-bit boundaries and classes referenced only by a result. Existing tests cover class merges, inverse indexes, forced and skipped compaction, persistence snapshots and cached results. Focused race checks pass for all three variants; the full DagQL race suite passes for the bit-index prototype and standalone branch.

Review checked that `findEqClassLocked` returns either zero or an index into the parent table, that bit zero remains unused, and that the inclusive population count assigns the exact old sorted order. The local bitmap and prefix table do not escape or alias cache-owned data. No ownership, lock-order or collection-policy change is included.

The retained engine remains `9123a6a5`; its volume and primary Rust timing manifest are unchanged. Runtime and complete-command validation of this new algorithm remain outstanding. The separate [direct-forwarding Go cohort](NATIVE_GO_DIRECT_SPAN_FORWARDING.md) stays unselected. The main listing target remains incomplete.

[Review description](upstream-prs/cache-class-mapping.md). [Evidence](experiments/cache-compaction-mapping/) retains the rejected array, all comparisons, tests, source variants and standalone provenance. No PR is open.
