# Read collection dimension keys directly

The standalone change [104f7ab5b](https://github.com/grouville/dagger/commit/104f7ab5b211a739b29cce40bd0fe492617b1b86) adds two field annotations and reduces a complete edited Rust collection listing from **3.743 to 2.877 seconds** median. The candidate is faster in **16/16 pairs**, with a **794 ms median paired saving** and **808 MB fewer allocated bytes per pair**. This is a listing improvement; edited compilation has no established gain.

## Change and measured path

`core.ArtifactDimensionKey` stores two strings: `Dimension` and `Key`. Expanded collection listings read both for every dimension key. Each read currently uses the normal result-cache lookup, ownership and publication path, even though the resolver only returns a struct field.

Add `doNotCache:"simple field selection"` to those two fields, following the existing `TypeDef` getters. The parent objects and their IDs retain their existing cache policy. Compiler results and incremental state remain native immutable Dagger snapshots. The production change is two struct tags, with no new lock, state, serialization format or API.

Paired wcprof captures verify the active engine path. Listing publications fall from **13,677 to 7,521**: exactly **6,156** string-result publications disappear. Both modes still execute all 3,078 reads of each string field and return the exact 1,026-package set. Field telemetry remains enabled. The engine avoids the execution and publication spans associated with work it no longer performs.

## Complete commands

Two eight-pair series rotate Dagger-before, Dagger-candidate and Cargo order; confirmation reverses the Dagger ordering. Every command uses a fresh process and a fresh edit to a used Rust value, with the same physical source tree and native cache history. Engine and compiler caches are warm. One preparation round per workload is excluded by design. Telemetry stays enabled through a local receiver; these measurements do not establish production Cloud latency.

The Rust module remains `3cd40e5928563ade3ea1cd21ab9924cd03d88fc3`. The diagnostic engine preserves the prior overlays and varies only the two getters' cache policies through an atomic flag. Wcprof and CPU profiling are disabled during the timed cohorts. Ordinary snapshot collection remains enabled; neither Go GC nor snapshot GC is forced.

| Complete edited command, 16 pairs | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Expanded listing, 1,026 packages | 3.743 s | 2.877 s | 0.441 s | 794 ms | 16/16 |
| Grouped check, 1,026 crates | 1.458 s | 1.520 s | 0.771 s | −90 ms | 5/16 |
| Direct check, 130 crates | 0.612 s | 0.616 s | 0.112 s | −28 ms | 5/16 |
| Small workspace tests | 0.955 s | 0.960 s | 0.494 s | 1 ms | 8/16 |

The initial listing comparison is **3.750 → 2.842 s**; confirmation is **3.631 → 2.904 s**. All eight pairs improve in each series. Pooled listing engine CPU falls from **16.18 to 12.17 CPU-seconds** median. Allocations are lower in all sixteen pairs, by **807,693,360 bytes** median per pair. Allocated bytes do not measure peak or resident memory. Differences between column medians are not median paired differences.

All admitted observations are retained. No listing overlaps snapshot collection. Host CPU pressure reaches 31% during listings. One Cargo metadata control encounters 71% host I/O pressure, with no engine I/O pressure; the other high-I/O observations occur in direct/Cargo controls. Admission windows cannot guarantee quiet conditions throughout a command.

## Why the check controls do not establish a regression

The slower check samples warranted a separate investigation. An eight-pair check-only series, without interleaved listings, gives **1.478 → 1.551 s**, with a **43 ms median paired slowdown**. Go GC runs during one original and four candidate samples.

An additional eight-pair identical-policy control keeps both labeled arms on the original implementation. It still gives **1.443 versus 1.516 s**, with a **30 ms median paired difference** and the same **one versus four** Go-GC samples. That demonstrates that this harness and allocation cycle can produce an apparent check slowdown without changing the implementation.

New paired check profiles contain **zero calls** to either modified getter and exactly **147 publications** in both modes. These profiles identify the same executed path in this workload. The controls support no compilation-speed claim; the observed timing and GC imbalance remain in the evidence rather than being discarded.

## Standalone measurements and validation

Six fresh-process pairs compare test binaries built directly from main and the two-tag patch, with identical test sources. Order alternates. Go 1.26.6, `GOMAXPROCS=8`, linux/amd64, Intel Core i5-9300H; 150 ms per case. Fixture construction is outside the timer. Every iteration changes the parent generation, so the original implementation must publish fresh child results rather than answer an unchanged query from cache.

| Dimension-key objects per query | Time before → candidate | Allocated bytes before → candidate | Allocations before → candidate |
| --- | ---: | ---: | ---: |
| 3 | 384.81 → 265.31 µs | 113,019 → 80,712 | 1,461 → 989 |
| 3,078 | 226.11 → 85.56 ms | 96,482,552 → 63,404,816 | 1,190,767 → 706,397 |

Both sizes improve in all six pairs. Maximum host CPU/I/O pressure over the complete benchmark processes is 4.1%/6.7%. The fixture uses ordinary Go-test telemetry configuration; the complete-command cohorts above keep engine telemetry enabled.

The production patch is extracted directly onto upstream main `717589c9ccacbba7d3cf902647aa5c9ca68085e8`, fetched again before extraction. Focused artifact/schema tests pass under the race detector on both the diagnostic source and the standalone branch, and normally on both standalone main/candidate binaries. The compatibility test reads both fields, reloads their parent objects by ID and checks distinct generations through the GraphQL response format. It passes on main as a compatibility check; the performance difference is established by benchmarks.

All six retained native Rust histories also pass with direct metadata reads enabled: **130/130**, **1,026/1,026** and **6/6** actions reused, twice each. The verifier first compiles each current input because the final Cargo or listing edit may not have been compiled by Dagger. These unchanged executions verify retention after the engine restart and are excluded from performance measurements.

## Diagnostics and remaining work

The installed engine is `4699d50526e3b2c358d0467c6cacc79aff1061b9295754648713a21104524c65`. Its predecessor exits cleanly after 102 seconds, before installation, with the cache volume preserved. Shutdown stacks locate a wait in persistence mirror deletion; that time is outside every command measurement. The new engine passes three quiet admission windows before timing begins.

Four separate diagnostic captures retain engine/CLI CPU profiles, CLI runtime traces, wcprof and bounded goroutine snapshots. Every wcprof capture has zero dropped events and zero open operations. The candidate listing still spends about **495 ms** of its reported critical path publishing results and **769 ms** reading artifact items. Stored protobuf-JSON decoding and span conversion remain substantial CPU costs; the cumulative CPU figures overlap and are not additive wall time.

Direct key-field reads are selected for subsequent experiments on the owned engine. All other temporary measurement modes are restored; profiling is off, ordinary snapshot collection is enabled, and no clients remain active. The final runtime state is archived so later comparisons can account for this selected change.

The native Rust backend remains experimental. Registry dependencies, general build scripts, procedural macros and automatic remote state discovery remain unfinished. This getter change addresses collection-listing overhead within that larger effort.

[Prepared description](upstream-prs/artifact-dimension-key-fields.md) · [Fork branch](https://github.com/grouville/dagger/tree/perf/upstream-artifact-dimension-key-fields) · [Raw commands, controls, sources and profiles](experiments/artifact-dimension-key-fields/). No PR is open.
