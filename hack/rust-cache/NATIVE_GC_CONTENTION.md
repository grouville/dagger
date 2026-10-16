# Snapshot collection competes with edited Rust builds

Controlled overlap makes a complete edited 1,026-crate check slower: the median is 1.56 seconds without added work, 1.83 seconds during cache accounting and 2.46 seconds during containerd collection. This establishes interference under the measured conditions. It does not establish the cause of the earlier 15–18-second command stalls.

The experiment also exposed a smaller, independent upstream issue: pruning a scalar value asks containerd to scan snapshots even when no snapshot lease was released. A regression against the production cache initializer fails on upstream main. Replacing its unconditional collection callback with the existing `CollectIfPending` callback passes that regression and the existing reclamation tests. This is narrower than changing collection scheduling.

## Controlled complete commands

Eight rotating four-way comparisons use the same physical workspace and the selected native Rust module, `f73c561`. Every observation edits a used leaf and runs `check rust:packages/check`. CLI and helper processes are fresh; engine, module and compiler caches are warm. Telemetry remains enabled. Profiling is disabled in these comparisons.

| Concurrent work | Median command | Median paired penalty vs idle | Slower pairs | Median case including teardown and final collection |
| --- | ---: | ---: | ---: | ---: |
| None added | 1.563 s | — | — | 2.785 s |
| Existing cache accounting | 1.829 s | +241 ms | 7/8 | 3.162 s |
| Accounting with lazy usage maps | 1.921 s | +330 ms | 8/8 | 3.166 s |
| Containerd collection | 2.461 s | +886 ms | 8/8 | 3.764 s |

Before each observation, the driver creates and retires a separate scratch snapshot containing 10,000 small files. This happens outside the command timer. Ordinary containerd collection is deferred in every arm; the selected background job starts immediately before the command. The scratch snapshot must survive until collection and disappear afterward. Cache pruning remains enabled, and the accounting jobs only measure usage. All accounting observations report a complete measurement, covering 50,626–51,245 retained results as the history grows.

Every command is followed by a real collection outside its timer, including the idle arm. Thus the case timer includes the cost of postponed cleanup; it excludes fixture preparation and the preceding cleanup. The collect arm also performs an earlier collection and does not represent an equal number of collection passes. Neither timer is a benchmark of a proposed production scheduling policy.

Admission requires no active client and a one-second window below 5% host and 1% engine I/O pressure. Later stalls remain included: post-command collections reach 8.37, 4.52 and 9.60 seconds. The metadata estimate stays below 675 MB against a configured 4 GiB limit, so automatic metadata pressure does not trigger this test. The usage-map change establishes no complete-command improvement in this comparison; its separately measured allocation benefit remains a component result.

## What wcprof shows

A separate profiled pilot has one measured observation per arm, plus preparation. All six captures have zero dropped events and zero open operations. During the measured collection, two `Host.directory` operations take 828.69 and 825.51 ms, compared with 17.32 and 16.12 ms in the idle observation. The third directory import takes about 170 ms in both. The collector overlaps these operations for about one second.

These observations locate interference in filesystem preparation. They do not prove a direct mutex wait or justify adding durations from concurrent operations. The collector and accounting durations are separate from the foreground critical path. Engine, sibling exec and Docker-parent CPU counters are recorded separately; the parent overlaps both children.

## Scope of the upstream fix

The cache installs `snapshotGarbage.Collect` as its callback after disk or metadata pruning. Metadata pruning can remove a scalar without changing containerd at all, but the callback still walks containerd's live resources. `snapshotGarbage` already tracks deletions through containerd's mutation callback, retries failed collections and requests one collection after startup. Use that existing condition for the prune callback too.

This adds no lock, index, scheduler or diagnostic endpoint. The disk-prune callback and the server's final pending collection remain in place. Existing tests cover actual released snapshots, explicit prune, GC disabled, protected snapshots and failures in the disk-stat stage. The new regression uses the real production initializer and counts actual containerd collection starts for both scheduled and explicit scalar pruning.

The Rust benchmark engine remains below the metadata-pressure limit, and real lease releases still require collection. This fix is therefore useful for avoiding needless scans, but no complete Rust-command saving is attributed to it.

Six alternating fresh-process comparisons of the actual explicit metadata-prune path take **4.004 ms → 25.30 µs** with 1,000 retained empty snapshots, improving in all six pairs. Allocated bytes fall from 1.93 MB to 2.90 kB and allocations from about 32,124 to 31. With no snapshots, the medians are 53.95 → 24.35 µs. Initialization, snapshot construction and scalar insertion are outside the timer; the store and prunes are warm. The native snapshotter retains every fixture snapshot, verified after measurement. Whole-process host I/O pressure, including fixture setup, reaches 9.34%; all completed observations remain included.

The [standalone fork proposal](upstream-prs/skip-empty-snapshot-gc.md) changes one production line. Seventeen focused server tests pass normally and under the race detector. Both regression subcases fail without the patch. Eight diagnostic lifecycle tests also pass together after removing an inherited fixture-report environment variable that had caused an earlier parallel-test collision. An initial benchmark reused a released cache session and failed; the corrected benchmark uses a fresh session per iteration. A first static race binary failed during glibc user lookup before reaching tests; the successful build selects Go user and network lookups for the minimal engine image. The initial failure logs are retained.

[Raw observations, diagnostic sources and drivers](experiments/snapshot-gc/) retain all admitted samples, cleanup timings, exact source hashes, wcprof dumps and validation logs. Diagnostic collection deferral is restored to false after the experiment. The standalone change is kept separate from that instrumentation; no PR is opened.
