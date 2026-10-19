# perf(dang): reuse empty callers for concrete function callbacks

`callFunc` allocates an empty caller object and type for each list or map callback, including nine empty maps. Concrete Dang functions only read its self, which is absent here; arguments and locals belong to a fresh function scope.

Reuse the empty caller for `FunctionValue` callbacks. Other `Callable` implementations retain a fresh caller because their Go implementation may mutate it. This was found while reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing after a fresh edit | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Test file | 10.01 s | 9.53 s | 4.8% |
| Ordinary source | 6.75 s | 6.13 s | 9.2% |

Four alternating pairs per workload, faster in all eight. Allocation falls **11.07 → 10.01 GB** for test edits and **6.29 → 5.19 GB** for source edits. CPU also falls in both workloads.

Commands start a fresh CLI, make real edits on the same warm experimental engine, and include telemetry, final flushing and successful cleanup. All 24 commands return correct rows. Profiles retain all 800 package getters, existing discovery hits and callback-body execution.

### Validation and tradeoffs

The standalone patch applies to pristine Dang da1bed304c and passes its full race suite. The development interpreter and Dagger SDK race suites also pass. Tests cover concurrent arguments, captured self and custom caller mutation. Sharing with every `Callable` deliberately makes the custom-callable regression fail.

Nine Go checks and 28 Rust/native-cache cases have their expected outcomes. The shared object contains no invocation data; fresh function scopes remain essential. No function results or user data are cached. Cold-start and Rust latency gains are unmeasured.

[Standalone patch](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/experiments/go-runtime-preparation-current/callback-standalone.patch). [Measurements and validation](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_DANG_CALLBACK_CALLER.md).
