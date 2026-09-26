# Performance beyond artifact listing

September 25, 2026. The target is 500 ms of visible Dagger overhead across
navigation, starting work, and returning its results. Application compilation,
tests and long-running services need separate execution measurements. A fast
listing does not establish a fast check, generator or export.

This pass found two upstreamable lifecycle and filesystem problems. Cancelled
services disconnected host access before the engine could save the workspace
lock. Preserving that connection through shutdown reduces subsequent service
readiness from 1.26 to 0.48 s warm and 1.35 to 0.44 s after an edit in the
independent native fixture. The full cancelled command still takes about 0.59 s.
These are local-only measurements, not fresh-engine cold starts.

After transferring a
sparse changeset, the local receiver walked its entire destination merely to
restore the timestamps of known directories. A tiny generator wrote its correct
output, then failed about a minute later on an unrelated inaccessible directory.
The corrected CLI completed the same non-Git fixture in 545 ms, with the new
bytes visible after 513 ms. That is one diagnostic replay, with Cloud disabled;
it is not a paired latency distribution or a general cold-start result.

## Changes suitable for upstream review

### Preserve workspace lock updates when cancelling a service

Commit `868ae5b616` keeps host attachables alive for the existing client shutdown
protocol. Previously, cancelling the command could close the host connection
before the engine exported its updated workspace lock. The next `up` then
resolved the same image tag again. Finite calls persisted the lock correctly;
waiting an extra second before cancelling `up` did not fix it.

Both ordinary and E2E session transports now use the existing internal client
lifetime. Request cancellation remains unchanged. Closing or failing client
initialization still stops the transport; no background daemon or new cache is
introduced. Tests exercise actual session setup, HTTP upgrade and gRPC calls:
the baseline fails after command cancellation, and the candidate passes,
including with the race detector.

The real A/B uses two fresh Git workspaces, an ordinary image tag, the same
retained engine and warm image. It includes first starts, three alternating
warm pairs, three alternating pairs with unique source edits, and separate
wcprof captures:

| Boundary | Before | After |
| --- | ---: | ---: |
| Warm exact HTTP readiness | 1,265 ms | 476 ms |
| Edit to exact HTTP readiness | 1,354 ms | 444 ms |
| Warm full cancelled CLI | 1,393 ms | 593 ms |
| Edit through cancelled CLI exit | 1,456 ms | 589 ms |

Every candidate saved the ordinary OCI lock; every baseline lacked it after
cancellation. All six candidate warm/edit readiness samples were below 500 ms
(404–494 ms), with correct response bytes and tunnel cleanup. Separate profiles
show executed `Container.from` falling from 682 to 1.1 ms. Its enclosing
interpreter interval overlaps and is not an additional saving.

The first empty-lock starts were 1.35 s before and 1.49 s after: this change
improves the following loop, not the first image lookup. See the
[source, tests and complete method](collections-qa-performance-data/next-bottlenecks/attachables-lifetime/report.md).

### Finalize only directories touched by an export

Commit `4b488e191f` contains this correction and its regression coverage.

`Changeset.Export` already selects changed paths. Merge-mode file reception
already avoids enumerating unrelated destination files. The extra enumeration
was in `DiskWriter.Wait`, after the actual writes completed.

The fix waits for the same asynchronous writes, then visits only recorded
directories and their ancestors. It uses `Lstat`, preserves parent-before-child
ordering and the existing timestamp implementation, and skips subtrees replaced
by files or symlinks. Relevant errors still propagate. The visited-directory map
lives for one finalization; there is no persistent cache or weakened freshness.

Filesystem work now depends on distinct relevant ancestors instead of the
entire destination. Sorting depends on the recorded directory set. This helps
sparse generator output and directory exports into large existing projects.
It does not claim to accelerate every single-file export path.

The controlled local benchmark, in baseline/candidate/candidate/baseline order,
isolates the removed scaling cost:

| Operation | Unrelated files | Before | After |
| --- | ---: | ---: | ---: |
| Write one small file and finalize | 0 | 0.084 ms | 0.071 ms |
| Write one small file and finalize | 10,000 | 7.333 ms | 0.070 ms |
| Write 16 small files and finalize | 0 | 1.083 ms | 1.086 ms |
| Write 16 small files and finalize | 10,000 | 8.587 ms | 1.066 ms |
| Finalize one recorded directory | 10,000 | 7.485 ms | 0.0068 ms |

Two samples per variant establish scaling, not a whole-command percentage.
The production revision additionally anchors ancestor traversal to relative
components for Windows path spelling. Its full local package tests and focused
race tests pass; the Windows-only semantics test is skipped on Linux.

