# Reduce allocations in Dang collection callbacks

## Current getter-preserving comparison

Retesting the existing callback-caller prototype on the current stack improves complete test-edited listing **10.01 → 9.53 seconds median** and ordinary-source listing **6.75 → 6.13 seconds**, faster in all eight balanced pairs. The median paired savings are 0.59 and 0.61 seconds respectively. All 24 timing commands return correct ordered names and identical full rows, and exit successfully. This is a useful interpreter candidate; three seconds remains unfinished.

| Complete-command measure | Allocate caller per callback | Reuse the empty caller |
| --- | ---: | ---: |
| Test-file edit | 10.01 s | 9.53 s |
| Ordinary-source edit | 6.75 s | 6.13 s |
| Test-file edit, engine CPU | 51.81 CPU-s | 49.51 CPU-s |
| Ordinary-source edit, engine CPU | 30.27 CPU-s | 26.85 CPU-s |
| Test-file edit, allocated bytes | 11.07 GB | 10.01 GB |
| Ordinary-source edit, allocated bytes | 6.29 GB | 5.19 GB |

Both arms use engine `3d1c4dee…`, CLI `97f7d82d…`, Go module `de633b12ed2aa02e42adb698a23fcecc13faf36d` and real dagger/dagger `ff0b029a4d270a651b9a8c7286babc79089066e4`. Only callback-caller reuse changes. Prepared-schema reuse is common to both arms; parallel client admission and shared receiver decoding stay disabled. Every invocation starts a fresh CLI and makes a real source edit on the warm engine. Test-edit commands also change a test-file comment. Both arms finish test addition and removal before four measured pairs per workload. Telemetry, ordinary GC, output, final flushing and cleanup are included, with no concurrent profiler or heavy work during timing. These gains are not additive with earlier cohorts.

The synthetic caller carries no `self`. Concrete Dang `FunctionValue.Call` only reads that property from the caller and creates fresh locals and arguments from its own closure. The callback body never receives the synthetic caller as its execution scope. Sharing this empty caller therefore removes allocation without sharing invocation state. Other `Callable` implementations retain a fresh caller because their Go implementation can mutate it. No user values, clients, resources or function results are cached, and no new production lock is introduced.

Lossless captures retain **804 evaluations, 1,494 SDK requests and all 800 getter executions** after test edits, with one test discovery executed and 799 hits. Ordinary-source captures retain **three evaluations and 572 SDK requests**, with all 800 getters and discoveries hitting. CPU samples directly below `callFunc` attribute **1.99 CPU-s** to caller type creation and **0.36 CPU-s** to caller object creation in the control's shared discovery; neither allocation path has samples in the candidate. Callback-body samples remain 12.24 and 12.40 CPU-s. These diagnostic CPU totals are separate from latency measurements, and the profile command durations are not another timing comparison.

The standalone patch applies to pristine upstream interpreter snapshot `da1bed304cb80f8a2f0714f1747e7f64e03297a3` and passes its full race suite. The exact development interpreter and native SDK full race suites also pass with the candidate enabled. Focused tests cover concurrent arguments, captured `self` and custom callable mutation. An intentionally unsafe variant that shares the caller with every callable fails the custom-callable test under the race detector. Formatting and final patch applicability checks pass.

Nine Go checks and 28 Rust/native-cache cases have their expected outcomes, including selected failures, excluded invalid crates, edits, restored versions and actual public-API test execution. Native Rust queries recover **2/2 compilation actions** in both modes. These are correctness checks, not a new Rust latency or transferred-cache measurement. All four retained engine binaries and volumes remain unchanged; all diagnostic switches are restored and no client remains active. Cold performance is unmeasured. No PR is opened.

[Standalone patch](experiments/go-runtime-preparation-current/callback-standalone.patch), [review description](PR_DANG_CALLBACK_CALLER.md), [every attempt, exact sources, checks and profiles](experiments/go-runtime-preparation-current/).

## Earlier comparison on the older stack

Two alternating before/after orders of the full Go listing measure a median **83.77 → 82.22 seconds**. All commands succeed and return the same 4,398 rows. The change removes about 1.25 GB of cumulative allocation per command, but does not resolve the listing bottleneck. It remains an opt-in experiment, disabled after measurement; no PR is opened.

`callFunc` creates a dummy object and type for every callback, including nine empty maps. Concrete Dang `FunctionValue.Call` only reads that caller's `self`; locals and arguments are allocated separately from the function's closure. The prototype shares the empty caller only for that concrete implementation. Other `Callable` implementations keep fresh callers because they can mutate them. There is no new production lock or cache of user values.

The focused race checks cover concurrent arguments, captured self, mutable custom callables, and the existing block/return/continue/self/closure cases. Real Go module ownership and test-collection checks pass with fresh inputs. A graceful engine replacement preserves all six recorded native Rust action histories. The initial captured-self test fails identically on the control; its corrected explicit-self fixture passes. Both observations are retained.

| Order | Original caller | Reused caller |
| --- | ---: | ---: |
| Before, after | 83.25 s | 82.23 s |
| After, before | 84.29 s | 82.20 s |
| Median allocated bytes | 43.38 GB | 42.14 GB |
| Median engine CPU | 263.40 s | 258.43 s |

These are warm-engine commands with a new CLI and a fresh Go source comment every time, against dagger/dagger `ff0b029a` and the same Go module `b5dd9434`. Telemetry and normal GC remain enabled. Both arms use declaration reuse, telemetry metadata batching, the selected attribute decoder and snapshot seeds. Flush coalescing and metadata read-ahead remain off. No compiler/test workloads run during listing. This is a comparison on the existing experimental engine, not stock upstream Dagger.

The callback-only benchmark measures 2,230 → 1,391.5 ns, 2,648 → 1,464 bytes and 30 → 17 allocations. Its larger relative gain is not the complete-command gain. Two full-command pairs do not establish a stable percentage improvement.

The previous wcprof capture also identifies a serial package-discovery chain: `Go.packages` takes 42.51 seconds, including 80 `GomodGoMod.ownFiles` calls. The next isolated Go-module experiment evaluates independent per-module discovery through Dang's existing ordered parallel selection, then concatenates the results in source order. It retains the collection API and test granularity.

[Source, race logs, complete measurements, engine identity and native-cache retention evidence](experiments/dang-callback-caller/).
