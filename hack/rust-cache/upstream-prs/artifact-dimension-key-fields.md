# perf: read artifact dimension key fields directly

Expanded collection listings read `ArtifactDimensionKey.dimension` and `.key` for every dimension key. These resolvers return two stored strings; caching them adds result lookup, ownership and publication work to each expanded listing.

Mark both fields as simple uncached selections, following the existing `TypeDef` getters. The production change is two struct tags. Parent objects keep their existing cache policy and IDs; field telemetry remains enabled.

Complete `dagger check --list --all rust:packages/check` commands over 1,026 packages, after fresh source edits, on the native Rust prototype's engine. Both arms share the same binary and other patches; only these two getter policies vary:

| Measurement | Before | Candidate |
| --- | ---: | ---: |
| Median elapsed time, 16 pairs | 3.743 s | 2.877 s |
| Median engine CPU | 16.18 CPU-s | 12.17 CPU-s |
| Result publications in paired profiles | 13,677 | 7,521 |

All sixteen listing pairs improve. Median paired saving is **794 ms**, with **808 MB less allocation** per pair. Engine/compiler caches are warm, CLI processes are fresh, and telemetry stays enabled. Confirmation reverses the Dagger ordering. All observations are retained; timings exclude profiling.

Edited checks have no established gain. Their profiles execute neither getter. A separate check-only comparison shows a 43 ms paired slowdown; an identical-policy control produces a 30 ms difference with the same uneven Go-GC counts. Those controls and raw measurements are included for review.

The standalone GraphQL benchmark improves **226 → 86 ms** for 3,078 key objects and **385 → 265 µs** for three objects, in all six fresh-process pairs. Fixtures are outside the timer; every iteration reads a new parent generation.

The standalone branch passes focused artifact/schema race tests. The compatibility test checks values and parent-object ID reloads on main and the patch. All six retained native Rust histories remain fully reusable. The annotations reuse the existing getter path and introduce no lock, shared state, API or stored-format change. Rust compiler artifacts and incremental state keep their native snapshot caching.

```sh
go test -race -count=1 ./core/schema -run '^Test(Artifact|DimensionKeyFields)'
go test -run '^$' -bench '^BenchmarkDimensionKeyFieldReads$' -benchmem ./core/schema
```

[Branch](https://github.com/grouville/dagger/tree/perf/upstream-artifact-dimension-key-fields) · [Measurements, controls and profiles](../NATIVE_DIMENSION_KEY_FIELDS.md). No PR is open.
