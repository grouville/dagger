# perf(dang): read source-error context only when evaluation fails

Every `EvalNode` call looks up source-error context before evaluating its node. Successful evaluation does not use that value; an absent value can still require a deep context-chain walk. Go collection profiling found about eight CPU-seconds in this lookup.

Use the received context for ordinary dispatch and fetch source-error information when wrapping an error. Explicit `EvalNodeWithContext` calls retain their replacement behavior, including an explicit nil argument. This was found while reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing after a fresh edit | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Test file | 12.88 s | 11.51 s | 10.6% |
| Ordinary source | 6.67 s | 5.75 s | 13.8% |

Four alternating pairs per workload, faster in all eight. Engine CPU falls **73.59 → 65.77 CPU-s** for test edits and **28.22 → 23.36 CPU-s** for source edits. Allocation is essentially unchanged.

Each command starts a fresh CLI on the same warm experimental engine, includes telemetry and successful cleanup, and returns the same ordered rows. Other development changes are present in both arms. Separate CPU captures show GetEvalContext dropping from 8.07 CPU-seconds to no samples; evaluations, SDK requests and discovery hits remain.

### Validation and tradeoffs

The focused regression fails on pristine Dang da1bed304c and passes with only this production patch. Tests cover source locations, inherited/replaced/nil contexts, cancellation, unsupported nodes, control-flow sentinels and nil-value validation.

The full upstream and development interpreter race suites pass, as do seven focused Go/library checks. All 20 listings succeed. The standalone patch changes only `pkg/dang/eval.go`, with no cache, lock or retained invocation state. Cold-start and stock-main Dagger latency are unmeasured.

[Standalone patch, commands and measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_DANG_LAZY_ERROR_CONTEXT.md).
