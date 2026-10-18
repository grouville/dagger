# Read node error context only when needed

Deferring source-error context lookup improves complete Go collection listing after test-file edits **12.88 → 11.51 seconds**, and after ordinary-source edits **6.67 → 5.75 seconds**. Both workloads improve in all four balanced pairs. All 20 commands return correct ordered rows and exit successfully. Three seconds remains unachieved.

This is a Dang interpreter change. The Go module is unchanged, and the preceding method-classification fix is enabled in both arms. A pristine upstream snapshot independently reproduces the unnecessary lookup; its full interpreter race suite passes with only this production change and the new tests supplied through an overlay.

## Why it helps

`EvalNode` previously fetched the current error-reporting context before every node evaluation, then passed it to `EvalNodeWithContext`, which stored the same value again when present. Most evaluations succeed. When the value is absent, a lookup may walk the caller's entire Go context chain. The previous profile sampled 8.60 CPU-seconds under this lookup.

Successful node dispatch now evaluates using the context it already received. It reads the source-error state only if an ordinary error needs wrapping. The explicit `EvalNodeWithContext` entrypoint still installs its supplied context and keeps its existing nil-argument behavior. Raised errors and control-flow sentinels bypass source wrapping as before. An evaluator returning a nil value still follows the same validation path.

The change adds no retained state, cache, lock or public API. Cancellation and caller values flow through the existing context. The type-checking wrapper and method fix are unchanged. This removes work rather than making context-value lookup faster; the earlier custom-context experiment remains rejected.

## Complete-command comparison

Command: `dagger check --module go --check test --list --all`, on real dagger/dagger source `ff0b029a4d270a651b9a8c7286babc79089066e4`.

| Real edit | Eager lookup | Deferred lookup | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 12.88 s | 11.51 s | 4 / 4 |
| Ordinary Go source | 6.67 s | 5.75 s | 4 / 4 |

Test-edit median engine CPU is **73.59 → 65.77 CPU-seconds**, and cumulative allocation **16.611 → 16.609 GB**. Ordinary-source CPU is **28.22 → 23.36 CPU-seconds**, allocation **6.32 → 6.29 GB**. CPU improves in every pair; the full command does not demonstrate a material allocation saving. Median paired latency savings are **1.33 seconds** for test edits and **0.95 seconds** for ordinary-source edits.

Each workload has four balanced measured pairs after one excluded initialization pair. Every arm starts a fresh CLI on the same warm engine and edits real Go source. The test-edit cohort also edits a real test file each time. Initializations add a test and return 4,399 rows; measured commands return identical ordered 4,398 rows and full row text. Full exit, session cleanup and final log flush are included. Telemetry and ordinary GC remain enabled, with no profiler or concurrent build/test during timings. Sources, configuration and switches are restored.

Both arms use one engine binary, CLI and Go module `09518aac0858390722e71c82a719c2f6e131e611`. Selected development optimizations, including method hoisting, getter content identity, typed artifact metadata and response projection, are common. The old context wrapper and receiver counters are disabled. These are development-stack measurements; cold-start and stock-main Dagger performance are not established. Host CPU pressure peaks at 26.5% in the test-edit cohort and 23.8% in the source-edit cohort. Raw attempts and pressure records are retained. Gains from earlier engine/cohort comparisons must not be added to these figures.

## Independent correctness and component benchmark

The upstream source is pristine [`vito/dang@da1bed304cb80f8a2f0714f1747e7f64e03297a3`](https://github.com/vito/dang/tree/da1bed304cb80f8a2f0714f1747e7f64e03297a3). The production overlay changes only `pkg/dang/eval.go`; it does not include the preceding method fix or engine experiments. A regression evaluates a real literal and observes source-context reads. It fails on the old implementation and passes after the change, with and without inherited source context.

Additional tests cover inherited source/error locations, an explicit replacement context, an explicit nil context, cancellation causes, unsupported nodes, raised errors, return/break/continue sentinels and nil-value validation. The full upstream interpreter race suite passes. The full development interpreter race suite also passes with both candidates enabled, and the runtime switch's disabled negative control fails at the intended lookup assertion. Seven Go/library checks pass, including module-boundary changes and collection test execution with generated binaries. No broader remaining Go-module suite or Rust performance cohort is run.

Four component samples per case measure successful literal dispatch. At context depth 128, absent source context improves **214.75 → 6.17 ns**; present context improves **261.10 → 6.16 ns**, with **48 → 0 bytes** allocated per operation in that present-context case. At depth zero, results are **8.72 → 6.16 ns** absent and **51.87 → 6.14 ns** present. These are component measurements, not full-command speedup ratios. Their allocation improvement does not appear materially in the real listing cohort, where source context is often absent.

The main review risk is preserving error behavior while moving the lookup later. The shared dispatcher preserves the explicit API's nil semantics and its special validation/control-flow paths. Error wrapping still uses the caller's immutable context and the original source node. The change does not defer telemetry or cleanup.

## Profiles and next target

Paired wcprof/CPU captures return correct rows and successful exits, with **270,622 / 270,136 events**, zero drops and no open operations. Both retain **804 module evaluations, 2,293 nested SDK requests, 800 getter executions, one test discovery execution and 799 discovery hits**. Sampled CPU under `GetEvalContext` falls from **8.07 CPU-seconds to no samples**. The candidate's remaining 0.07 seconds in the broader context-focused report comes from initializer ancestry tracking. CPU windows can extend beyond command exit; they are diagnostics, not additional timing pairs.

A separate candidate capture after an ordinary-source edit has **157,232 events**, no drops/open operations and correct rows. All 800 package getters and test discoveries hit, yet root discovery still executes. It performs **three Dang evaluations and 571 SDK requests**. The main query takes 6.52 seconds under profiling, of which `Go.packages` occupies about 5.85 seconds. This isolates shared discovery as the remaining ordinary-edit bottleneck.

Its CPU recording samples 10.62 CPU-seconds under interpreter evaluation. List map/filter/reduce callbacks account for substantial overlapping stacks. Source inspection finds repeated insertion and list copying in the private sorting helpers, and list-membership checks in package classification. These are investigation leads, not established latency savings. The older native-sort experiment had mixed end-to-end results; it must not be reselected without measuring the current root-discovery path. Exact module and compiled standard-library sources are preserved under `next-target-source/`.

[Evidence and minimal patch](experiments/dang-lazy-error-context/) preserve the pristine upstream archive identity, exact sources, all tests and timing attempts, three lossless captures, CPU reports and restoration records. [Prepared review description](PR_DANG_LAZY_ERROR_CONTEXT.md) is ready. No PR is opened.

The current isolated engine SHA-256 is `1ddf5411131aaeb87579f5d8dd099eae705139690f0895c4216b8571d6050060`; CLI is `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`. Its existing cache volume is preserved. Both new candidates and diagnostics are restored to disabled. The original retained Rust-cache engine and volume are untouched.
