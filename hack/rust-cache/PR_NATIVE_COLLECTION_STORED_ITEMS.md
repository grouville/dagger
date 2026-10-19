Prototype review notes, not a ready upstream PR. The engine and Go module changes must be reviewed together. No PR is open.

Title: **Resolve stored collection items without starting module getters**

A test-file edit currently causes 800 package getters to enter the module runtime, even though only one package's test discovery changes. Each call repeats source, schema, receiver and session preparation.

Let an author use the existing `@get` marker on stored key/value entries. The engine indexes the entries and returns the selected value directly. Function getters retain their current behavior. The Go prototype prepares those entries while package ownership is already known.

On dagger/dagger, with all 4,398 test checks listed:

| Complete edited listing | Before | Prototype |
| --- | ---: | ---: |
| Test-file edit | 10.81 s | 7.04 s |
| Ordinary-source edit | 6.00 s | 6.52 s |

Four balanced pairs per workload, fresh CLI and warm engine, telemetry and ordinary GC enabled, through successful cleanup. All 24 commands return correct rows. Test edits improve in every pair; ordinary-source edits regress in every pair. Cold effects are unmeasured.

Separate wcprof captures show module evaluations falling 804 → 4 with essentially unchanged SDK request counts. Test-edit CPU halves and allocation falls 15.25 → 6.69 GB. Existing per-item discovery reuse remains: one changed execution, 799 hits.

Core and SDK race checks and eight focused module commands pass. Tests cover lookup order, concurrency, subsets, implementation/type/view separation, unchanged/changed item hits, source edits and actual test/binary/generation execution.

Keep this experimental until the source-edit regression is resolved. Further SDK, malformed-data, enum/scalar, stored-entry persistence and resource-lifetime validation is required. The existing marker's stored form needs an agreed contract and documentation before proposing it upstream.
