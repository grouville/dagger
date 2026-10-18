# Give test discovery native snapshot inputs

Complete Go test listing on real `dagger/dagger` improves **19.70 → 9.30 seconds median** when an ordinary Go source file changes. All four measured pairs improve, return identical ordered 4,398 rows and finish cleanup. The prototype gives child discovery a native Directory input and fixes an overly broad ownership fingerprint. **Edits inside test files remain mixed**, and the direct API argument type changes. This remains an experimental fork branch; three seconds is unachieved.

## Complete ordinary-source edits

Both arms use the same development engine, CLI, retained volume and repository. Every invocation starts a fresh CLI and edits `dagql/types.go`. The candidate's test-file snapshot therefore stays unchanged during the measured pairs. Typed artifact metadata and generic data projection are common to both arms. Telemetry, ordinary GC, cleanup and final log flushing remain included; profiling is off.

```sh
dagger check --module go --check test --list --all
```

| Pair | Previous module | Native input and corrected guard |
| --- | ---: | ---: |
| 1, candidate first | 20.54 s | 15.25 s |
| 2, control first | 18.84 s | 9.50 s |
| 3, candidate first | 21.12 s | 9.10 s |
| 4, control first | 18.86 s | 8.87 s |
| Median | **19.70 s** | **9.30 s** |

Median paired saving is **9.66 seconds**. CPU and allocation fall in every pair, with column medians **99.22 → 41.30 CPU-seconds** and **17.26 → 7.70 GB**. Allocation is cumulative, not peak memory. Maximum host CPU pressure is 20.9% and I/O pressure 0.15%.

An excluded initialization pair adds a real test and both arms observe 4,399 rows in **21.64 → 17.86 seconds**. Measured pairs remove it and return exactly 4,398 rows. The first measured candidate's new input still needs population; it remains included. All ten commands succeed. No observations are discarded, and source and configuration are restored.

The engine is warm; cold engine startup is unmeasured. These are controlled development-stack comparisons, not stock main. Gains from older cohorts are not additive.

## Test-file edits remain unresolved

A separate matched comparison edits `dagql/cache_test.go` in every arm, changing the native snapshot each time. It also retains the ordinary source comment edit. This prevents the unchanged snapshot from concealing miss costs.

| Pair | Previous module | Native input and corrected guard |
| --- | ---: | ---: |
| 1, candidate first | 36.78 s | 15.08 s |
| 2, control first | 19.38 s | 22.54 s |
| 3, candidate first | 18.51 s | 17.83 s |
| 4, control first | 22.62 s | 28.59 s |
| Median | **21.00 s** | **20.18 s** |

Only two pairs improve; the median paired difference is a **1.24-second regression**. There is no established test-edit latency win. CPU falls in three pairs, with medians **104.06 → 98.84 CPU-seconds**; allocation falls in three, **17.14 → 16.03 GB**. Host I/O pressure reaches 7.3%, and all runs remain included. Every command returns correct identical rows and exits successfully, including the test-addition initialization pair.

The source argument currently includes test files across the repository. A change to one test file therefore invalidates all 800 child collection calls. The next data flow needs package-scoped snapshots. Discovery itself still contributes substantial preparation, so fixing this invalidation alone does not establish a three-second command.

## What changes

`GoPackage.tests` accepts a native Directory, with existing `@defaultPath("/")` and `@ignorePatterns` support importing `go.mod` and `*_test.go` files. It uses the existing matcher, file ordering and module-boundary guard. Direct callers now pass a workspace snapshot; the collection path and CLI command are unchanged. All data stays in normal Dagger snapshots and result caching. No cache volume, host memo, TTL, new dependency or engine lock is introduced.

This changes the direct argument type from Workspace to Directory. Nine internal call sites are adapted. It preserves explicit discovery against changed snapshots and execution still receives its workspace, but existing external `.tests(ws)` callers would need migration. The prototype is not a drop-in module update.

A separate ownership fix refines our existing prototype. The old `moduleLayoutDigest` hashes a sparse filesystem tree. A host workspace and a re-filtered native test snapshot can have the same module boundaries but different tree fingerprints, causing the retained owner to be rejected. The standalone host/native regression fails before the fix and passes afterward. This does not establish an engine hashing bug; filesystem details beyond module boundaries are outside the guard's actual dependency.

The guard now fingerprints the sorted workspace-root-relative `go.mod` paths. NUL separates paths unambiguously, and the existing native File API hashes the immutable path record with metadata excluded. Ownership depends on these boundaries; Go version and source contents are still read by their existing execution paths. The key detects added, removed and moved modules while ignoring unrelated source, metadata and empty directories. It remains independent of filesystem hash normalization.

## Isolate the guard fix

With native Directory arguments common to both arms, a separate test-file-edit cohort improves **26.86 → 17.59 seconds median**, faster in all four pairs. CPU and allocation fall in every pair: **148.25 → 89.09 CPU-seconds**, **24.66 → 15.83 GB**. All ten commands have correct rows and successful exits. This measures the correction to our native-input prototype, rather than a standalone gain against upstream.

Separate lossless captures show the mechanism:

| Edited test snapshot | Old guard | Corrected guard |
| --- | ---: | ---: |
| Fallback ownership executions | 800 | **0** |
| Dang function evaluations | 1,764 | **964** |
| Nested SDK requests | 8,772 | **4,848** |
| Child test-collection executions | 800 | 800 |

The corrected capture returns the right rows in 18.33 seconds, with 447,084 events, no drops and no unfinished operations. It does not avoid the remaining 800 child executions on a changed global test snapshot.

The initial native-input version also demonstrates actual reuse: its unchanged test snapshot gives **800 child cache hits**, 163 function evaluations and 2,079 SDK requests. That capture takes 11.80 seconds; its main query is 10.99 seconds. The main-query critical path includes 1.52 seconds of configuration-stat intervals, 1.29 of reads, 1.45 in `Query.node` and 0.53 waiting on session admission. These intervals include scheduling and contention and are not guaranteed removable CPU costs. The report is rooted at the main query; an unrelated outer GC operation is not charged to it.

The initial Directory-only cohort is retained too: **17.84 → 16.52 seconds**, two of four pairs faster. Its expensive first snapshot population and unnecessary ownership fallbacks explain why it was refined before the final comparison. No cohort is hidden.

## Validation and review state

All **24 Go-module checks** pass on the final combined source. Six focused standalone guard checks pass, including host/native equivalence, boundary add/remove/move, changed contents and permissions, unrelated directories, cwd changes, existing discovery and retained-package rebinding. The existing collection check covers Unicode, stable order, overlays and actual selected-test execution. The baseline failing regression and two test/setup mistakes are retained separately.

The [Directory-input prototype](https://github.com/grouville/go/commit/6dedab81205a1ed15972e1f5c9005afeb137b136), [independent guard correction](https://github.com/grouville/go/commit/08d8de10f396080cb3ca665ed36690dea6a3f28d) and [combined branch](https://github.com/grouville/go/commit/6b9173a88d8c2c97cee0c9ee59735b0236275f9b) are pushed to the fork. They build on our `0b487434` prototype, not current upstream main. The guard correction belongs with the pending ownership change. No PR is open, and the combined API change remains unselected.

Engine `1a514c53`, CLI `97f7d82d` and repository `ff0b029a` remain unchanged. Temporary controls are restored and no engine restart or Rust cache alteration occurs. [Sources, all forty listing commands, checks, failures, lossless traces and restoration](experiments/native-go-test-discovery/) retain the evidence. The [preceding frozen-data control](NATIVE_GO_COLLECTION_INPUTS.md) motivated this real-source experiment.
