# Read source-error context only when evaluation fails

Every `EvalNode` call currently looks up its source-error context before evaluating the node. When present, the same value is then stored in another context wrapper. Successful evaluations do not use it; absent values may require walking a deep caller context chain. Profiling Go test collection listing found about eight CPU-seconds in this lookup.

Use the received context directly during ordinary node dispatch and fetch source-error information only when an error needs wrapping. Keep the explicit `EvalNodeWithContext` behavior, including an explicit nil argument. Control-flow sentinels, raised errors and nil-value validation retain their existing paths. This adds no cache, lock or retained invocation state.

On our development Dagger engine, complete listing improves:

| Fresh edit on a warm engine | Before | After |
| --- | ---: | ---: |
| Test file | 12.88 s | 11.51 s |
| Ordinary Go source | 6.67 s | 5.75 s |

Both workloads improve in all four balanced pairs. Test-edit engine CPU falls 73.59 → 65.77 CPU-seconds; ordinary-source CPU falls 28.22 → 23.36. Full-command allocations are essentially unchanged. Every command starts a fresh CLI, edits real source, keeps telemetry and normal GC, includes cleanup and returns the correct ordered rows. Other development optimizations are enabled in both arms, including the separate typed-method fix. These measurements do not establish cold-start or stock-main Dagger performance.

The regression independently fails on pristine upstream `da1bed304cb80f8a2f0714f1747e7f64e03297a3` and passes with only this production patch. Tests cover source locations, inherited/replaced/explicitly nil contexts, cancellation causes, unsupported nodes and control-flow behavior. The full upstream interpreter race suite and full development interpreter race suite pass. Seven focused Go/library checks also pass, including collection test execution and module-boundary changes. All 20 complete listing commands succeed.

Separate CPU captures support the intended mechanism: `GetEvalContext` falls from 8.07 CPU-seconds to no samples. The existing function evaluations, SDK request counts and collection discovery hits remain the same.
