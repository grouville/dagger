# Reuse owned digest sets during cache compaction

On clean upstream main, the 131,072-class component benchmark reduces write-lock hold time **471.71 → 441.04 ms**, faster in all four pairs, and allocation **189.86 → 156.31 MB**, lower in every pair. The smaller case has mixed timing. Complete-command improvement remains unmeasured; the patch is not installed in the retained engine.

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

## Fork and remaining validation

[The standalone branch](https://github.com/grouville/dagger/tree/perf/cache-compaction-digest-sets) contains commit `9d36d0d39a`, based on verified upstream main `ff0b029a`. It changes one production file and adds the benchmark. The committed source matches the validated overlay byte for byte. [Its review description](upstream-prs/cache-compaction-digest-sets.md) states the measurement scope. No PR is opened.

The full-listing effect still needs measurement. The profile's CPU totals cannot be scaled into an expected CLI saving. The six retained Rust history checks validate the profiling engine; this compaction candidate has not yet run in that engine. The upstream review queue now contains eighteen Dagger descriptions and one Go-module description.

[Sources, ownership audit, both fixed cohorts, race checks and standalone patch](experiments/compaction-digest-sets/).
