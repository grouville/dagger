# Discovery: bootstrap work and the Cloud completion floor

The next work is ordered by removable time on the actual command path. The
largest listing/check opportunities remain execution-only discovery dependencies
and telemetry completion. Faster API metadata loading is a separate, demonstrated
gain; it does **not** accelerate the CLI's selected-check path.

| Priority | Evidence | Next experiment |
| --- | --- | --- |
| Listing preparation | Separate local listing diagnostics measure 331/289 ms in resolving the configured Container address; those listings do not subsequently consume the base. These are inclusive address-resolution intervals, not producer-only execution time. | Defer execution-only defaults until their consumer needs them, while testing error timing, ambient workspace reads, session ownership and actual check execution. No transparent semantic equivalence is assumed. |
| Command completion | Transport captures place engine log drainage at 307–432 ms; later CLI completion is also variable. | Separate the upstream OTel upgrade from joined early log flushing. Preserve delivery and count requests/bytes; independent log exporters did not earn adoption. |
| CLI API metadata | The measured warm core and native Dang API calls save about 140–150 ms locally; distinct-input edits save 138–152 ms in two pairs. | Keep the measured prototype, then reduce projection maintenance and extend cache-isolation/restart coverage. |
| First workspace navigation | One new-volume pair saves 374 ms by deferring unneeded TypeDefs. | Keep lazy metadata; distinguish avoided work from work deferred to a later consumer. |

These numbers are observations from different experiments, not an additive route
to 500 ms. Static SDK work overlaps registration/compilation costs and must be
measured in the combined stack. Small schema-fork and map changes are lower
priority here because they do not explain the current critical path.
Selected checks differ from listing: the 373 ms backend-address resolution in
their profile supplies a base that execution actually consumes. Deferral alone
would move this work, not remove it. Measure dispatch overhead and the authored
check's execution separately, preserving both in full-command timings.

Source commits on `perf/collections-discovery`:

* `03776794a2`: defer SDK-facing core metadata until first use.
* `53fe69a0fa`: include public collection types in metadata closure; a correctness
  fix exposed by the real command probes.
* `ee092e4122`: compact CLI metadata prototype, including workspace demand routing.
  Its commit message records remaining upstream gates. A normal branch build now
  includes this prototype; the experimental SDK payloads used for timings remain
  separate.

The latest ordinary comparison removes **374 ms from the first `dagger ws ls`**:
1.119 → 0.745 s on two new engine volumes with production Cloud enabled. It
avoids constructing SDK-facing core metadata before a command needs it. This is
one cold pair, not a cold-start distribution. The 500 ms complete-command target
remains unmet.

The comparison uses the experimental SDK stack already described in the
[navigation report](collections-navigation-performance.md), with the same SDKs,
CLI, source and image on both sides. The only engine difference is lazy core
metadata. It is a generic engine change, independent of greetings-api or an SDK.
Engine startup and existing image/page caches are separate from the timed CLI.

## Remove work before adding concurrency

Additional timers locate 401–482 ms of core TypeDef construction before the
query-level wcprof boundary. A workspace listing only needs the installed
GraphQL schema; it does not consume those module-facing TypeDef values. The
candidate forks that schema directly and leaves the existing per-view metadata
builder to its actual consumers. It adds no result cache, TTL or authority
exception.

That distinction matters: the first subsequent core-module call pays the deferred
cost, increasing from 731 to 1,032 ms in this sequence. Metadata construction
itself is not faster yet. First artifact discovery still takes roughly 25 s on
these engines after the earlier core/native commands. Those are not fresh-engine
artifact timings.

Thirteen focused schema tests pass normally and with the race detector, covering
API views, metadata content, cross-session retained IDs, isolated schema forks,
concurrent first demand and snapshot-share restrictions. All 44 real commands
pass output validation, including the 14-check listing, selected check execution,
native generation and fresh input edits. The
[source validation](collections-qa-performance-data/lazy-core-source/review.md)
and [complete ordinary results](collections-qa-performance-data/lazy-core-runtime/report.md)
retain the negative samples as well as gains.

## Warm observations are not all code improvements

| Flow | Pairs | Baseline median | Lazy metadata median |
| --- | ---: | ---: | ---: |
| Workspace listing | 3 | 578 ms | 560 ms |
| Native generation, full exit | 3 | 725 ms | 832 ms |
| Native generation, output visible | 3 | 332 ms | 326 ms |
| New-input generation, full exit | 3 | 835 ms | 927 ms |
| Artifact listing | 3 | 2.516 s | 2.126 s |
| Generator listing | 2 | 1.888 s | 1.581 s |
| Selected check | 2 | 3.581 s | 2.336 s |

