# perf: avoid quadratic span indexing

Adding a span currently scans its parent's existing children to avoid duplicate IDs. With thousands of siblings, indexing the trace becomes quadratic. The parent map already tells us whether an ID has been seen with a parent: skip the scan for new IDs and retain it for cross-trace collisions. Deduplicate cause links through their existing reverse index as well.

Six fresh-process pairs directly on main, including construction of a new index on every iteration:

| Children | Parent index, before → patch | Cause index, before → patch |
| --- | ---: | ---: |
| 1 | 0.890 → 0.822 µs | 0.891 → 0.879 µs |
| 1,026 | 1.878 → 0.462 ms | 1.978 → 0.484 ms |
| 4,096 | 24.742 → 1.942 ms | 25.511 → 2.099 ms |

Allocation counts are unchanged. Fixtures use mixed IDs and decoded links; storage and link decoding are outside this index benchmark. Go 1.26.6, linux/amd64, `GOMAXPROCS=8`, 150 ms per case.

On the full `dagger/dagger` Go test listing, new-session indexing performs over **two billion** ordinary-child comparisons. Three successful paired comparisons improve complete-command medians **53.58 → 46.72 seconds**, with **7.05 seconds** median paired saving and identical 4,398 rows. All four optimized attempts succeed; one control times out during session shutdown and is excluded from paired latency statistics. Each command uses a fresh source edit and CLI on the same warm engine, with telemetry and ordinary GC enabled. No profiling or counters run during timings.

The isolated index adds no allocations. This full-command cohort does not establish a memory gain: cumulative allocation is 36.32 → 37.19 GB, and disk-pressure differences affect the last pair. The low-IO pair still saves 7.78 seconds. A diagnostic attributes 4.74 → 0.12 sampled CPU-seconds to the index functions in different phase windows; this confirms the removed work, not a matched total-CPU comparison.

Earlier 1,026-package Rust listings remain mixed across 32 pairs: 119 ms median paired saving, with an uncertainty interval including zero. No compilation speedup is claimed.

No map, lock or retained state is added. Cause links update both directions under the existing lock. The compatibility test preserves cross-trace duplicates, ordering and late parent/link updates; it passes before and after the patch. The full `engine/clientdb` race suite passes on the standalone branch. All six native Rust compiler-cache histories remain reusable.

```sh
go test -race ./engine/clientdb -count=1
go test ./engine/clientdb -run '^$' -bench '^BenchmarkSpanLookupFanout$' -benchmem
```

[Branch](https://github.com/grouville/dagger/tree/perf/upstream-span-lookup-fanout) · [Go listing measurements and limitations](../NATIVE_GO_WIDE_TRACE_INDEX.md) · [Component and Rust evidence](../NATIVE_SPAN_LOOKUP_FANOUT.md). No PR is open.
