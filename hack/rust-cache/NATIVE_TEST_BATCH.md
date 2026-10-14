# Run captured Cargo tests in one execution

The real Rust module now has an isolated branch that runs its captured test commands sequentially inside one fresh Dagger execution. It preserves each command's cwd, arguments and environment, forwards output, stops on failure, and retains filesystem effects for later commands. Compilation still has separate per-action results and native incremental snapshots. Telemetry remains enabled.

The implementation is [commit 5c5ed76](https://github.com/grouville/dagger-rust/commit/5c5ed76), based on the binary-publication fix `f136cb4`. The previous implementation starts one container for each captured test command. The new runner replaces that chain with one execution containing the same ordered command list. It introduces no compiler CacheVolume.

## Edited full commands

Both modules use the same engine, CLI and Rust 1.77.2. Independent fixtures and cache histories receive matching fresh source edits. Cargo uses a separate target directory. Invocation order rotates, wcprof is disabled during timing, and every follow-up native compiler-hit probe passes. These are warm edited builds; cold toolchain and helper preparation are excluded.

| Small-workspace series | Original | Batched | Cargo | Batched faster |
| --- | ---: | ---: | ---: | ---: |
| First, 10 pairs | 0.968 s | 0.882 s | 0.362 s | 7/10 |
| Confirmation, 10 pairs | 0.938 s | 0.871 s | 0.351 s | 9/10 |

Median paired savings are 77.3 and 77.2 ms. The confirmation has at most 4.9% CPU and 4.6% I/O pressure. Its Dagger–Cargo median gap is 0.520 s, still slightly above the target.

The larger fixture has 102 packages, 203 compiler actions and 203 captured test commands. Six rotated pairs per scenario give:

| Edit in full workspace tests | Original | Batched | Cargo | Batched faster |
| --- | ---: | ---: | ---: | ---: |
| Leaf package | 34.39 s | 7.89 s | 2.32 s | 6/6 |
| Shared dependency | 46.04 s | 13.91 s | 9.41 s | 6/6 |

Median paired savings are 23.70 and 29.94 s. Keep every sample: host CPU/I/O pressure reaches 49.7%/56.3%, and candidate times vary substantially. The consistent large reduction supports removing the repeated executions; the exact speedup and remaining gap need lower-contention confirmation. The comparisons include 24 follow-up 203/203 compiler-hit probes and four preparation probes.

## What the profiles establish

Six small-workspace wcprof captures show seven executions becoming three. Three larger captures show 205 becoming three. All have no dropped events or open operations.

In the larger leaf capture, runtime starts total 702 ms before and 10 ms after; mount preparation totals 508 and 4 ms; output publication totals 5,456 and 5 ms. These are summed phase times, not an additive command breakdown. The original path also has expensive context lookups during snapshot lease attachment: a separate 45-second CPU recording attributes 11.97 of 38.29 CPU seconds to `context.value`, mostly through namespace/header lookup in `AttachLease`. That engine optimization is being reproduced separately.

The batched leaf still spends 5.18 s running tests and 0.25 s in its compiler worker. Its helper's 0.68 s includes that worker and must not be added again. The shared-edit CPU recording also contains substantial background cache pruning and Go garbage collection; it includes time after the command and does not establish that half the command waits on GC. Further profiling must separate test-process work from helper preparation and cleanup.

## Correctness and limits

Focused worker/replay/model/compiler-entrypoint checks pass with the race detector. Tests cover captured environment isolation, literal arguments, cwd, shared filesystem effects, failure stopping later commands and process cancellation. Actual module checks cover unit, integration, custom-harness and documentation tests; a custom harness writes a file consumed by a later doctest. Changed runtime data, invalid Rust and doctest failures surface, and restoration recovers native compiler hits.

A real integration test launches the normal binary through `CARGO_BIN_EXE_added`; changed output fails and restoration recovers 8/8 compiler results. Canceling an actual batched test command terminates its sleeping descendant in the owned engine; the observed cleanup takes 0.15 s. No telemetry is disabled. Individual test commands now share an execution span and have command labels in their output.

The branch is pushed to Guillaume's fork. No upstream PR is opened. General Cargo support, remote automatic cache discovery and the full performance target remain unfinished. Package collection discovery and selected-package execution are the next integration scope; they must preserve batching and be compared with matching Cargo selections.

Raw artifacts are under `/tmp/rust-cache-sipsma-review`: `native-test-execution-batch-paired`, `native-test-execution-batch-confirmation`, `native-test-execution-batch-profile`, `native-test-execution-batch-many`, `native-test-execution-batch-many-profile`, `native-test-execution-batch-correctness`, and `native-test-execution-batch-cancel`.
