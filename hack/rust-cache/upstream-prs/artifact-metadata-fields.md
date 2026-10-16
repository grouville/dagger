# perf: read artifact metadata strings without caching

`Artifact.description` and `Artifact.uri` derive strings from an already retained artifact. Large listings currently publish each string as another result-cache entry. Use the existing `simple field selection` policy for these two getters.

Complete edited 1,026-package listings, with both arms sharing one experimental Rust-module engine and native history:

| Cohort | Before | After | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Initial | 2.84 s | 2.60 s | 182 ms | 8/8 |
| Confirmation | 2.82 s | 2.48 s | 380 ms | 7/8 |

Across both cohorts, median paired saving is **328 ms**, with **368 MB fewer allocated bytes** per listing. Profiles show **2,052 fewer result publications**. Both getters are still read 1,026 times; artifact and key objects remain cached and loadable by ID. Edited build/test controls show no established compilation gain.

Six component pairs directly on upstream main repeat **76.3 → 31.6 ms** for 1,026 artifacts, with **37.0 → 26.1 MB allocated**. The single-artifact case improves **219 → 148 µs**. Fixtures are outside the timer; every iteration reads a new parent generation.

The production change is two field policies and adds no lock or shared state. Focused artifact/core/schema race suites pass on the standalone patch. Compatibility tests cover changing metadata and loading artifact and key IDs. All six native compiler-cache histories remain reusable.

Command measurements use warm engine/compiler caches, fresh source edits and CLI processes, telemetry enabled, ordinary GC, and balanced randomized ordering. All admitted observations and pressure are retained, including a worktree checkout during confirmation. Complete-command results use the experimental engine; standalone tests and components run directly on main.

[Branch](https://github.com/grouville/dagger/tree/perf/upstream-artifact-metadata-fields) · [Measurements, controls and profiles](../NATIVE_ARTIFACT_METADATA_FIELDS.md). No PR is open.
