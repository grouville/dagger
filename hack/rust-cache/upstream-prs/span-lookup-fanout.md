# perf: avoid quadratic span indexing

Adding a span currently scans its parent's existing children to avoid duplicate IDs. With thousands of siblings, indexing the trace becomes quadratic. The parent map already tells us whether an ID has been seen with a parent: skip the scan for new IDs and retain it for cross-trace collisions. Deduplicate cause links through their existing reverse index as well.

Six fresh-process pairs directly on main, including construction of a new index on every iteration:

| Children | Parent index, before → patch | Cause index, before → patch |
| --- | ---: | ---: |
| 1 | 0.890 → 0.822 µs | 0.891 → 0.879 µs |
| 1,026 | 1.878 → 0.462 ms | 1.978 → 0.484 ms |
| 4,096 | 24.742 → 1.942 ms | 25.511 → 2.099 ms |

Allocation counts are unchanged. Fixtures use mixed IDs and decoded links; storage and link decoding are outside this index benchmark. Go 1.26.6, linux/amd64, `GOMAXPROCS=8`, 150 ms per case.

A real 1,026-package listing produces **89 million** ordinary child comparisons that this patch skips. Its diagnostic profile reduces sampled indexing CPU from **0.58 to 0.11 CPU-second**. Full-command results remain variable: listings improve in 20/32 pairs, with 119 ms median paired saving, but the uncertainty interval includes zero. No compilation speedup is claimed.

No map, lock or retained state is added. Cause links update both directions under the existing lock. The compatibility test preserves cross-trace duplicates, ordering and late parent/link updates; it passes before and after the patch. The full `engine/clientdb` race suite passes on the standalone branch. All six native Rust compiler-cache histories remain reusable.

```sh
go test -race ./engine/clientdb -count=1
go test ./engine/clientdb -run '^$' -bench '^BenchmarkSpanLookupFanout$' -benchmem
```

[Branch](https://github.com/grouville/dagger/tree/perf/upstream-span-lookup-fanout) · [Measurements, profiles and limitations](../NATIVE_SPAN_LOOKUP_FANOUT.md). No PR is open.
