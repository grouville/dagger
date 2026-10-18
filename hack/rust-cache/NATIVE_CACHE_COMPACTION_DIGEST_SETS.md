# Reuse owned digest sets during cache compaction

On clean upstream main, the 131,072-class component benchmark reduces write-lock hold time **471.71 → 441.04 ms**, faster in all four pairs, and allocation **189.86 → 156.31 MB**, lower in every pair. The smaller case has mixed timing. The subsequent full-command screen does not establish a compaction benefit: path activity was not recorded during timing, and a separate diagnostic records zero compaction calls. The candidate remains off.

The [listing tail profile](NATIVE_GO_QUERY_ATTRIBUTION.md) motivates this change: cache maintenance overlaps queries, and class compaction consumes 9.17 CPU-seconds in its sampled tail. That diagnostic uses the experimental engine. The independent measurements below use main `ff0b029a`, its unchanged dependencies and one production-file patch.

## What changes and why it is safe

Compaction renumbers live cache classes. It currently clones each class's digest and extra-digest sets while rebuilding the tables. Those set entries contain no class IDs, so they need no rewriting. The patch moves the existing owned sets under their new outer-map keys.

The sets are private to the cache and protected by the existing graph lock. Current production mutation sites add entries or merge sets; individual entries are not deleted. Reusing them therefore retains their existing growth capacity. Dead classes still lose their sets, and the outer digest, term and result tables are rebuilt as before. The patch changes neither locks nor collection policy.

The source audit covers declarations, import, merge, publication, metadata export and remote entries. Exports copy values under the graph lock. Existing race-enabled tests verify class merges, reverse indexes, compaction, reset, metadata budgets and preserved live contents before and after the patch. No new functional test duplicates those checks. The added benchmark validates every rebuilt index outside its timer.

## Independent measurements on main

Each arm runs in a fresh test process. It prepares an in-memory cache with the stated live classes and 25% extra dead slots, then performs one compaction per size. Setup, validation and teardown are outside the timer. Normal GC remains enabled. These are component measurements, not engine startup, cache import or CLI timings.

Four pairs alternate execution order on Linux x86-64, Go 1.26.6, with eight Go scheduler threads. Separate column medians:

| Live classes | Write lock, before → after | Allocated, before → after | Faster pairs |
| --- | ---: | ---: | ---: |
| 16,384 | 42.45 → 41.95 ms | 23.74 → 19.55 MB | 2/4 |
| 131,072 | 471.71 → 441.04 ms | 189.86 → 156.31 MB | 4/4 |

The larger case makes **1,709,625 → 1,447,481 allocations**, saving 262,144 allocations and 33.55 MB per compaction. Its median paired saving is **22.95 ms**; that differs from subtracting the two column medians.

| Larger case pair | Before | After |
| --- | ---: | ---: |
| 1, candidate first | 497.24 ms | 437.58 ms |
| 2, control first | 452.35 ms | 444.51 ms |
| 3, candidate first | 480.11 ms | 472.74 ms |
| 4, control first | 463.31 ms | 425.24 ms |

An earlier fixed cohort on the controlled engine measured **470.92 → 432.38 ms**, faster in three of four larger-case pairs, with the same allocation reduction. Its smaller case measured **42.85 → 37.02 ms**, faster in four pairs. Both cohorts, including all regressions, are preserved. The main replication is required validation of the standalone patch; it does not replace the earlier observations.

```sh
go test -run '^$' -bench '^BenchmarkCompactLiveDigestSets$' -benchtime=1x -count=1 -cpu=8 -benchmem ./dagql
```

## Full-command screen and its limit

The controlled candidate is now installed in engine `2014598a` on the same retained volume. Both arms use the selected Go module `7568cd0`, CLI `e7ba08d0` and source `ff0b029a`. Each command starts a fresh CLI and receives a fresh source comment on the warm engine. Telemetry, ordinary GC, result caching and cleanup remain enabled. No compaction is forced. Every other unselected experiment stays off; profiling and event recording are off during timing.

The excluded initialization pair adds a real test and returns 4,399 rows. Four fixed alternating measured pairs remove it and return the same ordered 4,398 rows, all exiting successfully through cleanup:

| Pair | Copy sets | Reuse sets |
| --- | ---: | ---: |
| 1, candidate first | 38.59 s | 35.20 s |
| 2, control first | 37.86 s | 35.11 s |
| 3, candidate first | 38.27 s | 38.10 s |
| 4, control first | 37.26 s | 34.68 s |

Separate column medians are **38.06 → 35.16 s**; median paired difference is **2.66 s**. Engine allocation medians are **29.59 → 29.04 GB**. These observations alone do not show that the changed loops ran. During the cohort, estimated metadata stays below its 4 GiB maximum, rising from 3.10 to 3.44 GiB. Class-slot growth cannot rule out an intervening compaction.

A separate fresh-edited listing with compaction event recording enabled takes **38.46 s**, returns the same rows and exits successfully. It records **zero compaction calls**. No cache reset, forced collection or maintenance deferral is used. A bounded maintenance-log read also yields no matching events, but does not establish coverage of the timed interval. Consequently, **no complete-command saving is attributed to this patch**, despite the four faster timing pairs. This screen is retained rather than repeated to seek a favorable maintenance overlap.

The existing graph and metadata race checks pass with both controlled modes. Both real Go collection checks pass on a fresh fixture edit with reuse enabled. All six retained Rust histories hit every compiled action before replacement, on their first candidate-enabled calls afterward and after the cohort: **130/130, 1,026/1,026 and 6/6**, twice each. These verify cache correctness rather than build-time improvement. The replacement exits gracefully on the same volume. Sources, configuration, modes and profiling state are restored after both runs.

## Fork and remaining validation

[The standalone branch](https://github.com/grouville/dagger/tree/perf/cache-compaction-digest-sets) contains commit `9d36d0d39a`, based on verified upstream main `ff0b029a`. It changes one production file and adds the benchmark. The committed source matches the validated overlay byte for byte. [Its review description](upstream-prs/cache-compaction-digest-sets.md) states the measurement scope. No PR is opened.

The standalone proposal is supported by its component allocation reduction and larger-case write-lock measurement. The earlier pressure-heavy profile motivates it; its CPU totals cannot be scaled into a CLI saving, and the new screen establishes no such saving. The upstream review queue contains nineteen Dagger descriptions and one Go-module description.

[Sources, ownership audit, both fixed cohorts, race checks and standalone patch](experiments/compaction-digest-sets/).

[Controlled engine, complete-command screen, separate path-activity diagnostic and retained-cache checks](experiments/compaction-digest-sets-e2e/).
