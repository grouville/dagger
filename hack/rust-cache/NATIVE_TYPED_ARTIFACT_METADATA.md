# Read artifact metadata as immutable data

Complete edited Go test listing on real `dagger/dagger` improves **40.86 → 26.76 seconds median**, faster in all four alternating pairs. The prototype combines a typed metadata API with generic projection of immutable native data. Every command returns identical rows and exits successfully through cleanup. This is a measured improvement on the controlled development stack, not stock main; three seconds remains unachieved.

## Complete command

Both arms use the same new CLI and engine, unchanged selected Go module, retained volume and source checkout. Only the diagnostic API choice and projection control differ. Every invocation starts a fresh CLI and adds a fresh Go source comment. Telemetry and ordinary GC stay enabled; profiling, forced collection, cache resets, budget changes and cleanup deferral stay off. Timing includes command exit, cleanup and a final log flush.

| Measured pair | Existing path | Typed metadata and projection |
| --- | ---: | ---: |
| 1, candidate first | 44.35 s | 24.78 s |
| 2, control first | 32.98 s | 28.42 s |
| 3, candidate first | 53.52 s | 39.08 s |
| 4, control first | 37.38 s | 25.10 s |
| Median | **40.86 s** | **26.76 s** |

Median paired saving is **13.36 seconds**. All eight measured commands return the same ordered 4,398 rows. The excluded initialization pair adds a real test and both arms observe 4,399 rows; measured pairs remove it. No attempts are discarded. Source and configuration are restored afterward.

CPU falls in all four pairs, with column medians **169.21 → 110.83 CPU-seconds**. Allocation also falls in every pair: **27.97 → 18.53 GB** by column medians. These are cumulative allocations, not peak memory. Host CPU pressure reaches 25.0% and I/O pressure 5.8%. Ordinary maintenance overlaps several commands, including the slow candidate; all remain in the comparison.

The engine is warm. Cold startup is unmeasured. These medians are from a new matched cohort and must not be subtracted from or added to the previous 35.12-second diagnostic median.

## What changes

`Artifacts.metadata` uses the existing collection expansion, then returns addresses, descriptions and ordered dimension keys as typed native records. It does not evaluate artifact values. The records copy their display data and carry no workspace handles, executable values, module trees or release callbacks. Existing `items`, IDs, selectors and execution APIs remain available.

DagQL can project generated struct accessors on explicitly immutable native data without preparing and publishing a cache result for every intermediate field. It supports nested data arrays, nullable values, aliases and `__typename`. Custom resolvers, ID selections, type conditions, arguments, implicit inputs, resources and custom scalar implementations retain normal resolution. Selected schema views still determine the eligible field.

The private accessor proof belongs to the generated getter. A replacement resolver clears it even when it extends the old field specification. The regression test fails with an unsafe control that inherits the old proof. Runtime checks also reject values with resource ownership or custom scalar behavior, even when they advertise builtin names.

The parent list remains retained by the operation. Serialization checks the live session and its bound resources, and rechecks requirements and session release at completion. It uses the existing session-operation and graph-lock order; it adds no global mutex, retained plan cache or new dependency. Ordinary telemetry and log export remain enabled. Bulk projection has an aggregate wcprof operation.

The new API is typed; no opaque JSON payload or Go-specific path is introduced. The prototype's CLI environment switch and debug controls are experimental wiring, not proposed user-facing settings.

## Separate the two parts

A separate frozen fixture contains the same 800 package keys and 4,398 names in normal nested collections. Four balanced measured blocks follow one initialization block. All **20 commands** return identical complete rows and succeed through cleanup.

| Frozen-fixture path | Complete-command median | Allocated bytes median |
| --- | ---: | ---: |
| Existing path | 12.26 s | 9.74 GB |
| Generic projection only | 9.53 s | 6.66 GB |
| Typed metadata API only | 11.52 s | 7.97 GB |
| Both | **6.74 s** | **3.97 GB** |

