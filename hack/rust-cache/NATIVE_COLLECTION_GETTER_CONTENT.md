# Preserve unchanged collection children

The real Go collection listing improves **18.10 → 16.24 seconds** after test-file edits, faster in all four balanced pairs. Wcprof verifies the intended change: **800 test-discovery executions become one execution and 799 cache hits**. Three seconds remains unachieved.

This is a scoped engine prototype plus a Go-module variant using existing native directory APIs. The Go variant is pushed as `846aebb814d3356cdf7658ea97aeaecb4e99d818` on `grouville/go:experiment/subtree-test-discovery`. It remains disabled by default. No PR is opened, and the main retained-cache engine is unchanged.

## Change and correctness

The engine already computes return-content identity for module functions accepting Workspace. The prototype extends this to collection getters, so unchanged returned objects can be reused after their parent collection changes. The added identity includes the module implementation, return type and effective schema view. It retains existing cache publication and resource ownership paths.

The Go variant retains one native test-source snapshot in its package collection. Each getter selects the package subdirectory and filters its own test files through `Directory.directory` and `Directory.filter`, which preserve content identity. This replaces the rejected prototype's repeated `withDirectory` copies. Default test discovery uses the owner already established by root discovery; explicit Directory overrides still validate module ownership. It no longer recomputes the module-layout key against 800 package snapshots.

The default discovery source is now the immutable snapshot retained by the package. Explicit source overrides remain supported. This differs from the previous contextual source parameter, so direct API compatibility and broader SDK validation remain adoption work. The CLI still lists and selects ordinary nested collections; no rows are frozen, flattened manually or omitted.

Two focused engine tests exercise the actual module-call/cache path. Without the patch, changed parents execute downstream work again for identical child data. With the patch, identical children reuse that work and changed children miss and return the new value. The scope test separates module implementations, return types and view-specific fields while preserving reuse for global fields across unrelated views. An unsafe control that omits scope fails this test.

**42 focused core tests pass with the race detector**, covering collections, object ownership, persistence, retention, private handles and secret/socket resource fallback. The diagnostic wrapper also passes both new tests under the race detector when enabled; disabling it reproduces the original miss. These focused checks do not establish every new getter/resource combination or compatibility across all SDKs.

Three Go checks pass on the original engine with the module variant, then again on the isolated engine with the new getter behavior enabled: discovery, package-layout rebinding and test collections. They include overlays, changed module boundaries and checking generated test binaries. The remaining full Go-module suite is not rerun in this experiment.

## Complete-command comparison

Command: `dagger check --module go --check test --list --all`, on real dagger/dagger source at `ff0b029a4d270a651b9a8c7286babc79089066e4`.

| Pair | Getter content identity OFF | ON |
| --- | ---: | ---: |
| 1 | 17.72 s | 15.99 s |
| 2 | 17.78 s | 16.23 s |
| 3 | 18.43 s | 16.25 s |
| 4 | 20.15 s | 16.59 s |
| Median | **18.10 s** | **16.24 s** |

Median paired saving is **1.95 seconds**. Median engine CPU falls **103.64 → 90.77 CPU-seconds** and cumulative allocation **22.13 → 18.68 GB**. Every pair improves latency, CPU and allocation.

Both arms use exactly the same module source and engine binary. Every invocation starts a fresh CLI, edits an ordinary source file and a real test file, and includes successful command exit, session cleanup and final log flush. The engine is warm; telemetry and normal garbage collection remain enabled. No caches are reset and no workloads run in parallel. Two initialization commands add a real test and return 4,399 rows; all eight measured commands remove it and return identical ordered 4,398 rows and full row text. Initializations are excluded; the first measured removal is retained.

Host CPU pressure peaks at 21.6%; I/O pressure stays below 0.16% and memory pressure is negligible. All attempts and pressure records are archived.

## Limits and rejected follow-up

A separate ordinary-source-edit cohort shows no additional benefit: **9.62 → 10.49 seconds**, only one of four pairs faster. The first candidate removal costs 16.82 seconds, followed by 9.54, 11.05 and 9.94 seconds. All attempts are retained. Median paired latency regresses 0.77 seconds; median CPU and allocation remain nearly unchanged. This optimization is not a demonstrated win for that workload.

The new getter-heavy profile also justifies retesting the existing known-input-ID shortcut. With getter content identity enabled in both arms, it measures **17.21 → 17.09 seconds**; three pairs improve but CPU and allocation remain essentially unchanged. This does not establish a useful gain. The shortcut remains disabled, and broader interface/namespacing validation is not added for it here.

Across these three cohorts, all 30 commands return correct rows and exit successfully. Their gains are separate comparisons and must not be added to older results or to each other.

## Why it still takes 16 seconds

Separate lossless wcprof captures return the same 4,398 rows and exit successfully, with no dropped events or open operations:

| Work | OFF | ON |
| --- | ---: | ---: |
| Test-discovery executions | 800 | **1** |
| Test-discovery cache hits | 0 | **799** |
| Package-getter executions | 800 | 800 |
| Module-layout key executions | 1 | 1 |
| Dang evaluations | 1,763 | 964 |
| Nested SDK requests | 4,847 | 3,803 |
| Recorded events | 405,619 | 302,666 |

The optimized main query takes 16.84 seconds in its diagnostic: root package discovery occupies about **8.49 seconds**, then getter preparation about **7.4 seconds**, with the one changed discovery about 0.38 seconds near the end. These are critical-path observations, not standalone speedup promises.

Root discovery's path includes **2.28 seconds in config stat, 0.87 seconds in config reads, 1.76 seconds in Dang evaluation and 0.68 seconds in session-lock waits**. The longest getter's path includes **3.05 seconds in result encoding, 2.25 seconds in Directory.exists and 1.28 seconds waiting on the session lock**. Serialization can await lazy GraphQL/directory work: its wall time is not proof of JSON-encoding CPU cost. The earlier ID shortcut screen does not solve it.

The next experiment should reduce repeated getter setup through a generic collection path that preserves per-item selection, keys, subsets and deltas. Prove a complete-command benefit with real source discovery before adding a public declaration or SDK contract. Independently inspect which root-discovery config checks are necessary for already captured immutable dependencies. Preserve live host-config freshness; the earlier global sharing attempt was rejected for staleness. No TTL or manual invalidation is proposed.

## Engine and evidence

The isolated engine is `dagger-collection-content-oct18`, container `c852f474863db6e93f76740af2d3a00e22e3204c5a881faacb0c8584059283d2`, with its own same-named volume. Runner: `tcp://127.0.0.1:16277`; debug: `http://127.0.0.1:16105/debug/`. Binary SHA-256: `bcb54624de35daa61dbf801a9bfd303ea986c838d95932374f808c49caa131a7`. It inherits the preceding engine and dual telemetry readers; inherited source hashes are verified unchanged. The CLI remains `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`.

The original engine binary is unchanged; its volume was neither replaced nor reset. The isolated engine is left idle for follow-up; getter content identity, known-input IDs and wcprof are disabled. Source files, configuration and all experiment flags are restored after every cohort and capture.

[Evidence and reproduction drivers](experiments/collection-getter-content/) include the exact engine/module patches, failing controls, race results, every timing attempt, two lossless captures, detailed critical paths and source/binary identities. This is a development stack comparison; it is not a stock-main benchmark or a standalone upstream patch yet.
