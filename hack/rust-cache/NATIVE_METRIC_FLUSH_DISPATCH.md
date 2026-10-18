# Pruning empty metric-flush tasks does not help this listing

The real command skips only **1,149 of 481,449 dispatches: 0.24%**. Almost every selected runtime already has a metric provider. The candidate stays disabled, and no unprofiled timing cohort or upstream proposal is warranted.

The session currently launches one metric-flush task per live client. A client whose provider is uninitialized or already shut down returns immediately. The candidate publishes provider readiness with an atomic flag and filters those no-op tasks before dispatch. It retains every initialized provider, trace/log flush, callback and shutdown barrier. It adds no scan lock.

A first, unmeasured design checked each provider under its mutex. Review rejected that design because selection could wait behind a busy exporter before dispatching unrelated work. The replacement regression uses a blocked real metric exporter and verifies that selection remains responsive. Existing routing, exported-metric, reclamation and shutdown tests pass under the race detector with pruning disabled and enabled. Synthetic tests that install a provider directly also publish its readiness.

## Component ceiling and real mix

Four alternating fresh-process pairs benchmark selection and dispatch for 800 clients. Initialized clients use manual readers; these component numbers measure dispatch, not the real periodic readers' collection/export cost.

| Initialized providers | Original dispatch | Filtered dispatch | Allocations |
| --- | ---: | ---: | ---: |
| 0/800 | 264.58 µs | 9.38 µs | 1,602 → 2 |
| 8/800 | 259.01 µs | 14.26 µs | 1,602 → 18 |
| 800/800 | 258.80 µs | 263.55 µs | 1,602 → 1,602 |

The large component gain depends on a client mix absent from the measured repository. The real mechanism capture keeps the selected Go module and every selected engine optimization, with telemetry, ordinary GC, native cache and cleanup enabled. It starts a fresh CLI and source edit on the retained engine. It returns the same ordered 4,398 rows and exits successfully in **52.23 seconds**, recording 421,399 events without loss or unfinished operations. That is a diagnostic with profiling and counters, not a latency comparison with earlier commands.

Pruning and its counters are restored off. No telemetry is suppressed. The final native-cache checks verify all six retained Rust histories with pruning enabled, then restore it off: **130/130, 1,026/1,026 and 6/6**, twice each. The engine replacement exits gracefully and keeps the volume.

## Query phase markers identify the next target

The capture also separates GraphQL schema access from response execution. Each request owns its profiling wrapper; the underlying schema, response, errors and cancellation remain the same. A focused regression and the server race suite pass.

All 7,820 API requests retain exact backend parents. In the 48.48-second main query, schema access accounts for only **28 ms on the critical path**. Response execution outside recorded children accounts for 11.57 seconds, and result publication for 17.21 seconds. Several individual publications stall for seconds. These durations are specific to this capture and cannot be combined with earlier profiles.

A [targeted tail recording](NATIVE_GO_QUERY_ATTRIBUTION.md) then captures CPU, lock and goroutine evidence while those stalls recur. It finds cache maintenance overlapping the query, including class compaction and cache-usage collection. That evidence supports investigating maintenance work and its lock duration; it does not establish an optimization yet.

The first server-test command omitted the existing controlled suite's required `DAGGER_TEST_PARALLEL_CLIENT_ADMISSION=on` setting and fails its unrelated concurrency assertion with pruning disabled. The failed command is retained. The corrected command uses the required setting in both pruning arms. Component sources before the later query markers are preserved separately in `SOURCE_STAGES.json`.

[Sources, all attempts, benchmarks, race checks, native histories and the real capture](experiments/metric-flush-uninitialized/).
