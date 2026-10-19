# Parallel client admission does not establish a listing improvement

## Current compact-owner retest

The current-stack retest remains unselected: complete test-edited listing changes **10.16 → 9.64 seconds median**, faster in three of four pairs; ordinary-source listing changes **6.70 → 6.79 seconds**, faster in two pairs. Test-edit engine CPU rises slightly **52.25 → 52.53 CPU-s**. The modest, mixed command-level result does not justify selecting the additional concurrency.

The preceding compact-owner profile records 2.35 seconds of lifecycle waiting on the main-query critical path, motivating the retest. Both arms use the same engine binary, CLI and Go module `de633b12ed2aa02e42adb698a23fcecc13faf36d`; only the existing parallel-admission switch changes. Prepared-schema reuse is enabled in both, with callback-caller reuse and shared receiver decoding disabled. Each command starts a fresh CLI and makes a real edit on the warm engine; both arms complete test addition and removal before four measured pairs per workload. All 24 commands return correct ordered names and identical full rows, and exit successfully with telemetry, ordinary GC and full cleanup included.

Four lossless captures separate test edits from shared discovery, with no dropped or open operations. Increasing admission concurrency makes lifecycle waits cease dominating the candidate's critical path, while API waits, telemetry flushing and other work take more of it. Those diagnostic durations are not additional latency gains. Test-edited captures retain 804 evaluations, 1,494 SDK requests, 800 getter executions and the same 799 discovery hits plus one execution.

The separate current allocation attribution also finds that converting the repeated collection-key lists costs only **0.16 sampled CPU-s out of 51.04 CPU-s**. Their 640,000 entries are a scaling concern, not evidence that a new conversion cache would materially improve this command. Direct callback-wrapper allocation has a larger measured cost and leads to the useful [callback-caller retest](NATIVE_DANG_CALLBACK_CALLER.md). Configuration freshness guards still issue many requests; earlier in-progress read sharing remains rejected for stale observations after edits.

No new admission code is added and the switch is restored to disabled. All four retained engines and cache volumes remain unchanged. [Current measurements, attribution and all profiles](experiments/go-runtime-preparation-current/).

## Earlier comparison on the older stack

Complete Go test listing takes **48.69 → 48.48 seconds median** over four alternating pairs. All commands return the correct rows and exit successfully, but the variation is much larger than the difference. The candidate remains disabled. The selected full-command result remains **53.58 → 46.72 seconds** from the separate [span-index comparison](NATIVE_GO_WIDE_TRACE_INDEX.md).

## The measured queue

A diagnostic of `dagger check --module go --check test --list --all` completes in 45.32 seconds with the expected 4,398 rows. Sampled mutex and block profiles identify session-wide client admission as the largest contended unlock site. The main query lasts 42.86 seconds; wcprof attributes 30.41 seconds to synchronous requests from Dang. Those intervals include client encoding, transport and backend work, not network delay alone. All 582,308 events are retained, with none dropped or open.

`getOrInitClient` holds the session lifecycle mutex through client-specific schema and runtime setup. Unrelated nested clients consequently queue behind each other. Its mutex samples represent aggregate waiting across concurrent goroutines; they cannot be interpreted as seconds available to remove from command latency.

The experiment gives nested admission a read lock on session lifetime, serializes admission within each client before entering the scope lock, and protects initialization of the shared session gateway. Root admission and session transitions retain exclusive locking. Request leases, metadata sealing, transport validation, cache lookup, ownership checks and telemetry use the existing paths. The standalone production change is 37 changed lines in `engine/server/session.go`; diagnostic controls are excluded.

## Full-command comparison

Both arms use one engine binary, CLI and Go module. The control uses the exclusive arm of the new reader/writer lock; both arms retain the gateway initialization guard. Each invocation starts a fresh CLI and edits source on a warm engine. Normal telemetry, snapshot collection and span indexing remain on. Profiling, counters and unrelated candidates are off.

| Pair | Serialized admission | Parallel admission |
| --- | ---: | ---: |
| 1, candidate first | 48.74 s | 48.63 s |
| 2, control first | 42.52 s | 52.82 s |
| 3, candidate first | 48.65 s | 47.05 s |
| 4, control first | 51.94 s | 48.33 s |

All eight measured commands return identical 4,398 rows and exit zero. The separate initialization pair adds one real test, returns identical 4,399 rows in 45.42 → 42.63 seconds, and is excluded. Removing that test restores the original listing. Every admitted observation is retained.

The candidate is faster in three of four pairs; median paired saving is 0.85 seconds. Column medians differ by only 0.21 seconds. Engine CPU rises **235.97 → 239.25 CPU-seconds**, allocation stays **37.57 → 37.58 GB**, and sampled peak heap rises **13.40 → 13.80 GB**. Peak heap is not retained memory. Host I/O stalls reach 6.05% in controls and 8.98% in candidates; engine I/O reaches 0.34% and 0.78%. These results do not justify selecting the additional concurrency or claiming a regression-free latency gain.

## Correctness and scope

The new regression pauses one nested client at schema setup and requires another to reach that boundary independently. It fails on the original implementation and passes on the candidate. Closing either transport while initialization is paused must retain its admitted request lease. A separate test checks concurrent construction of the shared session gateway. The full server unit package and race check pass; the controlled modes are checked separately.

The standalone patch applies to clean upstream snapshot `ff0b029a4d270a651b9a8c7286babc79089066e4`. On that checkout, the regression also fails before the patch and passes with the patch under focused race checks covering metadata, transport closure, initialization and session teardown. This verifies the actual engine path, independent of the profiling overlays.

The owned engine restarts gracefully on the same volume. All six native Rust histories reuse every compiler action before and after restart, and again with the candidate enabled: 130/130, 1,026/1,026 and 6/6 on each side. These are correctness checks, not performance measurements. The engine now runs `1b314892…`; the candidate and profilers are off, normal GC is enabled and no session remains active. No PR is opened.

The [wait-profile archive](experiments/go-listing-lock-profile/) and [candidate archive](experiments/session-parallel-client-init/) retain the measured path, standalone patch, tests, complete cohort, exact overlays, allocation attribution, pressure and restored state. The [next combined CLI/engine capture](NATIVE_GO_LISTING_CLIENT_ENGINE_PROFILE.md) investigates repeated work rather than assuming that eliminating a queue improves elapsed time.
