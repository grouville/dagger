# Interpreter context lookup: no complete-command gain

Keep this candidate disabled. A depth benchmark improves from about 1,003 ns to 5 ns, but complete Go test listing does not improve. Test-file-edited listing regresses **13.59 → 14.51 seconds**, faster in one of four pairs. Ordinary-source-edited listing is **6.70 → 6.77 seconds**, also faster in one pair. These are separate workloads on a warm engine; neither is a cold-start result or an improvement attributable to this candidate.

Both arms use the same diagnostic engine, CLI and final batch-discovery Go module. Every invocation starts a new CLI and edits real source. Test-edit invocations also edit a real test file. Four balanced measured pairs follow one excluded initialization pair for each workload. All 20 commands return the correct ordered rows and full row text, and exit successfully. Initializations add a test and return 4,399 rows; measured commands return 4,398. Measurements include command exit, session cleanup and final log flush, with telemetry, ordinary GC and no profiler. Sources, configuration and flags are restored.

| Workload | Context change off | Context change on | Engine CPU, off → on | Cumulative allocation, off → on |
| --- | ---: | ---: | ---: | ---: |
| Test-file edit | 13.59 s | 14.51 s | 77.20 → 77.02 CPU-s | 17.32 → 17.47 GB |
| Ordinary-source edit | 6.70 s | 6.77 s | 29.73 → 30.12 CPU-s | 6.30 → 6.34 GB |

## Candidate and verification

The interpreter stores evaluation and initializer state in Go contexts. Repeated private-key lookups walk nested context values. The candidate puts both values in one wrapper and flattens consecutive wrappers it owns. Unknown context wrappers remain intact. Deadlines, cancellation causes, caller values, raw private values and the linked initializer ancestry retain their behavior. No new lock, public language API or cache-identity change is introduced.

A counting-context test fails against the old implementation with 1,280 ancestor reads for ten lookups through 128 initializer layers; the candidate passes. Focused race tests cover ancestry, overrides, absent and typed-nil values, cancellation and deadlines. The full `./pkg/dang` race suite passes. The diagnostic switch also has a failing disabled control and passing enabled check. Seven focused Go/library checks pass, including ownership rebinding and generated test binaries. A broader Go-module suite is not rerun.

These checks establish the narrow change's behavior. They do not establish useful command performance. The lookup benchmark measures its intended chain shape; real execution adds other wrappers. The new CPU profiles still show substantial lookup cost. No claim of eliminating that cost is justified.

## What the profiles establish

Separate lossless wcprof and CPU captures return correct rows and successful exits, with 268,998 and 269,016 events, no dropped events and no open operations. Both arms still perform **804 Dang evaluations, 2,293 nested SDK requests and 800 package getter executions**. Test discovery executes once and hits 799 times in both arms. The profiles do not show reduced work at those boundaries.

The control's main query takes 14.35 seconds under profiling. Root package discovery occupies about 5.97 seconds; a getter on the critical path spans about 7.25 seconds while the other getters run concurrently. Across the critical path, session lifecycle lock waits account for 3.14 seconds, result encoding for 2.82 seconds and function evaluation for 2.28 seconds. These are diagnostic measurements with overlapping work across cores, not unprofiled timing gains.

Source inspection identifies the next scaling question. `ModuleFunction.Call` marshals `collectionSDKFields` on every getter invocation. The latter clones the stored collection fields, including its keys. Dang's `callDangFunction` decodes all parent fields and recursively converts their lists and objects before invoking the method. This Go collection retains all package paths and shared module owners. Repeating that conversion for every package can introduce quadratic work in package count, plus work proportional to packages × module owners. The code path is established; its byte volume, scaling and share of elapsed time still need measurement.

The next experiment should count and profile that repeated receiver preparation, then test whether immutable preparation can be shared or transported in bounded batches. Cache identities, module/schema/view scope, session resources, cancellation, mutations and per-item errors must remain correct. Reusing a live mutable receiver or its creating session is not established as safe. Faster lookup alone does not justify advancing this candidate.

## Evidence and engine state

[Evidence](experiments/dang-evaluation-context/) preserves exact sources, tests, benchmark samples, all timing attempts, both lossless captures, CPU reports and restoration records. Engine SHA-256 is `8a47fcb90387346a0c8b2e20c133af3c2968c8456d45b36f2c7e9e2dec9c45d2`; CLI is `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`; Go module is `09518aac0858390722e71c82a719c2f6e131e611`; real repository source is `ff0b029a4d270a651b9a8c7286babc79089066e4`.

The owned isolated engine `dagger-collection-content-oct18` was stopped gracefully and restarted with its existing volume to install the diagnostic binary. The original retained Rust-cache engine and volume are untouched. Both new and prior diagnostic switches are restored to disabled. No PR is opened for this rejected candidate.
