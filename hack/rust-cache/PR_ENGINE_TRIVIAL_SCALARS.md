Generated scalar getters read data their receiver already holds, but normally perform another cache lookup and publish a separate result. A Go test listing reads search-result paths and matched text over 18,000 times.

Return plain builtin scalar data through the existing uncached path. This applies to generated native struct and module-object getters marked trivial. Object fields, lists, indexed selections and custom values keep their existing policy. Match concrete builtin types: a custom integer can own a release callback and still needs an attached result. No cache format, lock, dependency or API changes.

| Measurement | Before | After |
| --- | ---: | ---: |
| Complete Go test listing on dagger/dagger | 40.49 s | 39.20 s |
| Cumulative engine allocation | 32.65 GB | 31.78 GB |
| Five fields on 1,026 new objects | 138.0 ms | 33.6 ms |

All four alternating full-command pairs improve. Every command starts a fresh CLI, edits a source comment on the same warm engine, returns the same 4,398 ordered rows and exits successfully through cleanup. Telemetry and ordinary GC stay enabled. Initialization adds and removes a real test and is reported separately. A complete wcprof capture confirms 9,696 search-field publications disappear while their reads and all artifact/key element reads remain present.

Repeated reads trade allocation for time: the 1,026-object case improves 28.1 → 16.2 ms but allocates 14 → 22 MB because it constructs scalar wrappers again. Complete edited listings allocate less in every pair, saving 800 MB at the median paired difference. Engine CPU is mixed, with a median paired increase of 0.77 CPU-second; no CPU improvement is claimed. Listing remains far too slow.

The complete DagQL race suite and 32 module-object/stored-result checks pass. Added checks cover nullable and zero values, retained parent data, array/object IDs, concurrent reads, ordinary function cache hits and a resource-owning integer. All six native Rust histories retain every compiler action across restart and after the full comparison and profiling.

[Review branch](https://github.com/grouville/dagger/tree/perf/direct-trivial-scalar-fields). [Full measurements and limitations](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_COLLECTION_SCALAR_PROJECTION.md). No PR is open.
