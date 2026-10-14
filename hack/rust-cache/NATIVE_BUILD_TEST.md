# Native Rust builds and test execution

The Rust module prototype now uses native compiler snapshots through the normal
`rust:test` and `rust:build` entrypoints, in addition to `rust:check`. Compiler
outputs and incremental state remain immutable Dagger directories. Enabling
`nativeCache` still requires the experimental engine; this is a fork checkpoint,
not a released official-module capability.

## Preserve Cargo behavior

Capture records Cargo's actual unit, integration, custom harness and documentation
test commands. Replay preserves their arguments, environment, working directories
and execution order. Every test sees the whole workspace, so data files outside
crate roots remain runtime inputs. Files written by an earlier test are visible
to later commands. Compiler state is published before test execution, preserving
successful compilation when a test fails.

Build capture maps Cargo's final workspace artifact names to their native compiler
outputs. The generator publishes binaries and libraries under `target/dagger` and
removes obsolete generated files. Generated artifacts disable rustc incremental
compilation to preserve byte reproducibility across engines; `nativeBuild` retains
incremental state for development builds. These modes use separate cache hints.
Reconciling fast incremental builds with normal reproducible generation remains
unfinished.

## Remove per-variable graph construction

The performance comparison freezes the initial module implementation and changes
only how the captured environment reaches each test process. The first native
test implementation set each captured environment variable with
a separate Dagger operation. Preparing five test commands created 158 such calls
on the compiler helper's critical path. Passing the captured environment through
one `env -i` invocation per command removes those calls while preserving fresh
processes and test execution order. Argument arrays are passed directly, without
shell interpolation. Tracing state from the capture session is excluded.

Eight paired rounds use unique source edits through ordinary `dagger check
rust:test`, with separate source trees, cache keys and Cargo targets. The pinned
toolchain is Rust 1.77.2. Images, tools and compiler state are warm; CLI and compiler
processes are fresh. Two preparation edits precede timing. Order rotates between
the two implementations and Cargo. Telemetry remains enabled through the local
collector; wcprof is disabled for timing and captured separately afterward.

| Edited complete test command, median | Time |
| --- | ---: |
| Individual environment operations | 1.236 s |
| One captured environment per command | 1.063 s |
| Native Cargo incremental tests | 0.345 s |

All eight pairs improve, by 90–272 ms. The difference between medians is 173 ms.
Untimed probes after each command recover all five compiler actions, confirming
the normal entrypoint publishes reusable native state. CPU pressure peaks at 9.7%
for Dagger and 17.5% for one Cargo command; maximum I/O pressure is 5.3%. These
local measurements support the change but do not establish a general percentage.
The optimized command still exceeds Cargo +0.5 seconds by about 218 ms.

A second eight-pair series compares the frozen baseline with the final hardened
module, including its separate selection of test fields for nullable build
results. The medians are 1.236 s before, 1.075 s after and 0.346 s for Cargo;
all eight pairs improve by 132–255 ms. CPU pressure peaks at 4.3% for Dagger
and 0.9% for Cargo; I/O pressure stays below 2.8%. This confirms the improvement
with the final code. Its 161 ms difference leaves about 229 ms beyond the
Cargo +0.5-second target.

Both diagnostic profiles contain seven successful fresh executions with no
dropped events or unfinished operations. Summed runtime creation stays at about
25 ms. The helper's critical path falls from 556 ms to 456 ms: environment calls
and lazy evaluation accounted for 75 ms, query handling falls from 77 ms to 29 ms,
and publication falls from 24 ms to 6 ms. Compiler workload varies between these
single captures, so their phase differences are not independent latency gains.
The final confirmation also records seven fresh executions on each side, with
no dropped or unfinished operations. Runtime totals vary from 21 ms to 29 ms,
while the helper's measured critical work falls from 564 ms to 438 ms across
its field selections. These are diagnostic captures rather than phase medians.

This improvement reduces preparation before execution. It does not introduce a
persistent compiler process or a shared writable compiler cache. The earlier
[fresh process study](FRESH_PROCESS_START.md) still places runtime creation at
roughly 11 ms per warm-container start and the process fork itself at 0.7 ms.

## Correctness checks

- Focused Go packages pass under the race detector. Tests cover final artifact
  naming and workspace membership, unsafe output paths, captured test commands,
  transport environment filtering and configured target runner rejection.
- Native and ordinary test entrypoints pass unit, integration and documentation
  tests. Runtime-only file edits reuse all six compiler actions in the extended
  fixture and correctly fail execution. A doctest-only failure also surfaces;
  valid restoration passes. A custom harness writes a file consumed by a later
  doctest, proving execution order and filesystem effects.
- Native builds reuse 3/4 actions after an application edit and 4/4 on reversion.
  Normal generation publishes final filenames, removes obsolete outputs and
  restores the original hashes. Another engine reproduces identical generated
  bytes. A compilation failure leaves generated files unchanged.
- Twenty edited native test builds retain a stable pruned closure of 332 results
  and 79 snapshot references at edits 5, 10 and 20. Untimed checks after each
  prune reuse all five compiler actions. No mutual ownership pairs appear;
  eviction of the prototype hints followed by pruning releases all Rust cache
  objects. This checks graph retention, not unique physical storage or remote
  transfer size.
- A clean restart of the owned engine automatically restores test state with
  5/5 compiler hits and development build state with 4/4. Normal test and
  generation entrypoints pass before and after restart. Subsequent source edits
  reuse 2/5 test actions and 3/4 build actions, without caller-provided cache
  metadata. This verifies clean restart, not crash durability.
- Explicit transfer exports the native snapshot fields, then imports them on
  the second engine. All five test compiler results reuse; a new application
  edit reuses 2/5. Runtime-only failures surface and valid restoration passes.
  This is a correctness check, not a remote-cache transfer benchmark.

## Remaining scope

The supported subset remains locked Linux/amd64 workspaces with path dependencies,
no build scripts or procedural macros, and no extra system packages. Configured
Cargo target runners are rejected rather than bypassed. Formatting and Clippy
retain the existing Cargo backend. Registry dependencies, broader target support,
automatic discovery on remote engines, crash durability and the full edited
command performance target remain open.

Module branch: [experiment/native-build-test](https://github.com/grouville/dagger-rust/tree/experiment/native-build-test).
Engine branch: [experiment/persistent-native-cache-hints](https://github.com/grouville/dagger/tree/experiment/persistent-native-cache-hints).
Local artifacts are under `/tmp/rust-cache-sipsma-review`: `native-build-module`,
`native-test-module`, `native-test-env-paired`, `native-test-env-final-paired`, `native-test-transfer-oct14`, `native-test-hints-retention-final`,
`native-build-test-restart`, and
the corresponding verification scripts and logs.
