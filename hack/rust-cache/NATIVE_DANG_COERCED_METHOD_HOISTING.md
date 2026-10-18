# Recognize typed methods after type checking

This small Dang interpreter change improves complete Go test listing after a test-file edit **14.31 → 12.71 seconds**, faster in all four balanced pairs. Engine CPU falls **78.97 → 68.79 CPU-seconds** and cumulative allocation **17.40 → 16.62 GB**. Ordinary-source edits show no gain: **6.75 → 6.90 seconds**, faster in one pair. Three seconds remains unachieved.

The Go module is unchanged. The fix belongs in Dang, which the development engine uses to evaluate this module. It introduces no cache, new lock, public API or cache-identity change. A clean current upstream snapshot reproduces the unnecessary initialization, and its full interpreter race suite passes with only this fix and the two added tests.

## What the profile uncovered

Each of the 800 package getters receives the collection's stored state, including its 800 package paths and 80 module owners. A diagnostic capture measures **79,611,200 parent JSON bytes**, **1,872,800 converted values** and **64,800 reconstructed nested objects** across those getters. A second capture after initialization confirms the same work. Repeated receiver preparation is real, but its volume alone does not establish the latency saving from sharing it.

CPU profiling identifies a narrower problem inside that preparation. Type checking wraps annotated method declarations in `Coerce`, which preserves the declared type when the value is evaluated. `classifyForms` recognizes only a directly held `FunDecl`. After wrapping, methods are classified as computed variables instead of functions. Every reconstructed object consequently installs deferred variable initializers for its methods and immediately forces them, allocating initializer state and taking its synchronization path.

The fix looks through `Coerce` only to identify the declaration's phase. Evaluation still receives the original node, including its conversion wrapper. Methods keep their current receiver and closure; defaults still run through the normal call path. Computed variables retain their initialization behavior. There is no shared mutable receiver or retained client.

## Complete-command comparison

Command: `dagger check --module go --check test --list --all`, on real dagger/dagger source `ff0b029a4d270a651b9a8c7286babc79089066e4`.

| Real edit | Fix off | Fix on | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 14.31 s | 12.71 s | 4 / 4 |
| Ordinary Go source | 6.75 s | 6.90 s | 1 / 4 |

The median paired saving for test edits is **1.58 seconds**. CPU and allocation improve in every test-edit pair. Ordinary-source CPU is **30.21 → 30.53 CPU-seconds**, allocation **6.30 → 6.28 GB**. Its median paired latency change is a **0.15-second slowdown**. This cohort does not establish a general latency improvement or a universal absence of regression.

Each workload has four balanced measured pairs after one excluded initialization pair. Every arm starts a fresh CLI on the same warm engine and edits real Go source. The test-edit cohort also edits a real test file each time. Initializations add a test and return 4,399 rows; all measured commands return identical ordered 4,398 rows and full row text. All 20 commands exit successfully. Full exit, session cleanup and final log flush are included. Telemetry and ordinary GC remain enabled, with no profiler, concurrent build or test during timings. Sources, configuration and switches are restored.

Both arms use the same binary and Go module `09518aac0858390722e71c82a719c2f6e131e611`. Getter content identity, typed artifact metadata, response projection and other selected development optimizations are common. Receiver counters and the rejected context optimization are disabled for timings. These are measurements on the development stack, not a stock-main Dagger comparison. Test-edit host CPU pressure peaks at 21.5%; ordinary-source pressure peaks at 17.6%. Raw pressure data and every attempt are preserved.

## Scaling and profiles

A separate fixture models complete receiver preparation for 16, 64, 256 and 800 packages, one owner per ten packages and 32 typed methods per owner. At 800 packages, medians across three samples improve **2.50 → 1.68 seconds**, allocation **2.33 → 1.78 GB**, and allocation count **21.15 → 12.38 million**. This component benchmark excludes engine admission, source discovery and result encoding; its saving is not added to the complete-command saving. The earlier simple-owner fixture takes about 0.23 seconds at 800 packages and does not model method-heavy hydration.

Separate before/after wcprof and CPU captures return correct rows, successful exits, no dropped events and no open operations. They contain 270,634 and 270,156 events. Both retain **804 module evaluations, 2,293 nested SDK requests, 800 package getter executions, one test discovery execution and 799 discovery hits**.

Sampled CPU under parent conversion falls **13.52 → 7.92 CPU-seconds**; object-body evaluation falls **12.65 → 7.32 CPU-seconds**. These are overlapping call stacks, not additive savings. CPU windows can extend beyond command exit. Context lookup remains expensive; this fix does not eliminate it. The candidate's 12.75-second profiled main-query critical path still includes **2.88 seconds of session lifecycle lock waits**, 1.99 seconds of function evaluation and 1.40 seconds of result encoding. Generic shared preparation and admission remain investigation targets.

The candidate still samples 8.60 CPU-seconds under `GetEvalContext`. Inspection shows `EvalNode` reading and republishing the same error-reporting state on every successful node evaluation. A next experiment can test reading it only when an error needs source context, while preserving the explicit context API's behavior. The rejected lookup-wrapper experiment did not test this change. Its exact source is preserved; an end-to-end saving remains unproven.

## Standalone correctness and review

The upstream snapshot is [`vito/dang@da1bed304cb80f8a2f0714f1747e7f64e03297a3`](https://github.com/vito/dang/tree/da1bed304cb80f8a2f0714f1747e7f64e03297a3). Its classifier is byte-identical to the measured control's source. The new regression uses a real parsed and inferred typed method, observes that it is installed without a variable initializer, and checks its receiver and default argument. It fails on the clean upstream snapshot and passes with the fix. A second test checks a computed initializer calling a later declared method. The full upstream `./pkg/dang` race suite passes. Comparing the extracted tree with its original archive verifies that `pkg/dang/block.go` is the only changed production file.

The development overlay's focused tests and full interpreter race suite also pass. An initial broad run included the previous experiment's intentional failing disabled control; that failure is retained, and the final full run removes that virtual test from the overlay. Both sides of the new runtime switch are checked. Seven Go/library checks pass, covering package facts, owned files, discovery, lookup, module-boundary rebinding and test collections, including generated binaries. No broader remaining Go-module suite or Rust performance cohort is run for this change.

The phase-order risk is bounded: recognizing a wrapped function moves its declaration into the existing function phase before computed variables. Function creation does not execute its body. The original conversion node still runs, and existing variable initialization, error handling and fresh receiver behavior remain covered by the interpreter suite. No concurrency or cache ownership mechanism is added.

[Evidence and minimal source patch](experiments/dang-coerced-method-hoisting/) include the diagnostic that found the issue, exact sources, standalone upstream archive, regression tests, all timing attempts, profiles and checks. [Prepared review description](PR_DANG_COERCED_METHOD_HOISTING.md) reports the benefit and the slower ordinary-source cohort. No PR is opened.

The current isolated engine SHA-256 is `579ef167f1137d00e6c85d6332db8e0b2f0969b8f344ae182f51806c72b04a53`; CLI is `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`. The engine keeps its existing volume. The candidate and diagnostics are restored to disabled. The original retained Rust-cache engine and volume are untouched.
