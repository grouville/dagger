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

Next: instrument the nested execution interval and module startup, then measure
the many-crate and shared-edit cases through the actual module. Automatic
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
