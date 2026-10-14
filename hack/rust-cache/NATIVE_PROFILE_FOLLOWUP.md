# Native Rust module: remaining work

A 30-second CPU profile during 32 fresh app edits records 38.59 CPU seconds
across concurrent engine work. Every command uses the real Rust module and
reuses three unchanged compiler actions. Median command time is 865 ms.

The profile includes 2.30 CPU seconds in Dang parsing, 3.63 in protobuf JSON
decoding, and 10.35 in background garbage collection. Protobuf decoding is
split between span conversion for Cloud forwarding and log conversion for
streaming clients. CPU totals overlap their callers, and background CPU is
not an additive command-latency breakdown.

An isolated diagnostic module reports these warm compilation phases:

| Phase | Observed range |
| --- | ---: |
| Read plan | 2.6–3.1 ms |
| Validate image | 0.9–1.0 ms |
| Resolve native input handles | 7.3–8.8 ms |
| Resolve compiler helper | 3.6–4.3 ms |
| Construct native graph | 13.4–14.8 ms |
| Evaluate/execute graph | 321–341 ms |
| Materialize returned native fields | 8.9–9.6 ms |

The graph-construction cost is small in this four-crate fixture. The larger
execution interval includes filesystem/container preparation and the compiler;
it is not proof of slower rustc. The diagnostic logs arrive asynchronously,
so a collector file read immediately after a command can include late records
from the prior command; use trace identity before aggregating individual runs.

## Nested execution and container startup

Rebuilding the wcprof report tool from the profile checkout restores the
nested-client links that the old report binary omitted. In
`module-native-profile-direct-object/edited-1.wcprof.ndjson`, the Go helper's
394.2 ms workload includes its nested API calls and compiler execution; its
own time is only 29.1 ms. The compiler worker's workload is 184.6 ms.

The Rust `nativeCheck` call's critical path is 611.9 ms, including:

| Work | Time on the call's critical path |
| --- | ---: |
| Compiler worker and Go helper's own work | 213.7 ms |
| Rust module's own work | 107.0 ms |
| Creating the two containers in runc | 89.8 ms |
| Nested query handling | 54.0 ms |
| Starting Dagger init | 25.9 ms |
| Spawning the commands | 11.7 ms |

These are one profile's exclusive contributions, not medians or a complete
command breakdown. Source imports and module loading also happen outside
this call. Runtime startup excludes the separately recorded root filesystem,
network, mount preparation and command-spawn phases. The images and engine
caches are warm; the container processes are fresh.

Sipsma's [runtime change #14607](https://github.com/dagger/dagger/pull/14607)
merged after this capture. It replaces runc with crun and reports startup
falling from 31–35 ms to 7–8 ms per exec on arm64. The measured Rust engine
still uses runc. The already batched compiler worker avoids starting a
separate container for each crate.

### Runtime comparison through the native module

An isolated engine branch applies #14607 to the existing benchmark control,
with the same init, SDK, compiler and private profiling instrumentation.
Both engines start with separate fresh state, then prepare the same module
and native cache history. The runtime experiment uses the official static
`crun-1.30.1-linux-amd64-disable-systemd` release binary, verified against its
published SHA-256 (`e7b059390e27d0f283e1debbe89d9c5847870f3d8325f31ccd954533fdd6ea78`).
It reports seccomp and eBPF support. This tests the runtime change; it does
not reproduce engine-dev's musl build of crun.

The first five-pair command series has up to 51% I/O pressure and variable
Cargo controls. Its medians, 1.080 s versus 0.868 s, cannot establish a
212 ms runtime benefit. Preserve it as the initial noisy series.

Two subsequent profiled pairs show the two runtime starts falling from
75.5 and 102.8 ms in runc to 21.8 and 21.4 ms in crun. Both starts lie on
the native-check critical path. Each compiler worker takes 180–190 ms;
the Go helper's workload includes the worker and must not be added again.
All four captures have no dropped events and reuse three of four actions.

A final unprofiled series reuses those prepared states and alternates five
pairs of fresh host edits. Every variant receives a different edit, and
Cargo runs first and second in alternating pairs. Telemetry stays enabled
through the local receiver.

| Complete edited command | runc | crun |
| --- | ---: | ---: |
| Native Rust module, median | 816.5 ms | 775.0 ms |
| Module range | 801.9–829.9 ms | 760.8–834.1 ms |
| Native Cargo check, median | 185.7 ms | 184.7 ms |

The median reduction is 41.5 ms, about 5.1%; four of five pairs improve.
All ten compilations reuse three unchanged actions. Maximum host I/O pressure
is 2.2%, and CPU pressure is 8.3%. The small series and overlapping ranges
limit the precision of the command-level estimate. The profiled startup
reduction is much clearer than the complete-command reduction.

Processes remain fresh and isolated. Compiler results and incremental state
remain native Dagger snapshots. Runtime compatibility and wcprof timestamp
tests pass. Cold preparation and invalid-source failure without publishing
cache metadata pass on both engines. This experiment introduces no new
upstream PR: the runtime change is already merged.

