Metadata pruning can evict scalar values without releasing any snapshot lease. The cache still calls `snapshotGarbage.Collect`, which scans containerd's live resources even when nothing has been deleted there.

Install the existing `CollectIfPending` callback instead. It uses containerd's deletion signal, collects once after startup and retries failed collections. Actual lease releases still trigger collection. The production change is one line and uses the existing synchronization.

Six alternating before/after comparisons in fresh processes, based on main `717589c9cc`, measure an explicit metadata-only prune in a warm store:

| Retained snapshots | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| 0 | 53.95 µs | 24.35 µs | 13.16 kB → 2.90 kB | 141 → 31 |
| 1,000 | 4.004 ms | 25.30 µs | 1.93 MB → 2.90 kB | ~32,124 → 31 |

Each case improves in all six pairs. Actual containerd collections fall from one to zero per prune. The temporary stores use the native snapshotter and empty snapshots held by a lease; every snapshot is checked afterward. Server initialization, snapshot construction and scalar insertion are outside the timer. Go 1.26.6, linux/amd64, `GOMAXPROCS=8`, 150 ms per case. Host pressure is recorded over the whole process, including fixture construction; its maximum I/O stall fraction is 9.34%. All completed samples are retained.

The regression initializes the real server cache and verifies both scheduled and explicit scalar pruning. It fails on main because each path starts a collection, and passes here. Seventeen focused server tests pass normally and under the race detector, including actual snapshot reclamation, retained snapshots, GC disabled, explicit prune, cancellation and disk-stat errors.

```sh
GOMAXPROCS=8 go test -race -count=1 -run '^(TestLocalCacheMetadataPruneDoesNotCollectSnapshots|TestSnapshotGarbage.*|TestGCLocked.*|TestExplicitPrune.*|TestManual.*Prune.*|TestLocalCacheStateTakesTheBuiltinStore|TestGCSessionCompletionClearsMetadataPruneBlock|TestScheduledGCTrimsImportedMetadataWithoutPersistenceReset)$' ./engine/server
GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkLocalCacheMetadataPrune$' -benchmem -benchtime=150ms -count=1 ./engine/server
```

These are prune measurements. Complete Rust-command savings from this change have not been established. [Raw measurements, test logs and exact sources](../experiments/snapshot-gc/) also include the separate collection-contention experiment; its diagnostic scheduling controls are outside this change.