The artifact differences largely coincide with Cloud-drain variation. Generation
has mixed causes: one 704 ms penalty lies in the Cloud drain, but other residuals
are outside the engine shutdown handler. A baseline edit outlier occurs before
the output is written. These results establish neither a general warm speedup
nor a causal generation regression from lazy metadata.

A subsequent control runs the **same baseline binary in both engine slots**.
Its three measured pairs finish at 823/837/1,296 ms versus 734/724/830 ms, while
all files become visible in 289–307 ms. The previous direction reverses without
a code difference. This demonstrates measurement variability, not proof that
all code regressions are absent. The engines keep their independent volumes;
two explicit local and two Cloud primers precede the six measured commands.
All ten calls pass, and the candidate binary and fixture are restored afterwards.

Aligned engine logs place 69/71/481 ms of those paired differences after the
main shutdown handler completes. Output visibility and handler duration are
otherwise close. This narrows the variable tail to CLI completion after the
engine response, without identifying an individual CLI HTTP request. See the
[same-binary control](collections-qa-performance-data/lazy-core-aa/report.md).

## Cloud work on the critical path

A separate instrumented transport comparison records the actual request phases,
without retaining payloads or credentials. Each of six native generations sends
the same four log requests: two call-payload batches and two ordinary-log batches.
The processors already flush concurrently, but their shared SDK exporter admits
one request at a time. This log branch determines the 307–432 ms engine drain.

All 45 trace/log requests reuse connections, with no DNS, TCP or TLS setup.
Connection acquisition totals at most 0.059 ms per command. The time lies after
writing the request and before the first response byte: network plus remote
processing, which this measurement does not separate. Token refresh does not
occur, and engine disk writes are zero in these warm generation brackets.

An isolated candidate gives each log channel its own exporter while sharing the
HTTP pool and credential refresh source. It preserves each exporter's serial
contract, distinct retry writer identities, joined flush and bounded shutdown.
It does not return before delivery or change the UX. Subsequent paired
validation below does not justify adoption: more overlap may increase destination load, and the
concurrent trace branch limits the opportunity. In the existing samples, the
last log response ends only **13–107 ms after the trace flush**; removing the
whole log duration would overstate the possible gain.

The [transport evidence](collections-qa-performance-data/cloud-transport/runtime-evidence/report.md)
includes all numeric phases, request counts, bytes and resource counters. It is
an attribution experiment, separate from ordinary timing medians.

## Work still needed toward 500 ms

The priority is work on the critical path, measured separately for each command.
The general CLI metadata loader is not used by selected checks. A retained local
selected-check profile reaches its selected batch resolver after 1.415 s;
the complete CLI takes 1.573 s. Its collection preparation includes a 373 ms
backend-address resolution, 291 ms module discovery and 74 ms test discovery.
The backend contains one 86 ms registration process and two authored calls
(79 ms constructor, 95 ms base construction). Empty constructors already bypass
SDK execution; skipping these authored calls would change state. The incoming
static SDK work targets registration, while deferring an unused execution-only
default is a distinct, larger design question. See the
[check startup evidence](collections-qa-performance-data/selected-check-startup/profile-findings.md).

The compact metadata candidate has now been measured with both CLIs on the same
engine and volume, alternating order and using ordinary, unprofiled commands:

| Flow, three warm pairs | Original projection | Compact projection |
| --- | ---: | ---: |
| Core API call, local | 377 ms | 227 ms |
| Native Dang module call, local | 443 ms | 304 ms |
| Core API call, production Cloud | 628 ms | 591 ms |
| Native Dang module call, production Cloud | 823 ms | 817 ms |

These are full process-exit medians. The roughly 140–150 ms local gain does not
translate into that much Cloud end-to-end improvement in this small series.
There are 32 correct benchmark/primer calls. A subsequent collection correctness
probe fails in the old CLI with a missing `[GoModule]` typedef; a separate control
reproduces that failure on the original engine. Correcting the closure makes the
old-query collection call pass. The compact path then exposes a separate missing
workspace-module loading trigger; that failed call is excluded from performance
results. Both defects are now corrected in the branch, with the follow-up
validation described below. The one edited-input
pair confirms correct bytes, but its second command could reuse work from the
first on the shared engine, so it is not an independent edit latency comparison.
The [numeric report](collections-qa-performance-data/cli-metadata-runtime/report.md)
and [source validation](collections-qa-performance-data/cli-metadata-source/evidence.md)
preserve these limits. No 500 ms Cloud result is claimed.

