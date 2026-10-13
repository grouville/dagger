# Edited builds: where the remaining time goes

The 102-action workspace now spends roughly as much time in the compiler worker
as native Cargo spends in the complete build. Most remaining latency is outside
the worker. Optimizing compiler scheduling alone cannot remove that latency.

These are warm engines and incremental histories, with a fresh source edit on
every measured run. They are not unchanged-build measurements. The Rust compiler
is 1.77.2, the CLI requests beta.17, and the batch uses eight workers. Telemetry
remains enabled and exports to an isolated local receiver. Production Cloud and
remote-engine latency are not established by these measurements.

## Repeated wcprof captures

Twelve captures alternate the control engine and a directory-copier experiment:
three leaf edits and three shared-library edits per engine. Four preparation
edits populate each history before measurement. The existing benchmark checks
artifact bytes and modes, executable behavior against Cargo, the observed edit,
expected recompilations, and subsequent finished-result reuse. All twelve pass;
no history fallback or dropped profiling events occurred.

The shared edits show the most stable timings:

| Measurement, median of three | Control | Copier experiment |
| --- | ---: | ---: |
| Complete Dagger command | 1,266 ms | 1,242 ms |
| Complete native Cargo command | 633 ms | 626 ms |
| Engine query time before the worker | 325 ms | 298 ms |
| Compiler worker | 651 ms | 669 ms |
| Engine query time after the worker | 161 ms | 139 ms |
| Runtime start, included above | 36 ms | 38 ms |
| Output snapshot commit, included above | 12 ms | 13 ms |
| Client shutdown after artifacts/history are ready | 16 ms | 19 ms |

Each median is calculated separately; the rows are not an additive breakdown.
The worker includes dependency preparation, rustc and output publication. It is
not a measurement of rustc alone. Time outside engine queries includes client
work, request gaps, connection and shutdown.

The engine query times use the union of their intervals, split at the single
worker's start/end. Artifact export and history retention await the same
execution. Summing their critical paths would count the compiler twice: the
initial control capture reports 2.19 seconds summed across queries during a
1.36-second command. Inspect their timelines and one materialization request at
a time instead. A final `Directory.id` request is short and is not the whole
build's critical path.

Shared edits execute 539 recorded operations and 15 API queries, including 102
package digests and one container execution. Leaf edits reuse 100/102 compiler
results; shared edits correctly reuse none. Leaf timings in this capture series
are heavily affected by host I/O pressure: some runs show 34–66% host-wide I/O
stall time, with worker and output-commit outliers. They do not establish a
copier speedup. Host pressure is context, not a per-process measurement.

## Challenge the copier experiment

Reusing an already resolved directory parent cuts a focused 2,032-file copy
benchmark from 43.22 to 40.76 milliseconds, with about 11% fewer allocations.
The full layercopy suite and its race run pass, including directory replacement,
symlinks, overlay behavior, permissions and xattrs.

Two unprofiled five-pair series do not establish a command improvement. Leaf
medians are 620/617 and 592/596 milliseconds; shared medians are 1,333/1,591 and
1,340/1,312 milliseconds, control/experiment. Outliers remain in the data. The
profiled series' 24-millisecond difference is too small to resolve the question.
The experiment remains separate from the Rust prototype's default engine.

Even if a 6% copy improvement held for approximately 220 milliseconds of copy
work, it would save only about 13 milliseconds. That cannot close the roughly
133-millisecond gap between this control and Cargo plus 0.5 seconds.

## First principles

1. Preserve the compiler's incremental state and exact finished-result reuse.
   They already make the worker competitive with Cargo in this fixture.
2. Identify work that moves the same immutable state solely to assemble the
   next input or history directory. Reducing bytes, directory entries or whole
   copy operations has more potential than optimizing one path lookup.
3. Separate lock waiting from the work the lock protects. An ownership read
   can wait for a running snapshot operation to publish coherently; a long
   `leaseSyncMu` wait is not proof of slow lease bookkeeping.
4. Measure a large crate and long edit sequences as well as this fan-out graph.
   Four retained manifest entries do not, by themselves, prove bounded physical
   snapshot ancestry, storage or cross-engine transfer cost.

