# perf: avoid item cache entries when listing stored metadata

Listing all 4,398 Go tests on `dagger/dagger` creates 17,592 cache entries just to read collection dimension keys. Each key already contains the two strings the CLI needs.

Allow explicitly declared data-only classes to read those fields while retaining their parent list. Only `ArtifactDimensionKey` opts in. Normal functions, resources and ID selections keep their existing handling, and scalar getters still emit telemetry. This adds no cache format, dependency, lock or user setting.

Four alternating full-command pairs, including startup and cleanup:

| | Before | After |
| --- | ---: | ---: |
| Median elapsed time | 42.24 s | 35.90 s |
| Median allocated bytes | 32.79 GB | 29.09 GB |
| Median engine CPU | 211.49 s | 187.93 s |

Every pair is faster and allocates less. All ten commands, including initialization, return the correct ordered rows and exit successfully. Both arms use the same warm engine with a fresh CLI and source edit; telemetry and ordinary GC remain enabled.

One control runs during cache compaction, so its 12.50-second gap is not all attributable to this change. The first two pairs each save about five seconds. Wcprof separately confirms exactly 17,592 fewer key-item publications, with every string getter preserved.

The main risk is incorrect data-only classification: opting in requires immutable values without resource or session lifecycle. The selector also rejects known resource hooks, cached result elements and nontrivial selections. Tests cover later ID loads, nullable fields, aliases, concurrent lists and release behavior. The native-field regression asserts zero item rows for scalar output, followed by valid attached IDs for explicit access. The full standalone DagQL race suite and 32 top-level retention tests pass; all six retained Rust cache histories remain fully reusable after engine replacement and the cohort.

Repeated reads of a large component fixture allocate 6.27 MB more and have no established latency gain. The complete edited listing still allocates less in every pair.

[Code on the fork](https://github.com/grouville/dagger/tree/perf/project-data-list-scalars), commit `5a36ffd0`, builds on `perf/direct-trivial-scalar-fields`. [Full measurements, rejected variants and validation](../NATIVE_COLLECTION_DATA_PROJECTION.md). No PR has been opened.
