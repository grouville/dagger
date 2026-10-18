# Package-scoped test snapshots: rejected prototype

Giving each package its own native test-source snapshot does not make real edited listing faster. The complete command regresses **18.60 → 55.76 seconds**, slower in all four balanced pairs. The prototype stays unselected. No PR is proposed.

The intended benefit remains useful: a test-file edit should refresh discovery for the affected package while unchanged packages reuse their results. This experiment establishes that filtering the files is insufficient with the current object identities.

## Change

The parent collection imports one immutable snapshot containing test files and module boundaries. Each package getter filters it to that package's test files and all `go.mod` files. Child discovery uses this retained snapshot by default; explicit Directory overrides remain supported. The corrected module-layout key from the preceding prototype is present in both arms. No engine source or binary changes.

The source starts at Go module commit `6b9173a88d8c2c97cee0c9ee59735b0236275f9b`. The exact 17-line diff and both source versions are archived. The prototype remains an uncommitted experimental worktree at `/tmp/dagger-go-package-test-snapshots`; production branches are unchanged.

## Complete-command results

Command: `dagger check --module go --check test --list --all`, on the real dagger/dagger checkout at `ff0b029a4d270a651b9a8c7286babc79089066e4`.

| Pair | Parent prototype | Package snapshots |
| --- | ---: | ---: |
| 1 | 18.51 s | 55.08 s |
| 2 | 18.69 s | 56.17 s |
| 3 | 18.44 s | 55.35 s |
| 4 | 21.96 s | 75.95 s |
| Median | **18.60 s** | **55.76 s** |

Median engine CPU rises **95.10 → 326.36 CPU-seconds** and cumulative allocation **15.78 → 54.09 GB**. Median paired latency regresses by **37.19 seconds**. Every attempt is retained, including the slower fourth candidate.

This is a warm-engine comparison with a fresh CLI, ordinary Go source edit and real test-file edit on every invocation. Each arm includes successful exit, cleanup and final log flush. Telemetry and normal garbage collection remain enabled. No cache reset, engine restart, compilation or test execution occurs. Both arms use the same engine, CLI, typed artifact metadata and generic response projection as the [preceding native-input experiment](NATIVE_GO_NATIVE_TEST_DISCOVERY.md).

Two initialization commands add a real test and return 4,399 rows; all eight measured commands remove it and return the same ordered 4,398 rows and full row text. Initializations are excluded from medians. All ten commands exit successfully. Three focused checks pass: discovery, package-layout rebinding and test collections, including their explicit source overrides. The full remaining suite is not rerun for this rejected prototype.

Host CPU pressure peaks at 23.0%, I/O pressure at 11.3%, and memory pressure at 0.47%. These observations limit absolute-time comparisons with older cohorts; the slower candidate also increases CPU and allocation in every pair. Source files, workspace configuration and debug flags are restored.

## What the profile proves

A separate diagnostic completes in 103.35 seconds with all 4,398 rows. Its 1,162,220 wcprof events have no drops or open operations. Profiling time is not a performance comparison.

| Work after a test-file edit | Count |
| --- | ---: |
| Package getter executions | 800 |
| Child test-discovery executions | 800 |
| Module-layout key executions | 801 |
| Dang function evaluations | 2,563 |
| Nested SDK requests | 8,047 |

The changing parent invalidates the package getters, and package-scoped sources do not make child discovery hit the cache. Layout checks now execute against hundreds of different source receivers instead of sharing the one global snapshot. This introduces repeated directory walks and snapshot preparation.

The main query's critical path is 102.44 seconds: `Directory.glob` accounts for 39.16 seconds, session-lifecycle lock waits 19.66 seconds, and `String.glob` 6.23 seconds. Snapshot creation, commit and publication also appear on the path. These are on-path portions of this diagnostic, not independent speedup estimates. Merely fixing lock contention would leave substantial work.

## Next experiment

Test whether unchanged package results can retain a content identity after the parent collection changes. The engine currently assigns module-object return content digests automatically for functions accepting Workspace; the package getter does not accept one. That is a lead, not a proven fix. A generic change must preserve module provenance, schema views, secret/socket compatibility and resource ownership. Establish it with a small regression test before a full-repository experiment.

Stable child identities alone will not remove all 800 getter executions or snapshot operations. Also examine an engine operation that partitions one immutable source into package views without rebuilding each snapshot separately. Both changes must earn their complexity through complete-command measurements.

The target is still three seconds for real edited listing. The [frozen-name diagnostic](NATIVE_GO_COLLECTION_INPUTS.md) reaches 1.07 seconds using ordinary collections, but it performs no real source discovery and is not a claimed real-module result. Prior gains and this regression come from separate cohorts and are not additive.

[Evidence, source and reproduction drivers](experiments/go-package-test-snapshots/) include every command, restoration record, focused check, lossless wcprof chunks and the exact patch. Engine and CLI source identities are inherited from the preceding archive; no new binaries are needed.
