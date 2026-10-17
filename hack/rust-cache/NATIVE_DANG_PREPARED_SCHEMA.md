Reusing schema data with cached Dang declarations removes repeated engine work but does not establish a useful speedup for full Go test collection listing. The candidate remains disabled and unselected. No PR is proposed.

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
