# Source-sync and runtime attribution, 2026-09-10

## Context and instrumentation

The external dependency benchmark showed roughly 160-180ms between Cargo's
rounded reported duration and wcprof's combined rsync/Cargo process duration.
Before replacing the source reconciler, time rsync and Cargo independently.

`--trace-phases` enables three GNU date probes inside the existing shell action.
It keeps source reconciliation and Cargo in the same locked execution, and uses
`set -e` so errors retain their exit status. This is optional benchmark
instrumentation, not an optimized production module. Dagger CSV rows are marked
profiled and metadata records the shell probes. Unchanged-source diagnostic logs
contain timings from the cached producer; do not count those as new executions.

## Repro

Use the same pinned CLI, engine, Rust image and ripgrep revision documented in
external-dependency-upgrade-results.md. Start local otlpdump on port 43181 and
set its OTEL_EXPORTER_OTLP_ENDPOINT, explicit LOGS/METRICS endpoints and
OTEL_EXPORTER_OTLP_TRACES_LIVE=1 as in that report. Then run:

```sh
DO_NOT_TRACK=1 python3 hack/bench-rust-loop/run.py \
  --dagger /tmp/dagger-rust-cli-readiness \
  --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
  --ripgrep /tmp/dagger-rust-ripgrep-reference \
  --samples 3 --fresh-engine localhost/dagger-engine.dev \
  --dependency-upgrade --profile-dependency-upgrade --trace-phases
```

The first diagnostic omitted --fresh-engine and used
DAGGER_ENGINE=container://dagger-engine.dev with existing CLI state. The repeat
above used a new engine and fresh XDG state. These are different lifecycle
conditions, so their overall times are not a performance A/B comparison.
Both have analytics disabled, local OTel enabled, and native Cargo via docker
exec. Toolchain delivery prerequisites remain as documented in prior reports.

## Observed dependency-upgrade phases

| Duration (ms) | Existing engine/CLI state | Fresh engine/CLI state |
| --- | ---: | ---: |
| rsync phase | 56.37 | 56.11 |
| Cargo process phase | 1787.10 | 1734.92 |
| wcprof exec.processRun | 1925.62 | 1870.08 |
| exec.processRun minus timed phases | 82.15 | 79.05 |
| Whole CLI process | 2733.19 | 2343.36 |
| Before CLI root | 63.13 | 51.37 |
| After CLI root | 261.71 | 6.50 |

The earlier estimate of a 160-180ms source-sync cost was too broad: the directly
timed sync is approximately 56ms. Each phase includes timestamp-command
overhead. The remaining 79-82ms also includes unmeasured first/last probe and
shell work; it should not all be assigned to one runtime operation.

Cargo itself reports rounded durations of 1.75s and 1.70s, less than its complete
process phases above. Thus subtracting Cargo's printed time from the profiler
interval conflates source sync, Cargo process setup/teardown and runtime costs.

## Why wcprof's user-work interval is broader

Code inspection establishes the exact current boundary:

1. go-runc v1.1.0 Runc.Run starts its runc command, then sends
   `cmd.Process.Pid` through CreateOpts.Started, before waiting for runtime exit.
2. engine/engineutil/executor.go procHandle.WaitForStart calls the supplied
   started callback when receiving that runc monitor PID.
3. executor_spec.go uses that callback for the start of exec.processRun and
   records its end after callWithIO returns.

The profiler therefore classifies a runtime execution envelope as user work.
Both the native and OTel backends consistently use this boundary. Structural
completeness does not prove that an operation's work-type label isolates the
application process. The engine README now documents this qualification; no
recorder semantics or runtime lifecycle are changed by this commit.

The existing-state trial's 262ms after the root is also present with
DO_NOT_TRACK=1. Analytics cannot be assumed to explain all previously observed
exit latency. Fresh-state exit is 6.5ms; isolate CLI state and engine settings
before assigning causality. Native wcprof does not cover the whole CLI process.

## Verification and evidence

Both runs passed application/library edits, bstr 1.12.0 -> 1.13.0 with matching
10-package rebuild sets and memchr reuse, and failure/repair/old-failure revisit.
Both dependency OTel traces pass the maintained wcprof structural gate:
158 ops, one root, 143/143 declared spans received, no missing/open ops,
orphaned parents, unresolved waits, cycles or dropped links. Replay drift rounds
to -0.0%. The fresh native dump has 497 operations, eight roots, no open/dropped
events, a 2.07s window and replay drift rounding to -0.0%.

A separate two-crate run with phase probes disabled passed the same
failure/repair/revisit regression, validating the default action branch. Its
artifacts are at /tmp/dagger-rust-loop-ccebyx3f; its existing-state timings are
diagnostic checks, not a performance comparison with the fresh-engine trials.

Full artifacts are retained at /tmp/dagger-rust-loop-d5704yl8 and
/tmp/dagger-rust-loop-49_o5aja. Corresponding extracted traces, boundary JSON
and analyzer reports are /tmp/dagger-rust-sync-phase-* and
/tmp/dagger-rust-sync-phase-fresh-*. Per-execution phase values are in each
*cargo-diagnostic.log; every wall-time sample remains in timings.csv. The fresh
trial deleted its engine/volume; the existing dev engine and its caches remain.

This experiment changes the next optimization priorities: measure the actual
container-command boundary and runtime costs, and isolate CLI exit latency.
The source reconciler's checksum-based correctness is still required. There is
no performance improvement claimed by this instrumentation commit.
