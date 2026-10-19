# Reuse schema preparation while executing normal module logic

Retesting this existing prototype on the current getter-based stack improves complete Go test listing after a test-file edit **11.92 → 10.86 seconds median**, faster in all four balanced pairs. Ordinary-source edits are effectively flat at **6.43 → 6.45 seconds**. The median paired test-edit saving is **1.14 seconds**. This is a useful candidate on the development stack, with the flag restored to disabled after validation. Cold performance and a Rust latency gain remain unmeasured; three seconds is still unachieved.

| Complete-command workload | Prepare schema each time | Reuse retained schema |
| --- | ---: | ---: |
| Test-file edit | 11.92 s | 10.86 s |
| Ordinary-source edit | 6.43 s | 6.45 s |
| Test-file edit, engine CPU | 62.39 CPU-s | 56.63 CPU-s |
| Test-file edit, cumulative allocation | 15.33 GB | 13.63 GB |

Both versions use the same Go module, engine binary and CLI. Every command starts a fresh CLI and makes a real source edit on a warm engine. Each version completes test addition and removal before four measured pairs per workload. All 24 timing commands have correct ordered names, identical full rows and successful cleanup. Telemetry, ordinary GC and final log flushing are included, with no concurrent profiler, build or tests. The earlier 47-second comparison below belongs to a different stack and must not be combined with this gain.

## Why the full workflow is preserved

This shares the immutable schema already retained by eligible compiled module declarations. The existing key includes module source, schema file and source mount path. A cache hit avoids opening and decoding that same schema again. Each invocation still receives its current client, receiver, arguments and cancellation context; object initialization, getter bodies and return conversion use their existing paths. Modules requiring per-invocation top-level initialization retain the fallback path. No function result is substituted, and no cache input, test selection, telemetry flush or resource cleanup is removed.

A new sampled allocation capture attributes about **1.68 GB** to schema reading and decoding in a full edited listing, motivating this retest. Its exclusive categories assign each sampled allocation to one stack category; cumulative frame totals are not added together. Natural GC remains enabled and allocation-profile reporting can lag. This diagnostic command is separate from latency measurements.

Separate lossless wcprof captures confirm **804 → 2** schema opens, decodes and self-type preparations. Both versions still execute **804 module evaluations**, **1,494 SDK requests** and all **800 authored package getters**. One test discovery executes and 799 hit in each. The optimization removes repeated preparation while preserving normal getter execution.

Six actual Go checks pass with the candidate enabled, covering source snapshots, discovery, ownership rebinding, collection execution, binaries and generation. Eighteen public-API probe cases edit the module's own source: nested initializers change their results, fresh arguments remain independent, argument and return types change, errors report the current version, and restored source behaves correctly. These complement the existing exact-build SDK race coverage of concurrency, current clients, source/schema changes, initialization fallback and retries.

The Rust module and its native cache are exercised in both modes through 28 cases: fresh test names after edits, restored source, passing and failing selections, exclusion of an invalid neighboring crate, reporting that crate when selected, repair and the public workspace test API. Public `nativeTest` queries recover **2/2 native compilation actions** in both modes. These are correctness checks, not a new Rust performance comparison or transferred-cache test.

The initial Rust fixture omitted the Git boundary used by the established fixtures. Its `Workspace.directory("/")` began importing `/tmp`; cancellation output reports 12 GB, and a diagnostic snapshot shows 99,891 goroutines. Only that CLI was cancelled; engines and cache volumes were retained. Correcting the fixture removes the broad import. Two further inspection-query attempts used a private helper and an obsolete ID type; the final checks use the public API, an explicit source directory and this engine's universal `ID` input. All attempts are retained and excluded from performance claims.

The engine remains `3d1c4deeef3ca394ac64302263ff1d9a30b4b6e18c740ecb5b9d55ef64a784b1` on the isolated `dagger-collection-receiver-decode-oct18` engine. Go module commit is `a3d0e4bf562b834c31135bff24e5931fd32b3acc`; CLI is `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`. Shared receiver decoding stays disabled. This extends the private declaration-reuse prototype and is not a standalone upstream fix. No new PR is opened. [Current sources, every attempt and complete evidence](experiments/dang-prepared-schema-current-getters/).

