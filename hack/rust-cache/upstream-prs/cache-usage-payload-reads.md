# perf: avoid cloning payload state for cache usage

Disk-usage sampling copies a cache record's full payload state, including its snapshot references. Revision checks copy those references just to read one number. Sampling an unloaded record copies them twice.

Read the required fields under the existing payload lock. Loaded records retain their value; unloaded records receive one independent copy of their snapshot references. Revision checks read only the revision after checking that the same record is still in the cache. Size maps keep their independent copies, and provider callbacks and resampling keep their existing behavior.

Four alternating component benchmark pairs on main `ff0b029a`, with its unchanged dependencies:

| Operation | Before → after | Bytes/op, before → after |
| --- | ---: | ---: |
| Capture loaded record | 541 → 198 ns | 736 → 256 |
| Capture unloaded record | 859 → 528 ns | 1,216 → 736 |
| Check loaded record's revision | 332 → 17 ns | 480 → 0 |

Every case improves in all four pairs, including scalar records and unloaded revision checks. The reference-bearing fixtures have four distinct snapshot paths. Each arm starts a fresh process with normal GC, Go 1.26.6 and eight scheduler threads. These measure usage sampling, not a complete CLI command.

Existing usage and pruning tests pass under the race detector before and after. The added regression checks that a sample owns its nested snapshot paths and size map, and becomes invalid after payload replacement.

```sh
go test -race -count=1 -run '^TestCache(Usage|Prune)' ./dagql
go test -run '^$' -bench '^BenchmarkCacheUsagePayload$' -benchtime=500ms -count=1 -cpu=8 -benchmem ./dagql
```