The remaining Go helper command-spawn phase is 11–15 ms in these captures.
[Nonblocking nested-session setup #14608](https://github.com/dagger/dagger/pull/14608)
is another relevant change; it is not included in this runtime comparison.
The compiler worker already disables nesting. Reusing a long-lived module
or compiler process would need explicit handling of per-call state,
filesystem isolation and cache output publication; no such change is made
by this experiment.

Branch: [`experiment/rust-cache-crun`](https://github.com/grouville/dagger/tree/experiment/rust-cache-crun).
Artifacts under `/tmp/rust-cache-sipsma-review`: `module-native-runtime-paired`
(noisy initial series), `module-native-runtime-profile`, and
`module-native-runtime-confirmation`. The local reproduction harness is
`measure_runtime_pairs.py`; the final series uses `--runs 5 --initial-states
/tmp/rust-cache-sipsma-review/module-native-runtime-profile`.

The input-ID experiment also removes six requests in each of two profiled
edited commands: 81 to 75 `session.serveQuery` calls and 63 to 57 `Query.node`
calls, with no dropped events. It retains IDs already supplied when decoding
Directory inputs. Its noisy command timings do not establish a speedup;
the hand-edited generated binding remains an isolated prototype, not a
finished generator change.

## Nonblocking session-helper comparison

The next isolated branch adds the merged session-startup change #14608 and
its helper cleanup follow-up #14655 to the crun control. Both engines have
fresh state and matching init/session helper binaries. Focused race tests
pass in `cmd/init`, `engine/engineutil` and `engine/server`, covering startup,
failure, cancellation, fd plumbing, registration order and teardown. The
init import-check subprocess needs `GOFLAGS=-buildvcs=false` in this local
worktree, as the engine build does; its initial failure was VCS stamping.

The first two profiled pairs have heavy disk contention. They establish
the phase change, not a command speedup: the Go helper's spawn falls from
11–13 ms to 1–2 ms, but its first API request waits for session attachables.
One capture records a 13.27 ms wait there. The worker already disables
Dagger nesting and has no corresponding helper startup to overlap.

Five subsequent unprofiled pairs give medians of 728.9 ms before and 723.8 ms
after; Cargo medians are 172.1 and 175.2 ms. Module ranges overlap
(712–734 ms versus 703–795 ms). Maximum I/O pressure is 33.4%, so the 5.1 ms
difference does not establish a whole-command benefit. All ten commands
reuse three of four actions, and both variants pass cold compilation and
invalid-source failure without publishing cache metadata.

Keep this result separate from crun's startup improvement. The shorter
spawn phase mostly moves necessary readiness work to the module's first
API call; subsequent optimization should target work that remains on the
critical path. Artifacts: `module-native-nested-profile`,
`module-native-nested-confirmation`, and `nested-start-tests-configured.log`
under `/tmp/rust-cache-sipsma-review`. Engine branch:
[`experiment/rust-cache-nested-nonblocking`](https://github.com/grouville/dagger/tree/experiment/rust-cache-nested-nonblocking).

## Telemetry metadata experiment

Span rows repeat their resource and instrumentation-scope JSON. The experiment
decodes each distinct value once per batch and gives the read-only span wrappers
immutable decoded metadata. It adds no shared global cache or new lock, keeps
span records separate, and keeps the current exported payload semantics.

The focused test compares exported protobuf batches to the original converter,
including distinct resources/scopes and a changed subsequent batch. It passes
under the race detector. A 512-span microbenchmark decreases from 4.38 to
2.43 ms median, 1.73 to 1.21 MB, and 39,006 to 24,117 allocations.
The server's focused forwarding-order, retry and teardown-drain tests also
pass under the race detector. The isolated implementation is retained on
[`experiment/telemetry-batch-decode`](https://github.com/grouville/dagger/tree/experiment/telemetry-batch-decode).

The first command-level comparison had 31–69% I/O pressure in several Cargo
controls and up to 48% in Dagger samples. Its apparent 408 ms median difference
cannot establish a speedup. The control also had many more prior sessions than
the experiment engine. Preserve those samples rather than using that result.

A second five-pair series prepares the same native module on a fresh control
engine and the separate experiment engine. Each variant starts without retained
history, fills it with four edits, checks invalid-source failure without cache
publication, and advances the history before timing. Every timed source edit
is unique. Telemetry remains enabled through the local receiver, and wcprof
is disabled during timing.

| Complete edited command, median | Control | Batch decoding |
| --- | ---: | ---: |
| Native Rust module | 776.9 ms | 773.7 ms |
| Native Cargo check | 174.0 ms | 180.0 ms |
| Module range | 760–837 ms | 758–858 ms |

All ten compilations reuse three of four actions. Maximum measured I/O pressure
is 9%. The 3.1 ms median difference and overlapping samples do not establish a
command-latency improvement, despite the clear converter microbenchmark gain.
Keep this as an experiment; it is not selected by the normal performance
implementation and no PR is warranted from this series alone.

The [many-crate module comparison](NATIVE_SCALE_OCT13.md) now measures both
leaf and shared edits and identifies compiler-state copies and query handling
as concrete next targets. Automatic
plan/cache discovery and the ordinary check workflow remain required. The warm
fresh-control module still exceeds Cargo by about 603 ms, above the 500 ms
target. Engine age and retained heap also deserve a matched lifecycle test;
the old-engine versus fresh-engine comparison alone does not diagnose a leak.

Artifacts:

- `/tmp/rust-cache-sipsma-review/module-native-cpu`
- `/tmp/rust-cache-sipsma-review/module-native-phase-*.log`
- `/tmp/rust-cache-sipsma-review/telemetry-batch-bench.log`
- `/tmp/rust-cache-sipsma-review/module-native-telemetry-batch-paired-v3`
- `/tmp/rust-cache-sipsma-review/module-native-telemetry-batch-fresh`
