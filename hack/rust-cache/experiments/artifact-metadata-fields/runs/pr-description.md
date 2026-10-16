`Artifact.description` and `Artifact.uri` derive strings from an already retained artifact. Large listings currently publish each string as another result-cache entry. Use the existing `simple field selection` policy for these two getters.

In two eight-pair comparisons of complete edited 1,026-package listings:

| Cohort | Before | After | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Initial | 2.84 s | 2.60 s | 182 ms | 8/8 |
| Confirmation | 2.82 s | 2.48 s | 380 ms | 7/8 |

Across both cohorts, the median paired saving is **328 ms**, with **368 MB fewer allocated bytes** per listing. Profiles show **2,052 fewer result publications**; both getters are still read 1,026 times, and artifact/key objects remain cached and loadable by ID. Edited build/test controls show no established compilation gain.

Measurements use warm compiler/engine caches, a fresh CLI process and source edit for every command, telemetry enabled, ordinary Go GC and snapshot collection, and balanced randomized ordering. Both arms use the same diagnostic engine and native history; only these field policies change. These complete-command results are from the experimental Rust-module engine. The standalone patch is based directly on upstream main. All admitted samples and pressure are retained, including a worktree checkout during confirmation.

The production change is two field policies. It adds no lock or shared state. The existing object-ID policy is preserved: making the dimension-key object list uncached failed its ID test and is excluded. Compatibility tests cover metadata changes and loading artifact and key IDs; all six native compiler-cache histories remain reusable. Focused artifact race suites are checked on the standalone upstream patch.
