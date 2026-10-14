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

## Dang runtime parsing in the real module

A matched five-pair series compares the profiler-linked module engine with the
same engine plus Sipsma's PR #14649. That change avoids two additional source
parses on each Dang function call. The module code, compiler, telemetry receiver
and Cargo command remain the same. Four fresh preparation edits per engine are
excluded; every timed invocation makes a new application edit. An invalid Rust
edit fails on both engines, confirming that source changes and compiler errors
reach the real `dagger check rust:check` entrypoint.

| Median of five edited commands | Before | With PR #14649 |
| --- | ---: | ---: |
| Complete Dagger command | 1,501 ms | 1,318 ms |
| Complete native Cargo check | 314 ms | 323 ms |
| Check execution self-time, with nested queries linked | 427 ms | 187 ms |
| Check start to its first nested API query | 423 ms | 181 ms |
| Cargo/rsync worker | 453 ms | 437 ms |
| Container runtime start, included above the worker | 64 ms | 87 ms |

The full-command median improves by 183 milliseconds, about 12%. The phase
measurements support a reduction before the module's first nested API query;
they do not attribute all remaining self-time to parsing. Medians are separate
measurements and must not be added. All ten commands pass, with 1,427 recorded
operations, 17 API queries and zero dropped profiling events each.

The timings overlap: before ranges from 1.228 to 1.777 seconds, after from 1.219
to 1.514 seconds. Host-wide CPU pressure is substantial during several samples,
and I/O pressure varies. Keep all samples and treat this short profiled series
as encouraging evidence rather than a precise production speedup. Native Cargo
and Dagger both run `cargo check`; these numbers do not measure the prototype's
native compiler cache, which is not yet selected by the Rust module.

The next runtime measurement is an engine CPU profile during fresh module
edits, to locate the remaining computation. The compiler worker also includes
source reconciliation and Cargo bookkeeping; its gap from native Cargo is not
proof of slower rustc. Command logs, wcprof captures, pressure samples and the
analysis are in `/tmp/rust-cache-sipsma-review/module-comparison`.

A second five-pair series repeats the same fresh-edit workflow without wcprof
recording, keeping telemetry enabled. Complete-command medians are 925/673
milliseconds for Dagger and 209/190 milliseconds for native Cargo,
before/after. Dagger ranges are 861–1,149 and 650–1,011 milliseconds; all ten
checks pass and both invalid-source tripwires fail as expected. This supports
the direction of the profiled result without using profiler timings as the
user's expected latency. These remain short local-engine series. The faster
module still stores Cargo's state in its existing cache volumes; native replay
integration has not yet been measured through this command.

An engine CPU profile during sixteen fresh edits records 1.24 seconds of parser
work across the capture. Of that, 270 milliseconds pass through ordered-choice
statistics collection, including repeated string formatting and map updates.
The generated Dang parser collects those statistics by default. This motivates
a parser experiment that keeps statistics available when requested, without
caching mutable syntax or invocation state. CPU samples are aggregate work,
not an additive wall-time breakdown. The profile and command logs are in
`/tmp/rust-cache-sipsma-review/module-cpu`.

## Optional parser counters: complete-command experiment

The experiment makes ordered-choice counters opt-in through Pigeon's existing
`Statistics` option. Requested counters still work, and restoring an option
restores its previous counter setting. Expression counting and limits remain
active. The generator source produces exactly the patched Dang parser used by
the measured engine; this is not a syntax-tree cache or a telemetry change.

The focused regression fails on the original parser and passes with the patch.
The existing Dang package tests also pass. Five parser benchmark samples on the
Rust module source show 110.35/67.41 milliseconds with/without requested counters,
425,775/284,873 allocations and 20.42/18.34 MB per parse. The same binary runs both
modes. This locates the allocation cost; it is not the command-level result.

A separate five-pair series compares the engine containing PR #14649 with the
same engine and the patched parser. It records no wcprof events during timing,
and retains the local telemetry receiver. Every timed command has a new source
edit. Both engines receive four preparation edits, and the new engine's initial
toolchain preparation is excluded.

| Median of five edited commands | Control | Optional counters |
| --- | ---: | ---: |
| Complete Dagger check | 695 ms | 637 ms |
| Complete native Cargo check | 181 ms | 183 ms |
| Dagger range | 643–713 ms | 623–657 ms |

All ten checks pass; invalid source fails on both engines. Every paired Dagger
sample is faster with the experiment. The median difference is 58 milliseconds,
about 8%. Host-wide CPU pressure stays between 1–4% during these Dagger samples;
I/O pressure stays below 7%. Keep the short-series limitation, and do not add
its gain to the earlier series as though they shared identical conditions.

These are warm local-engine checks using the module's existing Cargo cache
volumes. They do not establish native compiler-cache module integration or
remote-engine performance. Reproduction patches and the regression are in
[experiments/dang-choice-stats](experiments/dang-choice-stats/README.md), with
raw data in `/tmp/rust-cache-sipsma-review/module-choice-stats-comparison-unprofiled`.

## Retaining compiler snapshots without an archive

The module backend experiment now offers `BuildNativeCached`: it retains a
manifest string and native batch-directory fields instead of copying each new
compiler batch into a combined history directory. Exact-result lookup and
incremental seed selection use the existing logic and execution cache keys.
Expired batch references are dropped from the object list.

Its full two-engine integration test passes, covering source edits, exact
reversion hits, pruning, transfer of the retained metadata and directories, and
a new dependency edit on the fresh receiver. This proves the representation's
correctness and portability. A latency improvement, bounded physical ancestry
and automatic module discovery remain unmeasured. The branch is
[`experiment/rust-native-cache-objects`](https://github.com/grouville/dagger/tree/experiment/rust-native-cache-objects).

The actual Rust module's native backend now passes edited reuse and transferred
cache reuse. A subsequent alternating five-pair edited-command measurement
reduces the integration from 1.154 to 0.845 seconds, with native Cargo check at
0.174 seconds. The implementation changes, correctness tests and remaining
limits are in [NATIVE_MODULE_OCT13.md](NATIVE_MODULE_OCT13.md).
