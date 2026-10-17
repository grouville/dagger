# Avoid publishing stored scalar fields

Complete Go test listing on `dagger/dagger` improves **40.49 → 39.20 seconds median**, faster in all four alternating pairs. Every command returns the same ordered 4,398 rows and exits successfully through cleanup. This is a modest engine improvement; listing remains too slow.

The collection UX is the requirement. The implementation can change more substantially where measurements justify it. The CLI already requests the full list in one GraphQL query; much of the remaining work is inside the engine and module runtime.

The selected-engine capture contains 7,487 search-result path reads and 10,965 matched-text reads. Of these, 3,109 and 6,587 respectively execute their scalar getter rather than reusing its result. They return data already held in the parent search result. The same trace spends roughly 21 seconds discovering packages, 13 seconds discovering tests and another 9 seconds projecting collection metadata. These are intervals from one diagnostic capture, not controlled performance comparisons or additive CPU costs.

## Prototype

Only generated native struct accessors and module-object data fields currently set the engine's `Trivial` marker. The refined prototype routes these accessors through the existing uncached result path when their declared value is a concrete builtin String, Int, Float or Boolean, including builtin nullable wrappers. It excludes indexed selections, arrays, objects, enums and custom implementations. Normal functions keep their cache policy. Object identities and their parent ownership retain the existing attachment path, and telemetry remains enabled.

This generalizes the existing direct-field policy used by artifact and type-definition strings. It adds no new API, dependency, cache format, lock or mutable cache volume. The selected Go diagnostic uses the refined policy; the broader Rust performance target remains incomplete.

## Complete command

The command is `dagger check --module go --check test --list --all` on source `ff0b029a` with Go module `7568cd0`. Each arm starts a fresh CLI and receives a fresh source comment on the same warm retained engine. Only the scalar-getter switch differs. Telemetry and ordinary garbage collection remain enabled. The initialization pair adds a real test, correctly returns 4,399 rows and is excluded from medians; measured pairs remove it. There is no cache reset or forced collection.

| Pair | Current policy | Direct scalar getters |
| --- | ---: | ---: |
| 1, candidate first | 40.50 s | 39.32 s |
| 2, control first | 40.47 s | 39.08 s |
| 3, candidate first | 42.13 s | 40.23 s |
| 4, control first | 38.44 s | 37.59 s |

Median paired saving is **1.29 s** and allocation falls by **800 MB per pair**, lower in all four pairs. Separate column medians are **32.65 → 31.78 GB** allocated and **203.32 → 207.11 CPU-seconds**. CPU differences are mixed: two pairs increase and two decrease, with **0.77 CPU-second more** at the median paired difference. This establishes a latency improvement, not a CPU improvement.

All admitted attempts are retained. Measured host CPU pressure reaches 26.4% and I/O 5.6%; engine I/O remains below 0.8%. Admission waits for quieter conditions but cannot guarantee they persist throughout a command. Native cache checks run outside timing and do not support unchanged-build performance claims.

## Work removed and remaining path

A completed diagnostic returns the correct rows in 39.98 seconds with **509,170 wcprof events, zero dropped and none open**. Against the preceding selected-engine capture, search-result path reads remain 7,487 and text reads 10,965. Their respective **3,109 and 6,587 publications disappear**. Artifact and dimension-key element reads remain **4,398 and 17,592**: addressable object attachment is preserved. Total publications in those two captures are 48,724 and 38,512; the other differences are not a controlled timing attribution.

The new main-query path is 37.98 seconds: **27.41 s** lies inside synchronous module API requests. Package discovery takes 15.92 seconds, test expansion another roughly 12 seconds, and artifact metadata another roughly 9 seconds. Indexed artifact/key element calls account for about 6.8 seconds of the path. Those synthetic labels do not mean their list resolver executes repeatedly. The next larger investigation should address this repeated engine work and module API processing, with bulk operations or a different value representation where ownership and IDs remain correct.

The CPU sample contains 202.37 CPU-seconds over 40.04 seconds, including concurrent work. Garbage collection accounts for 48.40 cumulative CPU-seconds; Protobuf JSON marshaling for 21.12 and unmarshaling for 16.32. Nested frames overlap, so these numbers cannot be added or treated as wall-clock savings. The earlier native-sort, schema and callback experiments remain separate; this capture does not validate them.

## Component screen

Four alternating pairs use fresh benchmark processes, Go 1.26.6, `GOMAXPROCS=8` and ordinary GC. The native DagQL fixture reads five scalar fields, including a nullable field. Fresh-parent queries include constructing and attaching the parent list and its elements. Repeated-parent queries first populate that same result.

| Projection | Original | Direct scalar getters | Allocation before → after |
| --- | ---: | ---: | ---: |
| One new object | 291 µs | 194 µs | 76.7 → 52.5 kB |
| One previously read object | 146 µs | 118 µs | 27.2 → 35.0 kB |
| 1,026 new objects | 137.98 ms | 33.60 ms | 59.82 → 32.46 MB |
| 1,026 previously read objects | 28.15 ms | 16.18 ms | 14.02 → 22.01 MB |

Repeated reads are faster but allocate more: the uncached path constructs result wrappers again. That tradeoff remains relevant even though the complete edited listing allocates less in every pair.

The table measures the refined concrete-type policy, faster in all four pairs for every case. Initial name-based observations remain separate. The first harness used an unanchored benchmark path segment: `1` also selected `1026`. That mislabeled raw cohort supports no claim. The reported cohort anchors every path segment and asserts exactly one benchmark result per process. All admitted attempts are retained. Host I/O pressure reaches 24.6% in one single-object fresh-parent process; the large fresh-parent cases peak at 1.2% I/O and 10.6% CPU pressure. Quieter admission does not guarantee low pressure throughout a process.

The initial prototype passes the complete DagQL race suite and 32 focused module-object/stored-result checks. An additional adversarial test nevertheless catches a bug: a reflected custom integer with a release callback is a supported cached result, but the name-based policy rejects it. The unchanged implementation passes this test and the prototype fails. That engine binary is never installed.

The refined policy matches concrete builtin values and their builtin nullable wrappers, preserving custom implementations even when they advertise a builtin GraphQL name. The failing case remains as a regression. The refined version passes the full DagQL race suite in 66.50 seconds and the 32 focused module-object/stored-result checks. All six retained native histories reuse every action before the restart, on their first candidate-enabled calls afterward, after the cohort and after profiling: **130/130, 1,026/1,026 and 6/6**, twice each.

The first installation attempt exposed a diagnostic wiring error: the handler was registered on the default HTTP mux while the engine serves a private mux. The candidate remained disabled and no listing timing started. The corrected handler is wired into the actual mux. Both restarts exit gracefully on the same volume, with no forced termination or reset; the first setup's source and logs remain in the archive.

The standalone branch is based on upstream `ff0b029a`. Its production logic is identical to the measured candidate, with an updated field comment; its concurrency assertions run on the test goroutine. [Review description](PR_ENGINE_TRIVIAL_SCALARS.md). No PR is open. [Evidence](experiments/trivial-scalar-projection/) retains every prototype, harness failure, component, full command and profile. Cache-compaction experiments are recorded separately in [the ownership note](NATIVE_CACHE_COMPACTION_OWNERSHIP.md) and remain unselected.
