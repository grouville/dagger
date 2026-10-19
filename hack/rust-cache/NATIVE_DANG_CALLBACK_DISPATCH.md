# Callback argument preparation screens

Neither screen establishes a faster complete Go test listing. The selected stack stays unchanged.

Concrete callback dispatch reduces allocation but changes test-edited listing **8.22 → 8.81 seconds median**, faster in only one of four pairs. Ordinary-source listing is **5.47 → 5.37 seconds**, faster in three pairs. Both modes use the same experimental stack; only callback dispatch changes. Fresh CLIs, real edits, normal telemetry, GC, output and successful cleanup are included on a warm engine. Cold and Rust edited-build performance are unmeasured.

| Complete listing | Original | Concrete dispatch |
| --- | ---: | ---: |
| Test edit, elapsed median | 8.22 s | 8.81 s |
| Test edit, engine CPU median | 40.15 CPU-s | 40.50 CPU-s |
| Test edit, allocated bytes median | 9.57 GB | 9.26 GB |
| Source edit, elapsed median | 5.47 s | 5.37 s |
| Source edit, allocated bytes median | 5.18 GB | 4.86 GB |

All 24 commands return correct ordered rows and exit successfully. Both modes complete test addition/removal before four balanced pairs. Host CPU pressure varies; the CPU samples do not support a large copy-cost regression. The latency cause remains unresolved, so the candidate stays disabled.

The nine-line standalone patch builds the same argument map in a concrete `FunctionValue` branch and calls the existing handler directly. Other callables retain their path. Go proves the map stays on the stack: `make(map[string]Value) does not escape`. Binding, defaults, control flow and fresh scopes keep their behavior. The patch adds no cache, API or lock.

Four native-only component pairs on Go 1.26.6 improve **2.22 → 2.05 µs** and **2,648 → 2,312 B/op**, removing two allocations. Pointer and custom-callable controls retain their allocation counts. Custom Go callbacks may retain their argument maps and mutate their callers, so they keep the original path.

Pristine and development interpreter race suites and the native SDK race suite pass. Checks cover concurrent arguments, captured `self`, custom caller mutation and retained argument maps. Eighteen Go checks and 28 Rust/native-cache cases preserve discovery, selection, execution, expected failures, changed/restored source and native compiled-result reuse. Both test-edited profiles retain **804 evaluations, 1,494 SDK requests, 800 getters and 799 unchanged discovery hits**. All four streams are lossless.

The preceding provenance-map screen saves no heap allocation: Go already keeps that map on the stack. Caller-level attribution to positional binding was insufficient to blame the auxiliary map. Its semantic tests pass both implementations, including duplicate diagnostics and mutable parameter names; it is not ported to the engine.

Harness failures and unmatched benchmark attempts are retained and excluded from summaries. Exact sources, commands, compiler diagnostics and binary hashes identify each cohort.

The ordinary-source diagnostic's 5.32-second critical path assigns 1.76 seconds to `Workspace.glob` and 1.30 seconds to interpreted execution. The test-edit path includes 1.62 seconds waiting on `session:lifecycle`. Investigate those larger costs while preserving freshness, permissions and invocation state. Native Dang already returns results directly; there is no redundant return-value GraphQL request to remove. These diagnostic durations are not promised savings.

[Standalone patch](experiments/dang-callback-direct-call-engine/callback-standalone.patch), [all sources, controls, attempts, checks and lossless profiles](experiments/dang-callback-direct-call-engine/). The seventh isolated engine and its cache are retained; the previous six binaries and volumes are unchanged. Sources and switches are restored, and no client remains active. No PR is opened or proposed for this unselected latency experiment.