A subsequent [15-command local validation](collections-qa-performance-data/cli-metadata-edits/report.md)
passes both collection probes, renamed-function calls, deliberate rejection of
the stale function name, and restoration of the original source. Four distinct,
unprimed input edits use bytes that neither CLI has previously evaluated; the
engine and unchanged lower-layer caches remain warm. The two
alternating pairs are **445 → 293 ms** and **443 → 305 ms**. This is a small native
Dang read fixture, not greetings-api listing or check execution, and has only two
samples per CLI. Collection/setup and schema-change timings are used for
correctness, not pooled into that latency comparison. No Cloud exports are enabled
in this follow-up; the original engine and fixtures are restored.

The [routing validation and final review](collections-qa-performance-data/cli-metadata-validation/final-source-review.md)
preserve scoped workspace loading and the existing schema/view cache identity.
The projection performs ordinary `currentTypeDefs` selection before assembling
the response, without a separate cache or TTL. Before an upstream proposal, extend
same-name module-version isolation, persistence/restart and older-engine live
fallback coverage. Sharing the projection shape, or a carefully proven generic
GraphQL response optimization, would reduce the maintenance cost of the prototype.

[Retained shutdown logs](collections-qa-performance-data/cli-metadata-attribution/report.md)
locate the masked gain: Cloud core calls reach the engine shutdown handler
93–137 ms earlier, but the CLI interval after that handler grows 84–127 ms.
Module calls reach the handler 113–154 ms earlier, while its Cloud flush grows
50–97 ms. These boundaries establish where time moves, not the exact network,
exporter queue or remote-server cause. Optimizing the completion tail remains
necessary to turn the reduced preparation work into consistent user latency.

* Prioritize unnecessary metadata work and discovery dependencies. A separate
  local first-consumer wcprof records 469 ms constructing core TypeDefs, followed
  by roughly 324 ms of response traversal/publication. The actual version query
  takes 0.36 ms. A scoped bulk metadata projection could avoid the thousands of
  scalar selections while preserving the CLI's existing metadata shape. These
  are instrumented first-demand observations, not warm latency estimates.
  A true warm capture after an explicit same-process primer subsequently measures
  36 ms in `currentTypeDefs` and 157 ms in response traversal, with 19,861 response
  operations. That is the measured warm opportunity targeted by the candidate.
  Type-reference reuse only touches about 26 ms of individually measured
  selections in that profile; it is a smaller opportunity than the full response
  path and is not a 400 ms solution.
* Per-module wcprof markers now bound the collection scheduling opportunity:
  Go and its backend dependency finish resolution **193 ms before catalog
  completion at warm state, and 167 ms before completion after a fresh comment
  edit**. These are optimistic upper bounds, not implemented savings. Resolution
  is earlier than the authoritative publication barrier: entrypoint arbitration,
  schema ownership and nested workspace addresses still have to be respected.
  A short test process may have overlapped the first profile; neither capture
  is an ordinary timing comparison. The
  [readiness evidence and design review](collections-qa-performance-data/module-readiness/report.md)
  explain why a large loading/expansion pipeline rewrite is not the first choice.
* The independent-log ordinary comparison is complete: 44 correct commands, with
  warm native generation 822 → 723 ms but new-input generation 830 → 1,016 ms and
  artifact listing 2.033 → 2.729 s. **The candidate remains isolated.** Separate
  [transport accounting](collections-qa-performance-data/cloud-parallel-logs/diagnostic/runtime-evidence/report.md)
  now records 16 → 33 artifact log requests for almost unchanged data volume.
  Removing the serialization gate fragments the batches in this sample. Disk
  pressure and a different critical branch prevent attributing the earlier
  latency regressions to that mechanism alone. All eight diagnostic calls pass;
  this experiment still does not justify adopting the candidate.
  Workspace listing has no engine log uploads in the earlier diagnostic, so this
  change alone cannot remove its trace-completion floor.
* Keep measuring both file/readiness time and full process exit. The same-binary
  control shows that a fast result can still have a variable completion tail.
  A joined early CLI log flush is a separate candidate. Its backpressure concern
  already has an [upstream OpenTelemetry fix](https://github.com/open-telemetry/opentelemetry-go/pull/8620),
  included in the [v1.45.0 release](https://github.com/open-telemetry/opentelemetry-go/releases/tag/v1.45.0).
  This branch explicitly pins the log SDK to v0.16.0, so the fix is not active.
  Dependency compatibility and paired CLI timings still need validation. This
  experiment is now the next completion-tail comparison; it is not a measured
  latency improvement.
* Keep static SDK metadata work separate from these engine changes. SDK work can
  remove warm registration processes as well as cold compilation; these costs
  overlap other work and cannot simply be summed as predicted savings.

The earlier [279-command matrix](collections-allocation-matrix.md) covers services,
exports and module calls as well as discovery. This latest 44-command comparison
does not repeat every service/export case. Any combined stack still needs those
flows before a claim of 500 ms across the product.
