# Skip module discovery for result graphs that reference no modules

The isolated lookup improves substantially, but the complete Go test listing does not: **37.47 → 37.56 seconds median**, faster in four of eight fixed pairs. Allocation is effectively unchanged at **29.35 GB**, and CPU changes **191.25 → 190.14 CPU-seconds**. The candidate remains disabled and is not counted as an end-to-end performance improvement. No PR is opened.

`Query.ModDepsForCall` prepares a list of every served module and its implementation-scoped comparison result before walking a stored call graph. Core-only graphs never use that list. The standalone change prepares it at the first actual `Module` reference, once per call. State stays local to the call; session validation, reference traversal and installed-module selection use the existing paths.

The [standalone patch](https://github.com/grouville/dagger/commit/c61e5a6348) has 13 changed production lines in `core/query.go`. The regression fails on upstream `ff0b029a`: a core-only graph performs one unrelated module lookup. It passes after the change. Imported-module preference and references in the module, receiver, arguments, implicit inputs and ancestors remain covered by existing tests. The upstream main reference is rechecked after the comparison and still names `ff0b029a`. The patch is kept on Guillaume's fork for tracking, without a new PR or an end-to-end speedup claim.

## Component measurements

Four fixed alternating pairs per case use the real `ModDepsForCall`, a real DagQL cache and attached module values. The fixture supplies a small implementation-scope resolver. Scoped rows are warmed before timing; each observation starts a fresh test process with normal GC and `GOMAXPROCS=8`. Shared test fixtures accept `testing.TB` so the regression and benchmark use the same setup.

| Graph | Served modules | Before | After | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Core only | 0 | 0.193 µs | 0.175 µs | 3/4 |
| Core only | 2 | 9.31 µs | 0.178 µs | 4/4 |
| Core only | 64 | 306.80 µs | 0.174 µs | 4/4 |
| References a module | 0 | 1.93 µs | 1.92 µs | 3/4 |
| References a module | 2 | 11.98 µs | 12.61 µs | 1/4 |
| References a module | 64 | 323.73 µs | 326.72 µs | 2/4 |

Core-only allocation falls **4,358 → 80 bytes** with two modules and **143,556 → 80 bytes** with 64. The module-bearing path retains the scan and shows slightly slower or mixed timings. These are component results, not listing gains.

## Complete commands

Both arms use one controlled binary, the same selected Go module, CLI, source and retained volume. Each invocation starts a fresh CLI and receives a source comment edit on the warm engine. Telemetry and normal maintenance remain enabled; profiling is off during timing. The measured time includes CLI exit, cleanup and a final log flush. No admitted observation is discarded or rerun.

| Pair | Eager candidates | Lazy candidates |
| --- | ---: | ---: |
| 1, candidate first | 35.98 s | 37.03 s |
| 2, control first | 37.59 s | 38.08 s |
| 3, candidate first | 36.44 s | 35.02 s |
| 4, control first | 40.24 s | 35.90 s |
| 5, candidate first | 39.32 s | 36.17 s |
| 6, control first | 37.35 s | 38.41 s |
| 7, candidate first | 36.66 s | 38.54 s |
| 8, control first | 39.65 s | 38.69 s |

All eighteen commands succeed with correct ordered output. The excluded initialization pair adds a real test, lists 4,399 rows and takes 61.80 → 38.50 seconds. Removing it restores the expected 4,398 rows. That initialization difference is not a measured gain. The median paired saving is 0.235 seconds; column medians are effectively unchanged and must not be replaced by that different statistic.

## Work removed and correctness

A separate lazy-mode diagnostic returns the correct rows in 56.40 seconds, with 985,599 events and none dropped or open. Exact parent links identify **3,506 successful schema-recovery calls and zero candidate scans**. A subsequent eager-mode positive control on the same binary records **3,506 successful recoveries and 3,506 scans**. It returns the correct rows in 41.89 seconds with 1,002,959 lossless events. Both retain 7,820 SDK requests, 963 Dang invocations and 2,508 host-directory calls. These profiled durations are not latency samples.

The copied positive-control analyzer initially reads the candidate directory again. Correcting its path and reprocessing the immutable captures restores the positive control. The analyzers now verify the expected mode and record capture directory, engine hash and event count; eager mode must contain exactly one scan per successful recovery. The original mistaken summary and correction remain archived. No command or timing observation is rerun.

Focused race suites pass on the standalone upstream patch and in both controlled engine modes. All 35 existing Go library and development checks pass with the candidate enabled. All six retained Rust histories reuse every compiler action before engine replacement, on their first calls after replacement, and after the full comparison: 130/130, 1,026/1,026 and 6/6, twice each. The old engine exits gracefully in 244.14 seconds while persisting its cache; that is not candidate overhead or a shutdown comparison. No volume is reset and no engine is forcibly terminated.

The comparison engine is `c058d999e0efbdb93aa6c2bea08c0299331397a391f37e11b40fcdb6cd545930`. Diagnostic markers and the mode switch are separate from the standalone production patch. The [archive](experiments/lazy-schema-candidates/) preserves exact sources, the failing regression, useful checks, all component and complete-command observations, both profiler outcomes and retained-cache checks. The [previous schema-buffer experiment](NATIVE_DANG_SCHEMA_READ_BUFFERS.md) is separate; its timings are not combined with this cohort.
