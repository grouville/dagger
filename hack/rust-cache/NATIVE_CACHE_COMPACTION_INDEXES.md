# Cache compaction: captured stall and rejected index changes

The real Go collection listing captured an **8.167-second compaction while holding the graph write lock**. Both index changes tested afterward are rejected. Neither is installed, and neither establishes a faster complete listing.

## Captured work

Fourteen complete listings with fresh source comments grow the existing cache, then six diagnostic listings capture its maintenance. Every command exits successfully with the same **4,398 ordered rows**. The engine, source cache and native Rust cache remain in place; there is no forced collection, budget change or deferred cleanup. This is a warm-engine edited-source workload, not a cold-engine benchmark or an optimization comparison.

The second capture records class slots shrinking from **1,067,435 to 602,255**, with **2,447,622 terms** present. The compaction event lasts **8.167 seconds**, and CPU sampling attributes **8.17 CPU-seconds** to that same operation. Several seconds are spent rebuilding the reverse indexes from classes to terms and results. The complete diagnostic command takes **51.321 seconds**. A preceding capture without compaction takes 36.874 seconds, but these are not matched observations: the difference cannot all be attributed to compaction.

Wcprof places the main query at 49.34 seconds, including an 8.26-second nested request during the compaction interval. The graph lock explains why otherwise small requests can stall during maintenance. Aggregate mutex-wait samples sum time across concurrent waiters; they are not elapsed seconds that can be subtracted from the command.

Compaction is positively captured once. No capture shows a net reduction in cached results. The diagnostic controller stops at its declared six-capture limit, rather than claiming to have captured result eviction too.

## Reuse member maps: rejected

Compaction renumbers classes but preserves term and result IDs. The first change reuses the three reverse indexes' member maps and remaps only their outer class keys. Four alternating fresh-process pairs on upstream `ff0b029a` show:

| 131,072-result fixture | Upstream | Reuse | Faster pairs |
| --- | ---: | ---: | ---: |
| Independent results | 463.79 ms | 392.54 ms | 4/4 |
| Shared dependency | 565.53 ms | 490.72 ms | 3/4 |

Allocated memory for the independent fixture falls from 181.07 to 128.56 MiB. Setup, graph validation and cache closing are outside the timer; compaction and its write-lock hold are measured.

An adversarial benchmark exposes the cost hidden by those results. It creates 131,072 transient dependents, keeps one dependent alive, releases the transient session through the cache API, and compacts. Both versions retain exactly two results and two terms with correct indexes. Reading the one surviving input membership takes **51.23 ns upstream versus 124,143 ns with reuse**. The reused Go map retains its former storage after deletion. Faster compaction does not justify imposing that cost on later reads.

## Rebuild by class: also rejected

The second version rebuilds each member map once per class, sized for its live entries. It preserves shrinking and returns the deletion benchmark to **49.69 ns** per read. However, a separate four-pair cohort shows slower compaction:

| 131,072-result fixture | Upstream | Grouped rebuild | Faster pairs |
| --- | ---: | ---: | ---: |
| Independent results | 443.14 ms | 509.51 ms | 0/4 |
| Shared dependency | 549.22 ms | 632.04 ms | 0/4 |

These are separate fixed cohorts; their baselines are not pooled. Neither result warrants an engine replacement or upstream proposal.

## Validation and evidence

The full DagQL race suite passes on upstream and both candidates. A focused check verifies exact term indexes after merged-class compaction, both in memory and after persistence import. Benchmarks independently rebuild term memberships and compare logical graph contents before and after compaction. Correctness alone would not have caught the retained-storage regression.

After all twenty real Go listings, all six retained Rust histories still hit every compiler action: **130/130, 1,026/1,026 and 6/6**, for both histories. Profilers and experimental flags are restored, with the same engine binary retained. The confirmed native telemetry codec and the unconfirmed native gRPC transport remain separate experiments.

[Maintenance evidence](experiments/cache-metadata-stall-profile/) retains every preparation command and capture, raw compressed wcprof events, CPU and lock profiles, exact source mapping, Rust checks and analysis drivers. [Index evidence](experiments/cache-compaction-indexes/) retains both rejected implementations, every sample and the deletion benchmark. Each archive has a verified manifest. An earlier resumed CPU analysis accidentally included its own combined output for the first capture; that derivation is retained and explicitly superseded by merging only the original numbered windows. The compaction event and second capture's CPU result were unaffected.

The next target must remove work without retaining obsolete storage. The existing [compact class mapping](NATIVE_CACHE_CLASS_MAPPING.md) and [digest-set reuse](NATIVE_CACHE_COMPACTION_DIGEST_SETS.md) remain distinct, previously measured candidates; this study does not replace their outstanding full-command validation.

The subsequent [TreeSet allocation study](NATIVE_TREESET_ITERATION.md) produces a small library improvement, but the real profile shows its allocation share is too small to explain the listing delay. Larger interpreter, schema and telemetry allocation sources remain the next priorities.