## Earlier comparison on the older stack

The earlier comparison removed repeated preparation without a useful full-listing speedup. Its measurements and limits follow.

The previous profile records 961 declaration-cache hits and two misses during a listing. Before each lookup, the SDK still opens the immutable schema file, reads its contents and prepares the decoded schema. The cached imports already retain that schema. The candidate returns it alongside the prepared declarations and loads it only when preparing declarations. This extends the existing private declaration-reuse experiment; it is not a standalone fix against upstream.

The key remains the encoded module source ID, schema file ID and source mount path. The bounded cache, eligibility gate and locking are unchanged. Every call receives its current client, parent, arguments and cancellation context. Modules with per-invocation initialization continue through the existing preparation path. No function result, workspace content or compiled test result is added to this cache.

The SDK package passes its full race suite. Focused tests cover concurrent callers with independent clients and arguments, schema/source changes, retry after schema-load failure, and per-invocation initialization. After graceful engine replacement on the same volume, all six native Rust histories report their expected action hits on their first invocation: 130/130 twice, 1,026/1,026 twice and 6/6 twice. No preparation call runs before these post-restart assertions.

The command is `dagger check --module go --check test --list --all` on the dagger/dagger snapshot `ff0b029a4d270a651b9a8c7286babc79089066e4`. Both arms use the same engine binary, CLI and selected Go module. Only the prepared-schema flag differs. Declaration reuse and linear restored-posting deletion are common to both. Telemetry and ordinary GC stay enabled; profiling is off. Each invocation starts a fresh CLI and receives a fresh source edit on the warm engine. An excluded initialization pair adds a real test; measured pairs remove it.

| Measured pair | Prepare schema per invocation | Reuse prepared schema |
| --- | ---: | ---: |
| 1, candidate first | 42.49 s | 47.12 s |
| 2, control first | 54.11 s | 48.24 s |
| 3, candidate first | 49.17 s | 46.21 s |
| 4, control first | 44.38 s | 43.05 s |
| Median | 46.78 s | 46.66 s |

All ten commands return the correct ordered rows and exit 0, including cleanup. Each measured command lists 4,398 rows. The candidate wins three of four pairs, but median complete-command time is effectively unchanged. Median engine CPU falls from 235.51 to 225.25 seconds and allocated bytes from 36.77 to 35.31 GB. Those reductions are real observations, not evidence of a useful latency improvement.

A separate wcprof capture confirms that schema opens, decoding and self-type preparation each drop from 963 executions to two. Both captures execute 963 SDK invocations and 7,820 recorded API requests. The candidate records 961 declaration-cache hits and two misses, returns the correct rows and exits 0. Its 567,569 events contain no dropped or open operations. This verifies the intended work reduction; concurrent phase durations must not be added or interpreted as wall-time savings.

The candidate profile's main query takes 53.15 seconds, of which 28.36 seconds are attributed to synchronous SDK API waits, 10.14 to result publication, 7.48 to artifact element materialization and 4.03 to dimension-key element materialization. Indexed element labels inherit their list resolver's name. This diagnostic command takes 55.19 seconds overall and is separate from the unprofiled timing cohort. Publication includes unusually long intervals that need their own explanation before choosing the next fix. No cache checks, client ownership, collection granularity, telemetry or cleanup are bypassed.

Several publication operations remain pending for about 6.65 seconds and finish within milliseconds of each other. Their overlapping snapshot-maintenance event lasts 132.52 ms, including 80.30 ms of metadata work; it cannot account for the full interval. This suggests a shared wait, but does not identify a lock owner or prove the cause. The bounded maintenance history is retained. A time-window Docker log query was interrupted after a prolonged read; the engine was untouched, and no conclusion relies on that incomplete log query.

An exploratory join by nested-client identity and interval containment finds one candidate backend query for 6,697 API intervals and multiple candidates for 1,123. The ambiguous matches are retained and excluded from detailed attribution. These are temporal correlations, not request identifiers; their overlapping sums are neither transport overhead nor available wall-time savings. The next diagnostic needs direct request correlation and publication wait attribution before another optimization is chosen.

[Sources, test output, complete attempts and profiles](experiments/dang-prepared-schema/).
