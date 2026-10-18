# perf: reuse class digest sets during compaction

Cache compaction renumbers classes and rebuilds their indexes under the cache write lock. It also clones every live class's digest and extra-digest sets, although their entries contain no class IDs and stay the same.

Move those owned sets under their new class keys. The sets are private to the cache and only grow; deleting a class drops its whole set. The existing lock covers the transfer. Compaction still removes dead classes and rebuilds the digest, term and result indexes.

Four alternating benchmark pairs on main `ff0b029a`, using its unchanged dependencies:

| Live classes | Write-lock hold, before → after | Allocation, before → after | Faster pairs |
| --- | ---: | ---: | ---: |
| 16,384 | 42.45 → 41.95 ms | 23.74 → 19.55 MB | 2/4 |
| 131,072 | 471.71 → 441.04 ms | 189.86 → 156.31 MB | 4/4 |

Allocation falls in every pair. The larger case saves 262,144 allocations per compaction. The smaller case does not establish a timing improvement.

Each arm starts a fresh test process and compacts a populated in-memory cache once per size; setup, index validation and teardown are outside the timer. Tests use Go 1.26.6 on Linux x86-64 with eight scheduler threads and normal GC.

Existing graph and metadata tests pass under the race detector before and after the patch, including preserved live contents, merges, reverse indexes, reset and metadata budgets. The new benchmark exercises substantial live sets and checks the rebuilt indexes outside its timer.

```sh
go test -run '^$' -bench '^BenchmarkCompactLiveDigestSets$' -benchtime=1x -count=1 -cpu=8 -benchmem ./dagql
```

A full-listing profile under cache pressure motivated investigating compaction. A subsequent complete-command screen did not establish its impact: path activity was unrecorded during timing, and a separate listing recorded zero compaction calls. This proposal claims the component allocation reduction and larger-case timing above.