Coverage includes asynchronous completion, exact timestamps and modes, merge
and non-merge behavior, links, replacement/deletion, relevant errors and no
access to unrelated directories. A bounded reproducer fails with the old code
after writing the file and succeeds with the fix. We deliberately did not rerun
the broken old receiver over the whole `/tmp` tree.

### Remove quadratic key collection from CLI listings

Commit `dc5c450f70` makes the alias-presence test stop at the first key instead
of constructing a full deduplicated union. Where a union is required, a small
ordered slice gains a membership index after eight distinct pairs. Output order,
dimension/key identity, quoting and filtering are unchanged.

The real formatter benchmark includes decoding and rendering but excludes the
engine and transport: 10,000 elements improve **415.5 to 60.0 ms** over six
alternating pairs. At 14 elements it remains approximately **0.17 ms**. This is
a generic scaling fix, not an explanation for seconds on greetings-api.

The shared formatter serves command listings such as `check -l`, `generate -l`
and `up -l`. Artifact navigation uses `dagger list`; workspace files use
`dagger ws ls`. Their separate code paths need regression coverage too.

## Measure the actual operations

An independent Dang fixture exercises a real check, a generator applied to the
host, an HTTP service, a direct module call and a host-file export. Each edit
has unique input bytes and is immediately followed by the command. There is
no preliminary listing to warm the edited result. File contents, HTTP bodies,
failure/restoration and service cleanup are asserted.

The matrix distinguishes full CLI exit, first observed correct file contents,
HTTP readiness, and execution boundaries from separate wcprof captures.
File/HTTP polling has a 5 ms interval. Exit timing uses a dedicated blocking
waiter; the earlier preflight used Python's timed-wait polling and is retained
as diagnostic evidence rather than a precise latency comparison.

These runs use a retained experimental engine and an isolated empty credential
configuration with Cloud/OTLP export and analytics disabled. They expose local
costs; they must not be compared directly with normal Cloud-enabled exit times
or Kyle's cold number. They are not fresh-volume cold runs. Normal Cloud-enabled
coverage remains a separate measurement boundary.

The baseline and production CLIs completed 79 validated commands, including three
alternating pairs per operation and cache state, deliberate check failure and
restoration, and five separate profiles. On the small Git-rooted fixture:

| Operation | Warm before | Warm after | Edit before | Edit after |
| --- | ---: | ---: | ---: | ---: |
| Run a check | 265 ms | 264 ms | 279 ms | 260 ms |
| Apply a generator | 373 ms | 326 ms | 407 ms | 393 ms |
| HTTP service ready | 1,332 ms | 1,315 ms | 1,345 ms | 1,266 ms |
| Call a module | 490 ms | 442 ms | 447 ms | 477 ms |
| Export a file | 369 ms | 367 ms | 364 ms | 351 ms |

Both CLIs contain the listing-key fix; this comparison isolates the export
change. Warm generator samples begin with already-correct output; edits must
write new bytes. Each export recreates its destination, including warm runs.
Three pairs on a small destination do not establish small gains or
regressions in unaffected commands. In particular, the call's edit median rises
by 30 ms while its warm median falls by 48 ms. The robust export evidence is
the removed destination-size dependency and permission failure, not a claimed
percentage improvement across this table.

All five wcprof captures have zero dropped events and open operations. The
profiled check has its first recorded engine operation after 126 ms and enters the author
interpreter invocation under `Check.sync` after 216 ms; full exit is 259 ms.
The earlier projected check producer is not the start of author check execution.
Time after the last recorded engine operation is 10–23 ms in these local-only
captures, and includes work outside the profiler. Nested spans are not added.

The initial service profile spends approximately 892 ms in `Container.from`,
overlapping the parent interpreter call. Its fixture had no persisted OCI lock.
A subsequent ordinary, finite core `image-ref` command automatically wrote
one `oci-sha` entry. With source and configuration unchanged, three subsequent
`up` commands reach HTTP readiness in **469 / 430 / 455 ms**. No manual digest
pin or cache-policy change was used. Their full lifetimes, including intentional
cancellation, are **540 / 545 / 579 ms**; readiness and exit are different metrics.
The lock remained unchanged. This established that nested calls can consume
the lock. The cancellation investigation above subsequently identified and
fixed why the earlier service calls did not persist it.

## Regression coverage on greetings-api

The pinned public greetings-api copy also completed 113 validated commands:
12 flows, three alternating warm pairs, source freshness probes and nine separate
profiles. The CLI source comparison includes both new fixes. The engine and
experimental SDK stack remain fixed; these are still local-only measurements.

