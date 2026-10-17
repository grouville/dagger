# Allocate Dang type maps only when used

The [completed comparison after the span-index change](NATIVE_DANG_TYPE_MAPS_CONFIRMATION.md) returns correct rows and successful exits, but shows no material full-listing gain: **48.83 → 48.74 s** across three usable pairs. Allocation falls by about 1 GB per command. The candidate remains disabled. The earlier interrupted experiment below is retained for provenance.

The Go collection profile attributes 2.32 GB of sampled allocations to `dang.NewType`. It allocates nine maps even for empty scopes used during evaluation. The same constructor is present on upstream Dang main at `da1bed304cb80f8a2f0714f1747e7f64e03297a3`.

The candidate leaves those maps nil until their existing writers need them. Reads, iteration and deletion keep their existing behavior. `Add`, `AddObject` and `AddDirective` reuse the origin setters; explicit visibility before `Add` remains preserved. There is no new lock, shared cache or dependency.

Full Dang package tests pass on the baseline, and the candidate passes the full package with the race detector. The added behavior check covers inherited lookups, child overrides, origin metadata, visibility and parent isolation.

Four sequential benchmark runs alternate before/after/after/before, with three samples per scope case in each run. Medians:

| Scope operation | Before | After | Allocated bytes before → after | Allocations before → after |
| --- | ---: | ---: | ---: | ---: |
| Empty scope | 506.60 ns | 130.00 ns | 1,008 → 576 | 10 → 1 |
| Clone | 523.45 ns | 134.95 ns | 1,008 → 576 | 10 → 1 |
| Clone with one local binding | 842.55 ns | 614.75 ns | 1,920 → 1,632 | 14 → 8 |

These component results do not establish a full-command gain. A controlled-engine comparison switches only eager versus lazy constructor initialization, retaining writer guards in both arms. It uses the selected Go module and CLI, fresh edits, normal telemetry and normal GC. The initialization pair adds a real test and returns identical 4,399 rows in 51.53 → 50.50 seconds. Allocated bytes fall from 36.27 to 35.09 GB. This pair is excluded from latency claims.

The first measured candidate run removes that test and returns the expected 4,398 rows, but exits with a ten-second session-shutdown timeout after 52.25 seconds. The planned timing cohort stops there. **There is no successful measured pair and no established full-command speedup. The map candidate remains unselected.** All attempts are retained.

A subsequent diagnostic with eager maps completes in 57.54 seconds with identical rows and exit zero, but captures a similar closing wait. The main shutdown handler is blocked in trace `ForceFlush`; the worker is indexing child spans with the original quadratic `spanLookup.addLocked` loop. The 15-second CPU sample windows attribute 4.74 CPU-seconds to that function. This capture identifies an expensive close path; it does not reproduce the earlier deadline failure or prove its cause. The existing span-index optimization is the next controlled comparison on this larger workload.

The experimental engine was replaced with a graceful shutdown on the same volume. All six retained Rust cache histories still reuse every action after restart (130, 1,026 and six actions on each side). Shutdown takes 108.3 seconds in this accumulated engine state; this is outside command timing. An unbounded startup log reader was cancelled after restart succeeded, and startup validation resumed with a bounded log tail. The engine was not interrupted or reset.

The independent next algorithmic target is the module's insertion sorting of path lists. Sorting cannot simply be removed: a directory walk visits `a/b.go` before the sibling `a.go`, while Go byte order requires the reverse. Any replacement must preserve file ordering across host sources, snapshots, overlays and mounts.

The allocation profile also narrows the next interpreter target: 1.43 GB (61.8%) of `NewType` allocation comes from `BoundBuiltinMethod.Call`. It creates a temporary type and object to pass a receiver to a wrapper that only reads `scope.Self()`. Passing that receiver directly could remove more work, but requires preserving custom callback behavior, defaults and block contexts. No such change has been implemented or timed.

[Complete source, checks, attempts and diagnostic captures](experiments/dang-lazy-type-maps/).
