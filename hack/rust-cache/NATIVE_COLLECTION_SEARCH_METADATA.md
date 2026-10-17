# Native search metadata: fewer entries, no reliable command gain

The latest selected complete Go listing takes **35.91 seconds median**. Extending data-only projection to native search results measures **35.52 seconds**, faster in only two of four pairs. The difference is insufficient to select the candidate; it remains disabled. This establishes no improvement over the earlier selected implementation.

`dagger check --module go --check test --list --all` uses source `ff0b029a`, module `7568cd0`, CLI `e7ba08d0` and controlled engine `c0740207`. Both arms retain all selected optimizations, including data-only collection-key projection. The rejected upstream scalar-list switch stays disabled. Each command starts a fresh CLI and receives a fresh source comment on the same warm engine and volume. Timing includes successful cleanup, with telemetry and ordinary GC enabled and profiling off. The local telemetry receiver does not model production Cloud latency. Cold startup is unmeasured.

| Pair | Selected path | Search metadata projection |
| --- | ---: | ---: |
| 1, candidate first | 37.03 s | 34.20 s |
| 2, control first | 37.04 s | 34.34 s |
| 3, candidate first | 34.79 s | 36.71 s |
| 4, control first | 34.78 s | 38.30 s |

All ten commands return the expected ordered rows and exit successfully. The excluded initialization pair adds a real test and finds 4,399 rows; measured pairs remove it and find 4,398. Median paired saving is **0.39 seconds**. No measured pair undergoes class-slot compaction. Host pressure reaches 26.4% CPU and 5.0% I/O; quiet admission does not guarantee quiet conditions throughout a command.

Column-median allocation falls **29.35 → 28.78 GB**, but the candidate allocates less in only two pairs. CPU medians are **183.10 → 181.42 CPU-seconds**, lower in three pairs. These concurrent totals do not establish elapsed-time savings. Class-slot growth consistently falls **24,018 → 20,909**, exactly 3,109 fewer entries.

## What the real trace changes

The native type contains strings, integers and plain submatch data. Its persisted family already declares no references. Search parsing, host conversion and decoding construct values before publishing them; workspace merging sorts a new slice without modifying its elements. Two production lines opt the type into the existing experimental `ClassOpts.PureData` policy. The private A/B gate changes only that type's eligibility. Module code and collection behavior are unchanged.

The initial profiling assertion incorrectly expected all 7,507 search-item publications to disappear. The full command subsequently loads objects in separate queries. The corrected trace shows **7,507 → 4,398 publications** and **11,885 → 4,398 indexed calls**, with every search scalar getter preserved. All 4,398 remaining calls are roots under `session.query`, linked to `go:GoPackage.tests`. The earlier capture has 4,378 cache hits and 7,507 executions; the candidate has 4,398 executions and no hits. The later calls therefore do not reuse attached items in this capture. These counts alone do not establish how much command time this costs; the purpose of those loads needs investigation before bypassing them.

The preflight returns all rows and exits successfully in **37.71 seconds with profiling enabled**, recording **371,747 events, none dropped or open**. This single diagnostic is not a timing result. Its main query takes 35.15 seconds; **24.22 seconds** of the reconstructed critical path lies inside module API requests, including backend work. That does not measure transport overhead. The earlier key projection remains active: its 17,592 item publications stay absent and both key scalar getters still execute 17,592 times.

## Component behavior and correctness

The benchmark uses the actual native type and schema registration, two stored strings and a constant-size generation argument. Forty-eight successful fresh-process runs cover 1, 8 and 128 results, fresh and repeated parents, in four alternating pairs per case. With ordinary GC, fresh-result medians are **0.129 → 0.088 ms**, **0.440 → 0.257 ms** and **4.83 → 1.48 ms**, faster in every pair. Repeated-parent latency improves in four, four and three pairs respectively, but allocates more at every size: **22.86 → 24.95 kB**, **108.90 → 125.51 kB** and **1.58 → 1.85 MB**. Component gains do not establish complete-command benefit.

The native regression verifies scalar output, absence of item entries during metadata reads, loadable IDs after a newer result set and nested submatches. Removing only the schema policy fails the entry-count assertion: four entries instead of the retained parent entry. The corrected candidate, scoped search/overlay race checks and full DagQL race suite pass. The first fixture used unsupported assignment into a typed result-of-array; its failed source and log remain preserved separately.

All six native Rust histories reuse **130/130, 1,026/1,026 and 6/6** compilation actions, twice each, before replacement, on their first candidate-enabled calls afterward and after the cohort. The old engine exits gracefully in **170.10 seconds** and the same volume is restored without a reset or forced termination. Shutdown is separate from command cleanup. The primary Rust timing manifest is unchanged.

The [evidence](experiments/native-search-data-projection/) retains exact source, failed assumptions, all attempts, outputs, profiles, cache checks and final disabled state. The isolated source overlay is prepared but unvalidated and is not a ready proposal. No PR is opened; the count remains sixteen Dagger descriptions and one Go-module description.

The selected SDK also has a concrete distinction to investigate: lazy GraphQL-list selection uses one query, while a materialized list of object handles is selected element by element. The actual Go receiver/type boundary still needs verification. That path is recorded in `FOLLOW_UP.md`; no SDK fix or speedup is claimed here.
