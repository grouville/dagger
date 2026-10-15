# Retain the selected Rustdoc executable

Profiling the 102-crate test command identifies 4.6 s in the test batch after compilation. The captured plan contains 203 compiler actions and 203 test commands. Its compiler already uses the selected toolchain's absolute `rustc` path, but the recorder stores the documentation program as bare `rustdoc`. Replaying that name goes through Rustup's toolchain selector for each of the 101 documentation commands. Rustup documents these wrappers as [proxies](https://rust-lang.github.io/rustup/concepts/proxies.html).

The [Rust-module fix, 3ee3187](https://github.com/grouville/dagger-rust/commit/3ee3187), resolves the selected documentation program once during capture. It preserves custom image-environment programs and checks that the selected file exists in the pinned image. A proxy is recognized by file identity, including hardlinks and symlinks; Rustup's `which` command supplies the selected binary. There is no hardcoded toolchain-directory layout.

The plan retains that path as test metadata. Replay substitutes it in an independent command list, preserving arguments, environment, working directories, ordering, filesystem effects and failure handling. The path is excluded from compiler recipe and incremental-seed identities; test-execution inputs still include it. Compiler outputs and incremental state remain native Dagger objects.

Automatic older test plans refresh once to record the program. Explicit legacy plans remain accepted. Cargo configuration that overrides Rustdoc is now rejected rather than silently replacing the recording hook; image-environment overrides remain supported. Capture adds one resolver execution and an image-file check. Cold-capture performance is not established by the edited-build measurements below.

## Isolate the process-launch cost

The startup probe compares the proxy and direct binaries in the actual pinned Rust 1.77.2 image, using the recorded Cargo environment and working directory. Forty rotating samples per variant verify identical version output:

| Program | Through PATH | Selected binary |
| --- | ---: | ---: |
| `rustc --version` | 34.18 ms | 8.82 ms |
| `rustdoc --version` | 34.97 ms | 9.51 ms |

Only Rustdoc needs this correction: the captured compiler already has its direct path. The [standalone probe](experiments/rustdoc-startup/main.go) uses the standard library. Build it with `go build -o /tmp/rustdoc-startup ./hack/rust-cache/experiments/rustdoc-startup`, then run that executable inside the pinned Rust image. Its optional first argument is a JSON file containing the captured `cwd` and `env`; matching source mounts must exist for that working directory.

A second controlled experiment executes the actual 203 test commands repeatedly inside one container with the same source and compiled outputs. Only the Rustdoc executable changes. Across four alternating pairs, median batch time falls from **4.528 s to 1.892 s**, with **2.626 s median paired saving** and every pair faster. All 203 commands run in every trial. This is a test-execution measurement, not a complete CLI command or a compiler-cache-hit timing.

Separately inspecting the normal module execution confirms **102 test binaries and 101 documentation commands** in its output. Fresh-edit wcprof captures retain three executions in both variants. The compiler worker takes **252 versus 258 ms**; the test batch takes **4.640 versus 2.048 s**. The helper includes that worker: its 718/744 ms workloads must not be added to the worker durations.

## Complete edited commands

Both variants use the same engine and Rust version. Toolchains, module helpers and compiler histories are warm; every measured command changes source. Invocation order rotates, telemetry stays enabled through the local receiver, and wcprof is disabled during timing. Cargo uses an independent source tree and target directory.

| Small collection, eight pairs per series | Original | Selected Rustdoc | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Existing measurement wrapper | 1.065 s | 0.983 s | 0.465 s | 6/8 |
| CLI invoked directly | 1.026 s | 0.962 s | 0.473 s | 6/8 |

Median paired savings are **58.3 and 55.7 ms**. The direct series removes the additional Python launcher process from the timed Dagger command; the driver applies the same environment and telemetry settings before timing. It is a separate measurement period, not a measurement of the launcher's exact overhead. The first series reaches 5.6% CPU/4.2% I/O pressure; the direct series reaches 5.5%/18.6%, with at most 0.6% memory pressure.

The direct series has **0.490 s median paired Dagger–Cargo gap**, reaching the target for this fixture's median. Only five of eight pairs are within Cargo +0.5 s, so this is a narrow result, not an established margin or a completed general Rust performance target.

The 102-crate complete-command comparison has four pairs per edit scenario:

| Edit | Original | Selected Rustdoc | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Leaf | 9.298 s | 3.411 s | 2.978 s | 4/4 |
| Shared library | 12.522 s | 8.766 s | 8.525 s | 4/4 |

These larger medians are noisy: I/O pressure reaches **64%**, Cargo varies by more than a factor of two, and the control has 18.7/39.0 s outliers. All samples are retained. This series supports the direction of the change, but does not establish those median differences as its magnitude or prove the large workspace meets the target. The same-container batch and wcprof captures establish the specific reduction in test-execution cost much more clearly. All 20 preparation/follow-up compiler probes report **203/203 hits**.

## Correctness and remaining work

Focused model, replay, worker, recorder and compiler-wrapper tests pass with the race detector. Added cases cover direct/custom executables, Rustup symlinks and hardlinks, plan refresh, legacy plans, invalid tool paths, retained command inputs and compiler-seed compatibility. Actual module checks pass for single/group package selection, runtime-data failures, documentation-test failures, invalid Rust, excluded-package behavior, restoration and unknown-key rejection. The final capture protocol also passes a new capture and subsequent **6/6 compiler reuse** in the small fixture, with all six test commands present.

After the Rustdoc change, the leaf profile still shows about **486 ms of helper workload outside its 258 ms compiler worker**. Source preparation, package hashing, state copies and nested API work inside that interval need further separation. The earlier generic-check profiles also retain source-mount and schema-file-opening costs; see [NATIVE_PERF_PROFILE.md](NATIVE_PERF_PROFILE.md).

The Rust branch is pushed to Guillaume's fork; no PR is open. All numeric timing samples, including outliers, are tracked in [measurements.json](experiments/rustdoc-startup/measurements.json). Raw logs, executed test output, profiles and local harnesses remain under `/tmp/rust-cache-sipsma-review`: `native-rustdoc-{small-paired,small-direct-cli,many-paired,many-profile,correctness}`, `native-rustdoc-isolated-test-batch.log`, `native-rustdoc-final-*`, `native-rustdoc-many-executed.json.tests.log`, and `rust-process-probe-captured-env.log`.
