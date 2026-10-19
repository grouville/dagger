# perf: avoid allocating empty callers in collection callbacks

`callFunc` creates an empty caller object and type for every list or map callback, including nine empty maps. Concrete Dang functions only read the caller's `self`; the synthetic caller has none. Their arguments and locals live in a fresh scope derived from the function's closure.

Reuse that empty caller for `FunctionValue` callbacks. Other `Callable` implementations keep a fresh caller, because their Go implementation can mutate it. Callback execution, captured state, errors and control flow retain their existing paths. No user data or function results are cached.

Complete Go test collection listing on real dagger/dagger:

| Edit | Before | After |
| --- | ---: | ---: |
| Test file | 10.01 s | 9.53 s |
| Ordinary source | 6.75 s | 6.13 s |

Each row is the median of four balanced pairs on a warm engine with fresh CLI processes and real edits. Both arms finish test addition and removal before measured pairs. Every pair improves; all 24 commands return correct ordered rows and exit successfully. Timings include telemetry, final flushing and session cleanup, with profiling separate.

Cumulative allocation falls 11.07 → 10.01 GB for test edits and 6.29 → 5.19 GB for ordinary-source edits. CPU falls 51.81 → 49.51 CPU-s and 30.27 → 26.85 CPU-s respectively. Lossless profiles retain all 800 authored getters after a test edit and the same discovery-cache hits. The source-only profile removes sampled caller type/object allocation while preserving callback-body work.

The standalone patch applies to pristine upstream snapshot `da1bed304cb80f8a2f0714f1747e7f64e03297a3` and passes its full interpreter race suite. The development interpreter and native SDK full race suites pass too. Tests cover concurrent arguments, captured `self` and custom caller mutation; removing the concrete-function guard makes the custom-callable regression fail. Nine Go checks and 28 Rust/native-cache cases also pass with their expected outcomes, including native action reuse in both modes.

The command measurements use the same experimental Dagger engine, CLI and Go module in both arms; the standalone interpreter patch is checked independently. Cold performance and a Rust latency gain remain unmeasured. [Patch and complete evidence](experiments/go-runtime-preparation-current/).
