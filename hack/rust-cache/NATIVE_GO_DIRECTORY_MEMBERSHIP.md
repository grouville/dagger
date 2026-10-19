# Directory membership in the complete Go listing pipeline

The selected candidate uses Dang's existing `List.contains` instead of `List.any` with a string-equality callback. It changes two lines in generation-directory selection. On real dagger/dagger:

| Complete listing after an edit | Before | Native membership | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 7.63 s | 7.44 s | 6/8 |
| Ordinary source | 4.40 s | 4.17 s | 3/4 |

These are fresh CLI processes on one warm development engine, with real edits, normal telemetry, ordinary GC, output, final flushing and successful session cleanup. The table uses the fixed eight-pair test-edit follow-up and the four-pair ordinary-source cohort. Both versions complete test addition and removal before measured pairs. All 44 real-repository commands across the initial screen and follow-up return the correct ordered rows. The stable list contains 4,398 rows. These are separate cohorts from earlier results; savings are not additive. Current cold, released-engine and Rust latency effects are unmeasured.

The initial four-pair test screen was **8.33 → 7.18 s**, faster in 4/4 pairs. Its larger saving prompted the fixed follow-up above because baseline times varied from earlier cohorts. Both cohorts are retained, without pooling or discarding samples. Use the follow-up when assessing latency; do not promise the initial saving on every run. The follow-up has a 111 ms median paired saving and retains one candidate run that is 1.69 s slower. This is a small simplification with lower allocation, not a large or uniform latency win.

| Engine work | Test edit, before → after | Ordinary edit, before → after |
| --- | ---: | ---: |
| CPU-seconds | 32.13 → 31.30 | 11.07 → 11.10 |
| Allocated bytes, decimal GB | 6.495 → 6.348 | 2.063 → 1.918 |

An allocation audit traced most sampled scope binding to function arguments. A separate diagnostic engine counted 284,472 local function calls in one edited listing, including 94,232 calls to the generation selector's equality callback. Those counts locate repeated work; they are not elapsed-time measurements. The diagnostic engine is excluded from timing cohorts.

`List.contains` and the `==` operator both call `valuesEqual`; strings compare their stored bytes. The module still computes the same workspace globs, preserves the include-all case and applies exclusions. Discovery, authored getters, initialization, state, errors and selection remain in the pipeline. No index, new builtin, engine patch, cache or lock is needed for this module change. Both timing arms use the original map-merge implementation.

Profiles retain 804 evaluations, all 800 getter executions and 799 unchanged test-discovery hits after a test edit. Ordinary-source captures retain all 800 getter and discovery hits. SDK request counts remain 1,415 and 493 respectively. All captures are lossless and close every operation. All 27 Go check invocations pass, including generation policy, nested modules, changed and restored sources, selected tests and real binary execution.

| Smaller source-edit fixture | Before | Native membership | Faster pairs |
| --- | ---: | ---: | ---: |
| 1 module | 0.617 s | 0.594 s | 2/4 |
| 16 modules | 0.746 s | 0.893 s | 2/4 |
| 16 modules, fixed eight-pair follow-up | 0.744 s | 0.694 s | 5/8 |

All 44 small-fixture commands succeed with matching rows. In the initial sixteen-module cohort, both slower candidate runs cross a natural collection boundary; none of its baseline runs does. The fixed follow-up checks this imbalance without forcing or disabling GC. Both cohorts remain in the evidence. These short cohorts are controls for added overhead, not evidence of a universal small-repository speedup.

A separate directory-index candidate preserves behavior but does not justify its larger implementation: test edits change **7.42 → 7.38 s**, faster in only one pair; ordinary edits **4.54 → 4.36 s**, faster in three. It stays unselected. Both arms use linear native map merging, and its 27 Go checks and four lossless captures pass. Its helper is retained in the evidence, not pushed as a selected change.

Preparing that index exposed an independent quadratic operation in Dang: `Map.merge` repeatedly copies the accumulated map. A standalone change copies once and inserts the right-hand keys in order. For two disjoint 512-key maps it improves **18.31 ms → 59.50 µs** and **33.04 MB → 0.10 MB** per merge. All 24 component pairs improve across three sizes and both overlapping and disjoint keys. Order, replacement, empty/self merges, type metadata and input independence are tested; the full interpreter race suite passes with both implementations. The standalone commit is `e463a5cbc8bbe2f80d4f716b3de2b10f13ec7f7b`, based on upstream Dang `da1bed304cb80f8a2f0714f1747e7f64e03297a3`.

That map change alone leaves complete listing flat: test edits **6.91 → 6.94 s** and ordinary edits **4.11 → 4.20 s**. Its exact engine overlay passes the interpreter race suite, 27 Go checks and 28 Rust/native-cache cases with expected outcomes, including selected execution, failures, source changes and native action reuse. No Rust speedup is claimed. The map change remains disabled in the selected listing stack. Its small standalone patch and [review description](PR_DANG_MAP_MERGE.md) are retained for review; the checked account has no accessible `grouville/dang` fork, so it is not pushed to a new repository and no PR is opened.

[Selected Go source](https://github.com/grouville/go/commit/720a5258ad8212ab643bbeaa4084127b2e866800) follows `511d38145daf87b531e44ed9b1c3b641fbe89ba3` on the prototype branch; it is not a validated current-upstream port. The [module review description](PR_GO_NATIVE_MEMBERSHIP.md) is prepared. No PR is opened.

[Evidence](experiments/go-directory-membership/) retains all five studies, raw timings, checks, race results, fifteen lossless captures, source patches and exact engine-input deltas. The eleven engines and cache volumes remain intact; workspaces, profiling and experimental mode switches are restored. Diagnostic engines retain their source-counting environment settings. The three-second full-pipeline goal remains unfinished.
