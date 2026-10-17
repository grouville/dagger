# Restored search metadata: no complete-command gain

The latest selected complete Go listing takes **36.34 seconds median**. Reading restored search metadata without attaching its items measures **36.19 seconds**, faster in only two of four pairs. The median paired difference is a **26 ms regression**. The candidate remains disabled; this is not a performance improvement.

The command is `dagger check --module go --check test --list --all` on `dagger/dagger`, source `ff0b029a`, module `7568cd0`, CLI `e7ba08d0` and controlled engine `b9bcd309`. Every command starts a fresh CLI and receives a fresh source comment on the same warm engine and volume. Telemetry and ordinary GC remain enabled; profiling is off during timing. Complete-command time includes successful session cleanup. The local telemetry receiver does not model production Cloud latency. Cold startup remains unmeasured.

| Pair | Selected implementation | Restored metadata projection |
| --- | ---: | ---: |
| 1, candidate first | 36.82 s | 36.79 s |
| 2, control first | 34.49 s | 36.45 s |
| 3, candidate first | 35.85 s | 35.93 s |
| 4, control first | 37.97 s | 33.44 s |

All ten commands, including initialization, return exactly the expected ordered rows and exit successfully. Initialization adds a real test and finds 4,399 rows. Measured pairs remove it and find 4,398. No measured command undergoes class-slot compaction. Host pressure reaches 26.5% CPU and 7.8% I/O; quiet admission does not ensure quiet conditions throughout a command.

Column-median cumulative allocation falls **29.27 → 28.43 GB**, lower in three pairs; this is allocation over the command, not resident memory. Engine CPU falls **184.05 → 177.87 CPU-seconds**, lower in every pair. Class-slot growth falls by about 3,109. These reductions do not establish faster complete listing. The earlier selected data-only dimension-key projection remains enabled in both arms.

## Verify the SDK hypothesis first

The previous search study suggested investigating materialized-list selection in the SDK. The real core and module-facing schemas return object lists for both `File.search` and `Workspace.search`. The direct expression, fold and helper variants each issue one bulk query in a mock using the selected SDK and real schema.

Grouping the existing wcprof events proves that the remaining **4,398 indexed search-result reads occur within 895 queries**, often with many results in one query. They are not 4,398 HTTP requests. An item span appearing directly beneath `session.query` does not prove one request per item: selection can run after the containing resolver span ends. All 1,049 `File.search` calls hit their cached parent result in that capture.

The generic SDK path for materialized object handles exists, but it is not established as this listing's bottleneck. No SDK batching fix is selected or proposed. The initial schema-argument and fixture corrections are retained with the passing reproductions.

## The actual missing projection path

A fresh native search list contains plain `SearchResult` values. After saving and reopening the cache, the list contains detached result wrappers owned by the persisted parent. The original experimental projection handles only plain arrays. Reading the same three stored values therefore keeps one cache entry before reopening but creates four afterward.

The candidate extends the existing data-only projection to a restored list only when each wrapper has no attached ID or session resource and its inline owner is the retained parent. It preserves that owner in the borrowed scalar result. Existing resource, type, field and object-selection guards remain in place. Explicit IDs still attach normally. No persisted encoding, compilation identity or production locking changes.

This is a gap in our experimental projection, not a demonstrated upstream persistence bug. The focused save/reopen test fails without the bridge and passes with it. Scoped native search races and the full DagQL race suite pass. Additional tests load IDs across two more cache reopenings and run concurrent metadata and explicit-ID reads under the race detector.

The real diagnostic returns all rows and exits successfully in **37.67 seconds with profiling enabled**, recording **340,947 events, none dropped or open**. It verifies **7,507 → 0 search-item publications** and **11,885 → 0 indexed search-item calls**, while preserving all 7,487 file-path and 10,965 matched-line getters. The earlier dimension-key projection also remains active, with all 17,592 reads of each scalar field preserved. This confirms the candidate reaches the intended path; the complete-command comparison above still rejects a latency claim.

Discovery remains expensive. In that diagnostic, the main artifact discovery interval is 27.90 seconds; package discovery is 15.08 seconds and the longest package-test expansion 11.29 seconds. These intervals overlap and include engine work and waiting. They do not measure pure parser CPU or host-file reads, and must not be added together as independent costs.

## Retained state

All six native Rust histories reuse every compilation action before replacement, on their first candidate-enabled calls afterward and after the cohort: **130/130, 1,026/1,026 and 6/6**, twice each. The old engine exits gracefully in 172.34 seconds; the same volume is retained without forced termination or reset. Shutdown is separate from measured command cleanup.

Both native-search and restored-list projection switches are disabled after the comparison. The previously selected dimension-key projection remains enabled. No new Rust timing result, standalone-ready proposal or PR is added; the count remains sixteen Dagger descriptions and one Go-module description. The prepared standalone overlay is unvalidated.

[Retained evidence](experiments/restored-data-list-projection/) includes the rejected SDK attribution, the cache-reopen regression and expected failure, exact source overlays, race logs, complete outputs, profiles, all timing attempts, native-cache checks and selected engine state.
