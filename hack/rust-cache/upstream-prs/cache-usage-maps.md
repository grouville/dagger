Disk-usage collection allocates three empty maps per cached result even when that result owns no measured disk usage. In a cache with many scalar results, these maps add allocations while the cache prepares a prune snapshot.

Leave empty usage maps nil. Clone an existing size map only when it has entries, and allocate the published size and record-type maps on their first insertion. Results that lose ownership still have their old maps replaced, so stale measurements are cleared.

### Performance

Fresh measurements on `4cd7f219ff`, based on main `717589c9cc`. Both sides use the same tests and benchmarks; the baseline restores only the production files to main.

| Disk-usage snapshot | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| 200,000 scalar results | 586.47 ms | 507.08 ms | 151.57 MiB → 124.11 MiB | 1,602,878 → 1,002,878 |

Six alternating A/B and B/A pairs in fresh processes, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. One measured snapshot per process; fixture construction is outside the timer. These are component benchmarks, not complete Rust builds. They do not measure engine startup or remote cache transfer.

The snapshot was faster in all six pairs. Allocations fall by exactly 600,000 and allocated bytes by 28,800,000 (27.47 MiB). This measures disk-usage snapshot preparation, not normal cache lookup latency.

### Tradeoff and validation

This is a small allocation change within the existing locking and ownership flow. Map readers already use lookup, len and range, which accept nil maps. Nonempty maps are still copied, and each write follows allocation. The change does not add a lock, move work across a lock boundary or change which result owns a measurement.

The full dagql race suite exercises cache usage, shared ownership, pruning and cleanup. The benchmark already exists on main and checks that all 200,000 fixture results appear in the snapshot; no new test scaffolding is needed.

```sh
go test -race -count=1 ./dagql
```

To reproduce the component benchmark:

```sh
for sample in 1 2 3 4 5 6; do
  GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkCachePruneSnapshot/disk/200000$' -benchmem -benchtime=1x -count=1 ./dagql
done
```

Use identical benchmark sources on both sides and alternate execution order.
