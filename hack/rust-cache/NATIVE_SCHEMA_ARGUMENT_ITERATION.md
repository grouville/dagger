Building schema argument definitions currently copies full input descriptions into a temporary list before building the actual definitions. Selecting argument indices instead removes those copies while preserving the same visibility and override rules. Complete warm Go test listing after a test-file edit improves **6.76 → 6.58 seconds median**, with **6.313 → 6.114 GB allocated** per command. This is a small engine improvement; it does not meet the three-second goal.

The complete pipeline remains the acceptance criterion:

| Stage | What remains in place | Evidence |
| --- | --- | --- |
| Source and configuration | Live imports, edits, restoration and module ownership | Go ownership/layout/discovery checks and changed source on every timed invocation |
| Collection expansion | Existing authored getters and test discovery | All four profiles execute 800 getters and 804 module evaluations, retaining 799 discovery hits |
| Argument preparation | Last matching override, declaration order, defaults, descriptions and directives | Compatibility tests against the original code, followed by the full DagQL race suite |
| Selection and execution | Normal collection filters, conversions, failures and actual test execution | 27 Go checks and 28 Rust cases, including expected failures and an invalid excluded package |
| Native Rust cache | Normal compiler actions and native snapshots | Repeated native-cache calls recover every action in both engine modes |
| Command completion | Output, telemetry, ordinary GC and session cleanup | All 24 timed commands exit successfully with exact ordered rows; final lifecycle is idle |

The engine patch extracts the existing argument selector into one shared helper. It keeps selected indices in a small stack buffer, retains the existing map threshold for larger argument lists, and lets each caller construct its required output. It introduces no persistent cache, lock, dependency or API. The production diff is 25 insertions and nine deletions in dagql/objects.go. Argument definitions remain fresh objects, and the public Inputs method still returns its own list. The existing small-list quadratic duplicate check and large-list map algorithm are unchanged.

| Component, four alternating pairs | Before | After | Bytes before → after |
| --- | ---: | ---: | ---: |
| One argument definition | 440 ns | 381 ns | 485 → 341 |
| Eight argument definitions | 3.45 µs | 2.94 µs | 4,012 → 2,731 |
| Sixteen argument definitions | 7.35 µs | 6.42 µs | 9,088 → 6,527 |
| Sixty-four argument definitions | 28.52 µs | 25.08 µs | 34,825 → 25,862 |

All definition cases improve in all four pairs. There is a tradeoff for direct Inputs callers: selecting more than 15 raw arguments adds one temporary index allocation. At 16 arguments its benchmark moves **1.712 → 1.767 µs**, with **3,624 → 3,752 bytes**; at 64 it moves **5.848 → 5.697 µs**, with **12,968 → 13,480 bytes**. One argument moves **73 → 80 ns**, with unchanged allocation. These regressions are retained in the evidence. The candidate is useful because schema construction accounts for most of the observed input-list copies, not because every caller becomes faster.

| Complete warm listing, fresh CLI and real edit | Before | Candidate | Faster pairs |
| --- | ---: | ---: | ---: |
| Ordinary Go source | 4.02 s | 3.89 s | 4/4 |
| Test file | 6.76 s | 6.58 s | 4/4 |

Test-edit paired savings are **157 ms median**, ranging from **6 to 414 ms**. Engine CPU medians fall **27.65 → 26.87 CPU-seconds**. Exact allocation medians fall **6.313 → 6.114 GB**, with a median paired saving of **204 MB**; CPU and allocation decrease in all four test-edit pairs. Ordinary-source paired savings are 82 ms, but CPU is flat at 9.99 CPU-seconds and allocation is flat at 1.882/1.883 GB. Only three module evaluations are expected after that edit, so no material source-edit resource improvement is claimed. Separate medians and paired differences are different statistics.

Both workloads use two complete initialization blocks, adding and then removing a real test, before four alternating measured pairs. The first block returns 4,399 rows and all subsequent blocks return 4,398. Timings include output, telemetry export and successful cleanup. No profiler or forced GC runs during timing. Both arms use the same Go module, CLI, engine binary, reader improvement, primitive-array selection and native glob pruning. Only argument selection changes. Correctness checks and initialization warm the caches; this establishes neither empty-cache first use nor restart performance. Engine memory pressure remains negligible. Source files, modules and all flags are restored afterward.

Four separate lossless wcprof/CPU/allocation captures confirm equal work in both modes: **800 getter executions, 804 module evaluations, 799 discovery hits and 1,415 SDK requests** per invocation, with no dropped events or open operations. The diagnostic invocations are not latency samples. Go's sampled allocation profiles can lag GC cycles and carry samples from the preceding mode; the exact TotalAlloc counters above are the authority for per-command bytes. A long result-encoding span still includes GC and waiting, so its elapsed duration is not a promise of removable serialization CPU.

The Rust cases verify correctness and native-cache reuse; they are not Rust latency measurements.

The standalone source is based on upstream **91e4d2b9e20b12d9c42fc923e91403b2805a88b5** and committed as [67eec58314](https://github.com/grouville/dagger/commit/67eec58314e531fb96eb2eed8b1d6c02617a3594) on experiment/schema-argument-iteration. Its full DagQL race suite and the exact development-overlay DagQL race suite pass. The final test-only formatting changes do not alter the tested behavior. The benchmark engine is **c50f994b6e8b673a7fb8dc5b77d98e242ac7b827ed921b4f6d6e238fcd972090**; its shared development base is ff0b029a4d270a651b9a8c7286babc79089066e4. The standalone selector/definition implementation matches that engine apart from diagnostic mode dispatch. The selected Go module remains 720a5258ad8212ab643bbeaa4084127b2e866800, Rust remains 31810265724e9a4b3f7ec36e2b3934b7182e340f, and the pinned CLI is unchanged. This is a controlled development-stack comparison, not a stock release result.

The source is pushed to the fork for review and the [PR description](PR_SCHEMA_ARGUMENT_ITERATION.md) is prepared. No PR is opened. [Evidence](experiments/schema-argument-iteration/) includes both race logs, component pairs, every command and attempt, lossless profiles, exact source identities and the production patch. All sixteen engines and volumes remain intact, with no active requests or runtimes. Keep this as a modest allocation improvement; the next larger investigation is repeated schema construction and receiver conversion, retaining the same getter behavior and the full execution contract.
