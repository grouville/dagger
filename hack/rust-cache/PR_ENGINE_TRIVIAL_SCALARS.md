# perf(dagql): read trivial scalar fields without another cache result

Generated scalar getters read data already held by their receiver, but ordinarily perform another cache lookup and publish a separate result. Go test listing repeatedly reads search-result paths and matched text.

Return plain builtin scalar data through the existing uncached path for generated getters marked trivial. Objects, lists, indexed selections and custom scalar types retain their existing policy. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Measurement | Before | After |
| --- | ---: | ---: |
| Complete Go test listing | 40.49 s | 39.20 s |
| Cumulative engine allocation | 32.65 GB | 31.78 GB |
| Five fields on 1,026 new objects | 138.0 ms | 33.6 ms |

Complete listing improves **3.2%**, in all four alternating pairs. Commands start a fresh CLI, edit source on the same warm experimental engine, return identical 4,398 rows, and include telemetry and successful cleanup. A lossless profile confirms 9,696 search-field publications disappear while the field reads remain.

Repeated reads have a cost: the 1,026-object control improves **28.1 → 16.2 ms** but allocates **14 → 22 MB**, constructing scalar wrappers again. Full listings allocate less in every pair; CPU is mixed, with a median paired increase of 0.77 CPU-second.

### Validation and tradeoffs

The full DagQL race suite and 32 module-object/stored-result checks pass. Coverage includes nullable and zero values, parent lifetime, IDs, concurrent reads, ordinary function cache hits and a resource-owning custom integer. Six Rust compilation histories retain their action hits across restart.

Matching concrete builtin types matters: a custom integer may own a release callback and still require an attached result. The patch changes no API, storage format or lock.

[Source](https://github.com/grouville/dagger/tree/perf/direct-trivial-scalar-fields). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_COLLECTION_SCALAR_PROJECTION.md).