Finer experimental wcprof phases distinguish snapshot allocation, mounting,
file copying, committing, ownership reads and lease updates. Their results
should determine the next implementation change; telemetry removal and relaxed
compiler cache keys are not supported by these profiles.

Raw recordings, command logs, pressure samples and correctness results are in
`/tmp/rust-cache-sipsma-review/wcprof-series`. The earlier unprofiled comparisons
are in `copy-comparison` and `copy-repeat` beside it.

## Finer phases and the large application crate

A separate diagnostic engine adds wcprof phases without changing the copy or
locking algorithms. Four fan-out edits and two large-crate edits pass the same
checks. The existing coherent ownership-read and lock-wait tests also pass.

On its two shared edits, actual directory-copy calls take 212 and 220 milliseconds
combined: 108–112 milliseconds preparing the seed and 101–112 milliseconds
inserting the new batch into history. Snapshot allocation adds 1–4 milliseconds,
the two commits add about 15 milliseconds, and mounting/copy setup adds about
15–16 milliseconds beyond the copy calls. The copy calls account for 204–207
milliseconds on the history request's critical path. Avoid double-counting its
overlapping export request.

Ownership collection takes 125–129 milliseconds in its slowest call, while all
lease updates together take only 6–7 milliseconds. The ownership reader waits
for coherent publication of the running input operation. Thus the earlier
approximately 128-millisecond lease-lock wait does not establish expensive
lease updates or a reason to weaken synchronization.

Local copies can hard-link unchanged files directly between snapshots when
their metadata permits it. These are filesystem traversal and entry-creation
costs; the copy duration is not proof that all file contents were transferred.
The profiles support investigating fewer traversed entries or removing one of
the assembly copies while preserving immutable ownership and portability.

| Diagnostic fixture, median of two fresh edits | Dagger command | Cargo command | Compiler worker |
| --- | ---: | ---: | ---: |
| 102 actions, leaf edit | 607 ms | 221 ms | 214 ms |
| 102 actions, shared edit | 1,247 ms | 636 ms | 635 ms |
| 128-module application plus three libraries, application edit | 742 ms | 478 ms | 488 ms |

The large application's edited build reuses 3/4 results. Its five directory
copies total only 7 milliseconds, so the fan-out copy optimization is unlikely
to help it substantially. The sample size is two per scenario and the diagnostic
engine differs by instrumentation; these numbers locate work and do not prove a
speedup over a previous engine.

Captures are in `wcprof-detailed` and `wcprof-large` beside the first series.
These replay timings exclude Rust-module resolution and module execution; the
module command and native cache are the integration target.

## Real Rust-module baseline

Two fresh application edits through `dagger check rust:check` take 1.447 and
1.383 seconds with the existing module cache. Both checks pass. They are
`cargo check` operations, so they cannot be compared directly to the replay's
`cargo build` timings above. The first valid toolchain preparation takes 27.8
seconds and is excluded from these warm edited-build measurements.

The first invalid preparation imported `/tmp` because a pre-existing Git root
there enclosed the fixture. It was canceled after an aggregated goroutine
profile showed over 500,000 blocked filesync goroutines. A separate Git root and
explicit CLI workspace isolate the valid retry. No filesync patch follows from
this setup error. The replay measurements use explicit source paths and do not
share this contextual-import mistake.

The valid module profile records 1,427 operations, including many cheap type
definition calls and one Cargo execution. Its Dang client's queries are not
linked to the parent check by the existing wcprof hooks. Consequently a
one-second `Check.sync` self-time includes unconnected child work; it cannot be
called one second of engine overhead. An experimental profiler correlation
connects the Dang client's work to its calling operation before deeper analysis.

The module-facing replay API now accepts native source/history directories,
reading only Cargo configuration into the client to validate its recorded plan.
The existing full two-engine replay scenario passes through this entry point,
including changed configuration rejection, incremental edits, exact hits,
pruning, undeclared input rejection and edits after cache transfer. This prepares
the module boundary; the Rust module still uses its existing backend until the
actual entrypoints, history discovery and supported Cargo workflows are wired.