The combination is faster and uses less CPU and allocation in all four pairs. Merely moving metadata into another API leaves most per-field graph work intact. The frozen fixture is a diagnostic control, not a replacement Go module or an edited-build benchmark. Its checks cannot execute. Host CPU pressure reaches 33.4%; all observations remain included.

Four fresh-process component pairs resolve 4,398 newly generated native rows with nested keys. Existing direct scalar getters and scalar-list projection are on in both arms. Median query projection improves **318.76 → 39.05 ms**, faster in all four pairs, with allocation **283.48 → 23.00 MB**. The component measures the query executor's response projection, not network transfer, final JSON encoding or the complete CLI. It does not establish the whole-command gain by itself.

## Correctness and profiles

The complete DagQL race suite passes with projection disabled and enabled. Focused tests cover nested output, empty arrays, nullable fields, aliases, Unicode, IDs, computed fields, custom scalar ownership, replacing a generated getter, cancellation, unbound sessions, requirements growing during a copy and release at operation exit. Core tests check that metadata owns its copied keys and preserves absolute-address errors. Engine and CLI builds pass.

End-to-end checks compare exact table, link and CLI output. A separate module reaches two nested collections through stored object fields, with Unicode, spaces and slashes in keys. Both paths return the same four rows. The file-backed workspace has no Git address; both paths preserve that expected absolute-link error. The initial harness incorrectly expected this case to succeed, and the failed attempt is retained separately.

Two subsequent wcprof captures return correct rows with zero dropped events and no open operations. The frozen capture records 116,155 events, no nested SDK requests and 801 function evaluations. Its metadata API finishes at about 9.91 seconds of a 10.04-second main query; projection itself occupies about **65 ms**. No `ArtifactMetadata.uri`, `ArtifactMetadata.dimensionKeys` or `ArtifactDimensionKey.key` calls execute. The slow part of this diagnostic is earlier cache publication and module preparation, rather than row output. Its elapsed time is not a matched performance observation.

The real capture takes 26.46 seconds, with a 24.73-second main query and 710,065 lossless events. It still makes **7,820 nested SDK requests** and 963 function evaluations. `Go.packages` takes 13.57 seconds and the longest package test-collection call 10.00 seconds; these intervals are not additive. The critical path includes 5.15 seconds in configuration stat intervals, 2.69 in reads, 4.17 waiting for the session lifecycle lock and 2.26 in host-directory imports. Those waits are not filesystem CPU or automatically removable savings.

That remaining discovery path is the next substantial target. Bulk metadata removes a category of work; reaching three seconds still requires reducing repeated discovery requests and their setup while keeping fresh configuration and tracked native inputs.

## Current boundary

Engine `1a514c53…` preserves the prior native telemetry v2 format and dual readers. It replaces `4b03eb19…` through a graceful exit on the same volume. Shutdown takes 255.17 seconds while saving the existing cache database; no force, reset or cache deletion occurs. A short shutdown CPU profile is retained for later investigation, with no new persistence performance claim.

All six Rust histories reuse every action before replacement, after restart, with the generic projection enabled and again after the listing comparisons: **130/130, 1,026/1,026 and 6/6**, twice each. These establish retained-cache correctness, not a Rust timing gain.

The source is `ff0b029a…`, selected Go module `7568cd0…`, and new CLI `97f7d82d…`. The implementation extends existing experimental scalar/data projection support and has not been ported into a standalone branch on current upstream main. Broader adoption, collection-dimension listing paths and integration with the Rust module remain unfinished. Controls are restored between comparisons. No new PR is open.

[Sources, tests, all controls and full-command evidence](experiments/typed-artifact-metadata/) preserve the complete prototype and its dependency context. The [preceding decomposition](NATIVE_COLLECTION_WORK_AMPLIFICATION.md) explains the choice of this experiment.
