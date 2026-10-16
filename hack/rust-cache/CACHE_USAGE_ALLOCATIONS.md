# Avoid empty maps while accounting for cache usage

Follow-up: the change is now also [measured on the retained Rust benchmark engine](REAL_CACHE_USAGE.md). Two eight-pair series reduce preparation from 563 to 538 ms and 567 to 530 ms, with about 14.4 MB and 302,000 fewer allocations. The report below records the earlier synthetic benchmark and validation; neither experiment establishes complete Rust-command savings.

[Fork commit `7fea7693f`](https://github.com/grouville/dagger/commit/7fea7693f), based on upstream `cbef9c953`, changes two files in `dagql`. No PR is open. The change avoids three empty map allocations for each result that owns no measured snapshot bytes.

The existing disk-usage snapshot benchmark with 200,000 scalar results allocates **600,000 fewer objects and 28.8 MB less memory per pass**. Allocation bytes fall by 18% and allocation count by 37%. All existing `dagql` unit tests pass with the race detector. At the time of this initial experiment, the change had not been installed in the owned Rust benchmark engine. No complete Rust-command speedup is claimed.

## The change

`cacheUsageInputLocked` previously allocated a map even when it had no previous sizes to copy. It now clones only a nonempty map. `publishUsageMeasurementsLocked` previously allocated size and record-type maps for every result. It now allocates each map when it first stores an entry, and assigns nil when there are no entries.

Assignments still clear old maps when ownership changes. Snapshot identities, size ownership, provider callbacks, graph locking and pruning decisions use the existing code. The callers read these fields using lookup, range or length, which accept nil maps. No lock, cache index, dependency or persisted format is added.

This code is used by the real engine. On the pinned upstream base, `engine/server/server.go` constructs `dagql.NewCache` with the snapshot manager and without `WithBlobStore`. `pruneLocalCacheLocked` calls its `Prune` method, which measures and publishes this usage. The code is also present in the owned engine's CPU profile; it is separate from the unused internal BuildKit implementation involved in the earlier mistaken fix.

## Measurements

Five paired observations alternate order and use a fresh process for each observation. They run the repository's existing `BenchmarkCachePruneSnapshot/disk/200000`, with one iteration and `GOMAXPROCS=8`. Fixture construction is outside the benchmark timer. The before binary substitutes the two unmodified files from the pinned base; all other source is identical.

| Per accounting pass | Before median | After median |
| --- | ---: | ---: |
| Allocation count | 1,602,878 | 1,002,878 |
| Allocated bytes | 158,934,504 | 130,134,504 |
| Time | 596 ms | 479 ms |

The median paired time saving is **49 ms**, with four of five pairs faster. Timing varies more than allocation counts; the difference between the two time medians is not the paired median. Do not extrapolate these timings to a Rust workspace or engine restart.

The initial output parser expected the standard benchmark metrics to be adjacent. The existing benchmark also prints its estimate and result count. The corrected parser retains the completed first observation and reads each metric by name. Its initial failure and every raw observation are archived.

## Verification

Focused ownership, cancellation, population-change and pruning tests pass under `-race`. The full `go test -race -count=1 ./dagql` passes in 66.178 seconds. These existing tests cover reassignment of shared sizes, callbacks outside the graph lock, row lifetime during measurement, cancellation and changed provider populations. The existing benchmark checks that the snapshot contains all 200,000 expected results. No duplicate functional tests are added for nil-versus-empty internal maps.

The remaining step is a controlled real-command comparison with this engine change enabled. The Rust module's state reduction was measured on the preceding engine binary, keeping the two experiments independent.

[Measurements, binaries' source substitutions and test logs](experiments/constant-scripts-and-usage-maps/).
