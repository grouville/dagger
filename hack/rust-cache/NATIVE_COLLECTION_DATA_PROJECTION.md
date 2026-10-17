# Read collection metadata without item cache entries

Complete Go test listing on `dagger/dagger` improves **42.24 → 35.90 seconds median**, faster in all four measured pairs. All ten commands, including initialization, return the expected ordered rows and exit successfully through cleanup. This is the current selected Go diagnostic; it establishes no new Rust build-time result.

The engine keeps each metadata list cached, but no longer needs an attached cache result for every item when the query only reads its stored scalar fields. Wcprof confirms that all **17,592 dimension-key item publications disappear**, while both string getters still run 17,592 times. Artifact objects and explicit ID selections retain their ordinary path.

## Complete command

`dagger check --module go --check test --list --all` uses source `ff0b029a`, Go module `7568cd0`, CLI `e7ba08d0` and controlled engine `7c989097`. Both arms run on the same retained engine and volume. Each command starts a fresh CLI and receives a fresh source comment. Telemetry and ordinary GC stay enabled; profiling is off during timing.

The excluded initialization pair adds a real test and correctly returns 4,399 rows. Measured pairs remove it, alternate order and return 4,398 rows.

| Pair | Ordinary item attachment | Data-only projection |
| --- | ---: | ---: |
| 1, candidate first | 40.40 s | 35.35 s |
| 2, control first | 40.43 s | 35.40 s |
| 3, candidate first | 51.27 s | 38.77 s |
| 4, control first | 44.05 s | 36.39 s |

Median paired saving is **6.36 seconds**. Allocation falls in every pair, with separate column medians **32.79 → 29.09 GB**. Engine CPU also falls in every pair: **211.49 → 187.93 CPU-seconds** at the column medians, or 25.31 CPU-seconds at the median paired difference. Concurrent CPU totals are not elapsed time.

The third control coincides with class-slot count falling from 931,484 to 715,487. Its full 12.50-second gap cannot be attributed to projection. The first two pairs each save about five seconds without a compaction in either arm. Their class-slot growth falls from about **41,610 to 24,018**, exactly 17,592 fewer slots. All attempts remain included. Host pressure reaches 26.3% CPU and 0.25% I/O; quiet admission does not guarantee those conditions persist.

This comparison has its own matched control. Its saving is not subtracted from the earlier 39.20-second cohort to manufacture a lower time.

## Scope and correctness

`ClassOpts.PureData` explicitly identifies immutable values without cache-bound resources, session requirements, lazy parts or release hooks. Only the native two-string `ArtifactDimensionKey` opts in. The selector requires a plain-value list and stored builtin scalar fields, without arguments, type conditions or dynamic/implicit inputs. Cached result elements, resource hooks, computed methods, arrays, custom scalars and object selections retain ordinary handling.

The enclosing operation retains the parent list. A borrowed item keeps its concrete parent result and position in its call frame, and every scalar getter still passes through normal resolution and telemetry. Explicit object or ID access attaches the item normally. No cache format, compilation identity, lock, dependency or mutable cache volume is added.

Focused races, the full standalone-base DagQL race suite and 32 module-object/retention checks pass. The controlled engine also passes the full DagQL race suite and native metadata ID checks. A new native-field regression proves the optimized query creates zero item rows, then verifies that explicit access creates three valid, loadable IDs. The final isolated branch also passes the full DagQL race suite, all 32 top-level retention tests (65 including subcases), and every new projection check with concurrent lists from different sessions. Its direct validation is recorded with the evidence.

All six retained native Rust histories reuse every action before replacement, on their first candidate-enabled calls afterward and after the completed cohort: **130/130, 1,026/1,026 and 6/6**, twice each. Both replacements exit gracefully on the same volume, with no reset or forced termination. These are cache-correctness checks, not unchanged-build performance claims.

## Experiments that were rejected or corrected

The broad first prototype changes resource-release behavior. The initial probe incorrectly expected one callback; the unchanged control produces two. The corrected probe passes on the control and fails on that prototype. The explicit data-only policy preserves the control behavior. This establishes a lifecycle difference, not a diagnosed production resource leak.

The retained engine contained an older diagnostic that installed a dynamic-input hook on the same two string fields. That hook is retired in both timing arms. Their native uncached field policy remains equivalent to the previously selected setting; no eligibility guard is relaxed.

An incomplete compatibility adapter copied only the upstream typed-array marker and missed `DynamicArrayOutput`, used by reflected Go fields. Its completed cohort measures **39.44 → 41.37 seconds**, faster in only two pairs, and supports no speedup. The new native-field regression fails on that adapter and passes when both upstream marker types are present. The valid cohort begins only after a full wcprof capture proves the real fields take the new path.

A stale profiler assertion also fails on the unchanged selected source: instrumentation includes the result ID in a lock label, while the test expects its older name. The maintained diagnostic test asserts the exact result ID. Production locking is unchanged.

## Component tradeoff and remaining work

Four fresh-process pairs per case use ordinary GC and the same five-field fixture in both arms. For 1,026 new objects, projection improves **33.98 → 20.54 ms**, faster in all pairs. Repeated-parent projection is **17.08 → 17.29 ms**, with mixed latency and **6.27 MB more allocation**. One-object fresh and repeated cases improve in every pair. The full edited listing allocates less despite that component tradeoff.

The completed preflight returns the correct rows in 42.80 seconds with profiling enabled and records **397,854 wcprof events, zero dropped and none open**. It contains 20,921 publications; the indexed-key publication count is zero. Its main query spends 31.70 seconds discovering artifacts before the final metadata reads: package discovery takes 15.79 seconds and the longest test expansion 14.69 seconds. Those intervals include backend work and waiting; they do not establish a TOML parsing or network cost. Discovery remains the larger target. The reconstructed critical path assigns **29.41 seconds** to synchronous module API requests, **3.38 seconds** to the remaining publications and **3.03 seconds** to artifact item reads. CPU windows contain 200.52 sampled CPU-seconds over 45.15 seconds, including a final window after command exit; GC background marking accounts for 38.93 cumulative CPU-seconds. These diagnostic totals overlap and are not additional controlled savings.

[Review description](upstream-prs/data-list-projection.md). The [isolated branch](https://github.com/grouville/dagger/tree/perf/project-data-list-scalars), commit `5a36ffd0`, builds on the existing scalar-field policy proposal. No PR is open. [Retained evidence](experiments/scalar-list-projection/) includes all variants, failed probes, both cohorts, source identities, full outputs and profiles. The shutdown and upstream scalar-leaf follow-ups are separate investigations.
