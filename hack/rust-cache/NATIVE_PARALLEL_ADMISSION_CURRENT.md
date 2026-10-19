# Parallel admission regresses the current listing stack

Parallel nested-client admission remains **unselected**. Retesting it after local generation matching makes complete listing slower in both edit workloads, with higher CPU use.

| Complete command | Original admission | Parallel admission | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 7.15 s | 8.34 s | 1/4 |
| Ordinary-source edit | 4.31 s | 4.69 s | 1/4 |
| Test-edit CPU-seconds | 31.10 | 34.47 | — |
| Ordinary-edit CPU-seconds | 11.49 | 13.89 | — |

Both versions use Go module `511d381`, the same engine binary and the same selected settings. Each command starts a fresh CLI, receives a real source edit on a warm engine, and includes telemetry, normal GC, output, final flushing and cleanup. Both modes complete test addition and removal before four alternating measured pairs per workload. All 24 commands return the correct ordered 4,398 rows and exit successfully. Earlier cohorts are separate and are not pooled with this retest.

## What the lock protects

`getOrInitClient` holds the session lifecycle lock while admitting a request and, when needed, initializing its runtime. That includes telemetry-store retention, schema setup and client-bound providers. The experimental path takes the lifecycle lock for reading for existing sessions' nested clients, with a separate admission mutex for each client. Session creation and root requests retain exclusive locking; metadata, request leases and cleanup checks remain.

The earlier selected-module profile placed 1.77 seconds of its test-edit critical path in lifecycle waiting, which justified this retest. Corrected before/after captures retain all 800 getter executions, 799 unchanged discovery hits and 1,415 SDK requests. Parallel admission removes lifecycle waiting from the leading critical-path classes, but work shifts to other stages. One instrumented candidate trace is faster than its control; that does not override the completed unprofiled cohort, where three of four pairs regress in each workload.

All 27 Go check invocations and 28 Rust/native-cache cases pass with their expected outcomes. These cover actual selected execution, expected failures, source edits and restoration, generation policy and native compilation-action hits. They establish behavior for the exercised workflows, not a Rust latency improvement. The engine source is unchanged from the existing diagnostic build; its prior exact-overlay server race suite already ran with parallel admission enabled.

The initial baseline profile failed in the script's cleanup after the CLI completed: a generated flag lookup used a tuple key. Other source, configuration and mode restoration steps had run. The remaining diagnostic counter was restored, the engine was verified idle, and the final raw buffer was preserved. That attempt is retained and is not counted as a successful capture. Only the four corrected captures enter the analysis; timings were not rerun.

## Follow allocation rather than the wait alone

A separate allocation capture uses the selected admission mode and returns all rows without lost wcprof events. The exact runtime counter records **6.78 GB** allocated and three natural collections. The after-minus-before sampled allocation profile reports **4.96 GiB**; profile samples can lag natural collection and are not a complete attribution of that counter. No collection was forced.

Direct samples attribute roughly **0.55 decimal GB** to Dang's `Object.Bind` and `Object.Derive`, and **0.44 GB** to log `ForceFlush`. The latter is the already-rejected flush-buffer experiment, not a new finding. `Derive` already uses a parent chain, so replacing an assumed full-environment copy would target work it does not do. Audit the actual binding and conversion paths before another allocation change. The original profiles, corrected `-base` analysis and initial engine-lifetime-denominator output are retained.

That source audit also found an independent [SDK list-type bug](NATIVE_DANG_LIST_ELEMENT_TYPES.md). It has a clean-main regression and a one-line fix; it is not counted as a speedup.

[Evidence](experiments/parallel-admission-local-discovery/) contains all samples, behavior checks, five successful lossless captures, the failed capture and recovery record, source references and allocation analysis. All nine engines and volumes are retained, workspaces and capture switches are restored, and no performance change or PR is selected here.