| Command flow | Baseline median | Candidate median |
| --- | ---: | ---: |
| Artifact overview, `dagger list` | 783 ms | 790 ms |
| `check -l` | 811 ms | 785 ms |
| `check -l --all` | 1,534 ms | 1,627 ms |
| Filtered check listing | 1,886 ms | 2,098 ms |
| Checks by artifact type | 1,649 ms | 1,658 ms |
| Go module collection | 1,270 ms | 1,313 ms |
| Go test collection | 1,658 ms | 1,398 ms |
| Dynamic check help | 708 ms | 623 ms |
| Generator listing | 1,474 ms | 1,395 ms |
| Service listing | 732 ms | 795 ms |
| Workspace files, `dagger ws ls` | 184 ms | 184 ms |
| Execute the selected check | 1,644 ms | 1,643 ms |

The filtered-listing slowdown appeared in all three pairs. Eight further pairs
gave 1.93 versus 2.07 s and a +212 ms median paired difference. Separate profiles
showed identical operation/query counts, while the higher engine CPU regime
occurred more often for the candidate. A subsequent six-pair control with the
**same executable on both sides** had a −18 ms paired median and individual
differences from −252 to +293 ms. This establishes substantial variability;
it does not conclusively clear the earlier difference. No blanket performance
or non-regression claim follows from this table. The expanded 14-row output is
checked exactly; renaming/adding a test changes its keys, and restoration
restores the original output. These edit probes test correctness, not paired
edit speed, because identical content can prewarm the second CLI.

The expanded-listing profile records six Go runtime executions totaling 543 ms
and seven Git public advertisements totaling 703 ms. These intervals overlap
other work and are not additive savings. Local overhead remains substantial
without Cloud: the 500 ms mixed-SDK goal needs more than faster telemetry exit.

## Allocation work that remains on the warm path

The unprofiled identical-executable control allocated a median **574 MB per
filtered listing** inside the engine. A separate eight-command CPU/allocation
diagnostic found GC marking at 33% of sampled process CPU. This includes idle
workers and cleanup after commands; it is not 33% of removable user latency.
No forced GC or runtime tuning was used.

Repeated module/schema preparation is a concrete target. Of the sampled
`Interface.FieldSpecs` allocations, 89% came from `Interface.Satisfies`.
Reusing visible field signatures within one reconciliation pass could avoid
rebuilding them for every compatibility check while preserving view and
session boundaries. This is under investigation, not included in the timings.

Local span export also allocates substantially even without Cloud. JSON
assembly and database opening are visible in its stacks; those samples alone
do not prove unnecessary reopenings or a lifetime bug. Further instrumentation
must establish counts before changing ownership or durability. See the
[allocation report and measurement limits](collections-qa-performance-data/next-bottlenecks/cli-key-scaling/filtered-engine-allocation-v1/report.md).

## Other findings and next decisions

* A larger Cloud coalescing window reduces async relay request count by 34%
  and ten-command complete-delivery time from 25.96 to 19.05 s. CLI latency
  stays about 1.59 s and the queue still grows. Synchronous forwarding shows
  no latency gain. Keep the window change experimental; do not enable it
  globally or describe it as solved telemetry throughput.
* A [local receiver experiment](collections-local-receiver-performance.md)
  completed 24 commands using the real ingestion handlers and isolated
  Postgres/ClickHouse: core calls take 378 ms, workspace navigation 237 ms,
  and the mixed-SDK listing 1.57 s with local export enabled. All 433 POSTs
  were accepted. HTTP acceptance, observed database rows and full durability
  remain different boundaries; this is not a production capacity test. A later
  five-pair comparison gives **1.721 s local versus 2.064 s production** for
  the same listing, with seven ordinary production commands in total. The full
  broader UX matrix has not yet been repeated against production Cloud.
* Reusing the greetings backend constructor removes a 91–96 ms constructor
  execution on a warm hit, but five whole-listing pairs do not establish a
  latency improvement. Source edits still invalidate it. Do not claim the
  helper saving as a whole-command gain or override an author's cache policy.
* Snapshot `Flush` has the same timestamp-restoration traversal pattern.
  A separate audit and tests are prepared. Its subsequent `Usage()` still
  needs a full accounting walk, so removing the first pass would not make
  the whole snapshot operation sparse. This path is not changed here.
* The existing Go SDK static-entrypoint work should own metadata generation.
  A compatibility adapter for its current JSON call contract is prepared,
  not benchmarked. Deferred configured defaults remain a separate prototype;
  authority, live workspace reads and effectful defaults must retain their
  current evaluation semantics.

The existing [cold, SDK and developer-loop investigation](collections-next-bottlenecks-review.md)
remains applicable. The 500 ms target has not been demonstrated across the
real mixed-SDK workload, Cloud-enabled commands and cold starts.
