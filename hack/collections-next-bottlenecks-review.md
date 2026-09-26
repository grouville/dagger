# Collections: review after main and the next bottlenecks

September 25, 2026. This review targets `grouville/dagger:perf/collections-discovery`
with reviewed baseline `c12a34663b`, rebased onto main `d8f1f0d6d2`. It separates the performance
commits from the collections feature commits carried by the same branch.
The goal remains a 500 ms real edit-to-listing loop. It has not been reached.
The investigation also covers actual check execution: first execution, reuse of
a warm result, and source edits that must change the result. Those are separate
workloads; a faster listing alone does not demonstrate faster tests.

The retained changes still remove necessary, independently identifiable costs.
Current SDK and remote-cache work does not make them redundant. However, the
fastest recorded absolute timings require the experimental SDK stack; they
are not promises for an ordinary build of this branch. Historical incremental
gains are not additive and have not all been remeasured separately after main.

The largest new developer-loop gain is an ordinary module recipe change:
**edit application code, then execute the selected checks: 11.446 → 3.559 s**
over five alternating pairs. Compiler/download cache volumes are now mounted
on the actual backend builder in the isolated candidate. The build and tests
still execute; a changed HTTP response correctly fails the E2E test.
This module fix is separate from engine improvements and from the experimental
static-metadata and durable-telemetry prototypes described below.

## What to keep, and what is still experimental

| Change above main | Review decision | Reason / upstream boundary |
| --- | --- | --- |
| CLI single session and bulk artifact metadata (`70afe1641e`) | Keep | Avoids repeated discovery sessions and per-row GraphQL object work. Static SDK definitions do not remove transport and command setup costs. The internal JSON projection trades field-level selection for a fixed CLI representation; preserve complete-output and filter tests. |
| Dimension indexes and shared expansion (`b58e794fe9`) | Keep | Index construction is linear in dimensions; repeated name lookup is constant-time for large scopes. The prefix DAG shares receiver work only within one expansion, with workspace identity in the key. It does not cache dynamic collection answers across edits or sessions. |
| Parallel collection expansion (`e6200c7b3f`) | Keep; examine large fan-out | Preserves result order and skips unselected descendants. Concurrency is currently unbounded per template/parent. A future bound must govern actual receiver execution, not hold a semaphore while recursively waiting on children; that can deadlock. No new large-workspace claim is made here. |
| Prepared caller-scoped schemas (`e25f244f3d`) | Keep scope restrictions | Only eligible `WithRoot` forks under the same opaque session/caller authority reuse preparation. Mutations, ownership clones and entrypoint proxies invalidate/exclude reuse. Do not extend to global module-name caches. |
| Artifact servers fork prepared core schemas (`21e85073d2`) | Keep | Removes repeated resolver reflection/installation. User-module installation, root and mutable schema maps remain independent; API view is explicit. Remote result caching does not eliminate this local preparation. |
| Dang schema decode once per session (`cdf8585227`) | Keep | Uses the existing session-owned cache and held schema File identity; each evaluation gets a private mutable copy. Move the copy implementation alongside the library model so new fields cannot accidentally become shared. |
| Native Dang calls skip registration metadata (`74c8455922`) | Keep; simplify with library fix | Runtime calls with already-served self types do not need registration passes. Registration and entrypoint paths retain them. The new directive-retention candidate removes one workaround at its producer. |
| Empty module-env lookup / duplicate self-module installation (`0773d9e7b6`, `e78afd970a`) | Keep | Avoids work when its inputs prove it unnecessary; no new answer cache or relaxed invalidation. |
| Public Git advertisement reuse (`5e487bc94c`) | Keep session boundary | Reuses refs already fetched by the anonymous visibility probe, avoiding a duplicate transfer. New sessions still recheck visibility/refs; credentials, SSH, services and URL userinfo retain separate behavior. Request-count reduction is proved; historical full-command timings were too noisy for a stable percentage. |
| Packaged TS runtime uses committed Go bindings (`f14419ac42`) | Keep; rebuild SDK payload | Removes redundant generation using existing TOML runtime behavior. It does not prebuild all user modules. Upstream needs ordinary generated-file freshness and supported-platform payload CI. |
| First analytics upload overlaps the command (`ab360f6bd5`) | Keep | Starts existing work earlier; Close still waits and drains. Separate from engine/CLI OTel splitting. It helps the fixed floor, not all discovery CPU. |
| Cloud payload batches 128 to 512 (`1b18e58b86`) | Keep | Network batches amortize round trips independently of local persistence. Local batches stay 128; retry/order/shutdown bounds remain. Post-rebase paired evidence: 2.867→2.662 s with the full prototype stack. |
| Module-config reads, idle nested connections, empty metrics, lazy digest (#14179/#14180/#14182/#14183) | Keep; already separate open PRs | Fresh GitHub checks show all four still open. They address distinct local paths and remain useful after telemetry splitting. The connection fix addresses multi-second tails; do not claim it as a median gain. |
| Image-import wcprof boundaries (`80baa2eb11`, `677da74a1e`) | Keep as observability | Expose copy/prepare/apply/commit costs without changing ownership, GC or cache identity. Instrumentation is not a latency improvement by itself. |
| Dang syntax cache; TS bundle/startup caches (`4a97c1b69e`, `08984e1214`) | Keep isolated; rework before enabling | Require maintained AST cloning/ownership and a memory budget; generator-owned packaging; Node/loader/UID/image compatibility. Published patches are not automatically enabled by a normal engine build. |
| Archive-parent reuse (`64be200d28`) | Leave disabled | Isolated extraction improved but full-command cold timing did not. Upstream containerd ownership; no justification for vendoring solely for this workload. |

[#14181](https://github.com/dagger/dagger/pull/14181), the reserved cache floor
fix, is related but **not included in this branch's delta**. It may prevent
repeated eviction on space-constrained machines. It does not explain fresh
volume latency on this approximately 53%-full device.

## Existing work to build on

Erik Sipsma's remote-cache foundation, transfer, lazy acquisition, offers and
local snapshot-sharing PRs are already merged and included in the rebase:
[#14224](https://github.com/dagger/dagger/pull/14224),
[#14228](https://github.com/dagger/dagger/pull/14228),
[#14229](https://github.com/dagger/dagger/pull/14229),
[#14233](https://github.com/dagger/dagger/pull/14233), and
[#14235](https://github.com/dagger/dagger/pull/14235).
His open [#14241](https://github.com/dagger/dagger/pull/14241) adds verification,
fixtures and CI. We should use those facilities to measure remote-hit cold
behavior, rather than implement another result cache. These local benchmarks
do not use remote result caching. A remote hit can remove a build while still
requiring local materialization of a demanded compiler/runtime filesystem.

Yves Brissaud is `eunomie`. [Go SDK #35](https://github.com/dagger/go-sdk/pull/35)
moves generation out of its optional runtime, but that runtime still compiles
source. Static type discovery is a distinct change:
[Go SDK #36](https://github.com/dagger/go-sdk/pull/36) (Solomon) and
[Java SDK #19](https://github.com/dagger/java-sdk/pull/19) (Yves) use generated
Dang entrypoints. Adopt that common contract instead of inventing another
schema format or scanner. [Python SDK #33](https://github.com/dagger/python-sdk/pull/33)
offers shared/generated entrypoints; its current shared `types()` still runs
installed Python code. Test the selected mode before claiming no-runtime
metadata discovery.

Yves's [#14299](https://github.com/dagger/dagger/pull/14299) and
[#14346](https://github.com/dagger/dagger/pull/14346) preserve client-input
invalidation and owning-module boundaries. They are correctness requirements.
Their per-call host-tree work deserves measurement on large trees, but removing
it without equivalent freshness/authority would make a fast stale result.
Exact PR pins and detailed source-review notes are archived with the evidence.

## Measurement rules

The main workload is the full new CLI process running `dagger check -l --all`
on Kyle's greetings-api, including exit and telemetry. The 14 expected rows are
checked byte-for-byte. Application source edits must change the expected test
names; restoring source must restore the original output. No command is
replaced by a narrower listing to improve its score.

Measurements distinguish ready-engine/empty-local-volume cold, warm, and the
first command after an edit. Host page caches are retained in the cold test;
engine/image provisioning and pull are outside that timer. Profiling and builds
run outside timed series. CPU, overlapping spans and I/O pressure are not
additive components of elapsed command time. All new engine comparisons use
the same complete experimental stack documented in the post-rebase report.

## New measured results

These comparisons each use their own matched controls. Do not add their gains
or compare small differences between separate series as if they were paired.

| Experiment | Matched baseline | Candidate | Decision |
| --- | ---: | ---: | --- |
| Batch grouping, 10,000 keys, eight pairs | 172.196 ms | 16.182 ms | Commit the request-local membership index. This is a scaling gain, not a greetings listing claim. |
| Bulk immutable function metadata, eight real listing pairs | 2.131 s | 2.284 s | Do not enable: large-object microbench gain does not improve this consumer. |
| Local Go module path normalization, eight warm pairs | 2.6304 s | 2.5464 s | Preserve as an upstreamable module patch; no edit gain established. |
| Dang directive retention and discarded schema-function work, eight warm pairs | 2.5197 s | 2.5236 s | Semantics tests pass; full-command latency is flat. Do not claim a wall-time gain. |
| TypeScript static registration proof, eight warm pairs | 2.6433 s | 2.1319 s | Real gain; fixture-only implementation must become a generic SDK generator feature. |
| Durable local telemetry handoff, eight triples on that TS prototype | Direct: 2.1430 s; synchronous relay: 2.1388 s | Async relay: 1.6487 s | About 494 ms less CLI wait; delivery continues after exit. Prototype only. |
| Instrumented relay follow-up, eight balanced pairs | Sync: 2.1887 s, 49 requests | Async: 1.6345 s, 94.5 requests | 554 ms faster CLI exit, 1.93× requests; ten-command async block accumulates backlog. |
| Application edit → paired check, five alternating pairs | 11.446 s | 3.559 s | 68.9% less with standard compiler/download cache mounts on the actual backend builder. |
| Same backend cache change, unchanged warm checks | 2.242 s | 2.226 s | Effectively unchanged: immutable results already hit. |
| CLI source-prefix shortcut plus workspace reuse, eight triples | 2.351 s | 2.410 s | No full-command gain established. Commit workspace reuse for the proved redundant catalog removal; leave prefix prototype separate. |
| Overlap engine/CLI telemetry shutdown, eight warm pairs | 2.6236 s | 2.4764 s | Reject this implementation: a deterministic late-record test demonstrates telemetry loss. |
| Go compiler scratch on tmpfs, cold slow-disk pair | 42.540 s | 42.913 s | Leave disabled. |
| Same scratch experiment, cold quiet-disk pair in reverse order | 26.735 s | 26.127 s | No stable gain across disk regimes. |

### Batch construction: an actual complexity improvement

Commit `627f60eb28` replaces repeated scans of accumulated collection keys with
an ordered slice plus a request-local membership map. Small groups scan at most
eight keys before promoting to a map. Key deduplication becomes expected O(K)
overall rather than O(K²), retaining output order, parent separation and
source immutability. No collection answer is cached across requests.

The eight-pair median at 1,000 keys improves from 2.991 to 1.609 ms. Singleton
allocation counts are unchanged (1,977 bytes, 13 allocations), with timings
1.551 versus 1.560 µs. Ten keys incur a small promotion cost: 15.645 versus
16.318 µs. At 10,000 keys the overall Batch benchmark improves 10.64×. Focused
tests cover duplicates on both sides of promotion and independent parents.
A coarse `artifact.batch` wcprof boundary makes the real execution cost visible.

### Another quadratic builder exists, but its first consumer does not win

`ObjectTypeDef.WithFunction` clones member slices and scans existing functions
on each addition. A bulk immutable builder reduces 1,000 distinct appends from
42.007 ms to 0.463 ms in a focused microbenchmark, and allocates 0.566 MB instead
of 52.844 MB. It preserves earliest-match replacement by normalized/original
name, ownership and input order. Its temporary indexes are discarded before
publication. Tests cover alias collisions, randomized equivalence and GraphQL
dependency retention after the producer session ends.

The first real engine consumer batches function replacements during object
namespacing. Eight alternating full listings give **2.131 → 2.284 s**; it is
not enabled. Additional counts-only profiling explains why the synthetic case
was a poor predictor: this workload executes just 17 replacement groups, with
1–18 functions each, 104 replacements total. It replaces existing members
rather than constructing a 1,000-method object from empty.

Publication count falls 2,074 → 1,997 in separate captures, yet the observed
engine span remains 1.409 versus 1.430 s. Reduced summed nested span time is
not reduced critical-path time. The larger builder remains a scaling opportunity
for an appropriate consumer; this evidence does not justify shipping the tested
namespacing change as a discovery speedup.

### Module work: avoid crossing the runtime boundary for string manipulation

`GoMod.nestedRoots` explicitly calls `gomod.workspaceRootPath` for each root.
That enters the module runtime to perform path normalization. A private helper
receives the already-resolved cwd and performs the same operation locally;
the public method delegates to it without changing its API.

On matched local copies of Kyle's Go module, the profile drops from 21 to 18
Dang invocations and from three `workspaceRootPath` calls to zero. The eight
warm pairs save about 84 ms median. Comment/rename/restore measurements do not
establish an edit speedup, so this is not presented as one. Existing discovery
and lookup checks, including nested-cwd behavior, pass.

### SDK dead work: useful cleanup, no demonstrated command gain yet

Dang already owns the evaluated object type. Retaining its annotations there
allows the engine to remove its second source parse/AST-clone pass for object
directives. Separately, schema loading constructs function values for object
fields that it immediately discards; only Query fields need that particular
eager conversion. Object method dispatch retains its existing lazy path.

Targeted ownership, directive and dispatch tests pass; original directive
handling fails the new metadata tests. Nevertheless, the matched full-command
median remains effectively unchanged. Aggregate phase time is not equivalent
to time saved on the critical path. The engine workaround must remain until
the annotation fix is available in the Dang dependency. Existing
`TestCollections/TestSDKs/dang` and all six `TestDang/TestDirectives` integration
cases pass on the combined candidate. The directives suite must run from
`core/integration`, where its relative testdata directory lives.

### TypeScript: generated metadata should not require a language runtime

The existing TS analyzer and emitter already generate literal TypeDefs in
`__dagger.entrypoint.ts`. Delivering them still boots the SDK and user runtime.
The isolated proof delivers the same frontend definitions through the existing
Dang entrypoint driver while preserving TypeScript runtime execution for calls.
The two actual Node `exec.processRun` operations (733–734 ms each, overlapping)
disappear. `Workspace.artifacts`' first query drops from 1,070 to 630 ms in the
separate captures. These spans are not additive command savings.

The matched eight-pair full-command median improves by 511 ms, from 2.6433 to
2.1319 s. Both configurations include the earlier experimental SDK stack and
the otherwise-flat Dang cleanup. All 14 listing rows are identical. Original
frontend field access and `build entries` calls return identical results,
exercising the retained TS constructor, dispatch and serialization.

| Real edit, three observations per variant | Control median | Static metadata median |
| --- | ---: | ---: |
| Comment only | 3.047 s | 2.558 s |
| Rename a test | 2.748 s | 2.429 s |
| Add a test | 2.832 s | 2.582 s |
| Restore source | 2.823 s | 3.259 s |

The restore regression remains in the evidence. This small edit series does
not establish a uniform improvement or a 500 ms loop.

This proof is intentionally not a production engine feature: it has a
fixture-specific schema and a conservative 19-file, 5.66 MB freshness guard.
Changed/added inputs are rejected instead of returning stale definitions.
The guard plus scope preparation takes about 78–79 ms and Dang evaluation
48–53 ms per registration in these captures. Upstream work must extend the
existing `TypedefModule` emitter for arbitrary modules and use the common SDK
entrypoint contract, preserving constructors, enums/interfaces, defaults,
pragmas, source maps and dependencies. A private Kyle-specific engine path is
not an acceptable implementation. Automatic metadata regeneration on API edits
is a separate missing capability, not something this manifest solves.

A second prototype now extends the existing TypeScript generator's
`TypedefModule` representation to emit Dang definitions for arbitrary modules;
it does not add another source parser. Four focused tests with two fixture
subtests pass, covering enums, interfaces, lists, defaults, pragmas, collections
and API edits. The generated Dang parses, and both generator and SDK runtime
compile. This is generator validation, not a measured generic engine release.

The remaining freshness contract matters: a module-local source hash omits
dependency API changes, and the SDK can rewrite configuration/generated files
after code generation. Rejecting every ordinary body edit is not an acceptable
user flow. On invalidation, the existing SDK code-generation path must provide
both fresh metadata and matching executable dispatch. Updating only TypeDefs
could list a new API while running stale dispatch code. The fixture engine and
the generator prototype remain separate evidence until that fallback is wired
and tested end to end.

### Telemetry: producer lifetime comes before an early return

The first shutdown-overlap prototype saves roughly 147 ms, but closes the local
telemetry stream before all accepted work has finished producing records. A
test drives the actual shutdown handler and stream subscriber, then emits a
late record during the Cloud wait. The retained implementation delivers it;
the prototype loses it. Passing listing output and ordinary shutdown tests was
not enough. This implementation remains an archived rejected experiment.

A durable local exporter is a different proposal: the CLI can return after
another live process has durably accepted responsibility for delivery. It must
retain retry/order semantics, recover after a crash and expose terminal failures.
Its command-return latency and eventual Cloud delivery latency must be reported
separately. Merely launching a goroutine in the exiting CLI does not provide
that ownership transfer.

The implemented local relay persists mode-0600 records in a private spool,
syncs the file and directory, then acknowledges the exporter. A separate
process owns retry and eventual delivery to the same original Cloud endpoint.
It preserves export IDs, orders each writer, applies backoff across workers,
caps pending bytes, and retains terminal rejection evidence. Eighteen focused
tests pass with the race detector, including filesystem faults and partial
OTLP rejection. This prototype is independent of module language.

The live process-crash test stops outbound delivery, runs the actual listing,
kills the relay, and compares only file count/size with immutable recovery
counters. All 99 persisted records are recovered. An additional live export
arrives after the checkpoint; final counters show 100 accepted and 100
delivered, no pending bytes, rejection or storage error. This proves recovery
from this process crash, not physical power-loss durability.

Eight balanced triples compare direct export, a synchronous relay and an
asynchronous relay, all on the same static-TS candidate and full command.
Medians are 2.1430 / 2.1388 / 1.6487 s. Thus persistent connections and the
local reachability probe alone show no useful gain here; durable handoff saves
about 490 ms against the matched synchronous relay. The output remains exact.

Separate synchronization profiles put engine shutdown wait at 453 ms direct,
476 ms synchronous relay and 14 ms async relay; CLI OTel close is 125 / 85 /
10 ms respectively. These are individual profile observations, not an additive
decomposition of the medians. They locate the removed wait at the expected
delivery boundary.

However, the async queue has another **3.147 s median observed drain wait** after
the CLI exits. The harness begins that wait after its post-exit stats read; it
is not an exact exit-to-reception timestamp. Each trial drains before the next
command; this first series does not measure a sustained developer-loop backlog. Cloud HTTP
acceptance is measured, not completed search/index visibility. Credential
refresh, daemon lifecycle, failure reporting and throughput remain production
requirements. Raw spool contents and credentials are never archived.

A second relay binary adds integer request/byte, signal, connection and queue-age
counters; twenty race-tested cases pass. After explicit user approval, its
forty-command follow-up completed: four warmups, eight balanced sync/async pairs,
then ten consecutive commands per mode without an inter-command Cloud drain.
The engine, fixture, CLI and original Cloud destination remain the same as in
the preceding trial. All forty outputs match; no extra CLI calls were made.

| Eight isolated pairs, medians | Synchronous relay | Durable asynchronous relay |
| --- | ---: | ---: |
| Complete new CLI process | 2.1887 s | 1.6345 s |
| HTTP export requests per command | 49 | 94.5 |
| Encoded request-body bytes per command | 2,228,274 | 2,262,939 |
| Log requests per command | 19 | 60 |
| Additional observed drain wait | 0.321 s | 3.962 s |

The CLI saves **554 ms (25.3%)**, while requests increase **1.93×** and encoded
body bytes increase only 1.6%. Most additional calls are log requests. The source
mechanism is consistent with these counters: rapid durable acknowledgement
removes the accumulation time provided by an in-flight remote HTTP request.
This is measured request amplification, not a proportional increase in useful
telemetry. Request-body bytes exclude headers and transport overhead.

| One ten-command block per mode | Synchronous | Asynchronous |
| --- | ---: | ---: |
| Time through the last CLI exit | 23.260 s | 16.387 s |
| Additional observed drain wait | 0.426 s | 9.753 s |
| Whole block through drained/stable observation | 23.890 s | 26.348 s |
| Final post-exit sample: pending requests | 0 | 314 |
| Final post-exit sample: pending spool bytes | 0 | 9,856,241 |
| Oldest pending request in that sample | 0 | 6.738 s |

The async post-exit queue samples are **65, 97, 124, 151, 177, 204, 228, 253,
284, 314**. Delivery catches up only after the commands stop. In this block,
earlier CLI completion therefore comes with later completion of remote delivery.
The synchronous block ran first; a single block per mode is order-confounded
and ten commands do not establish steady-state capacity. Growing pending count
and age do establish backlog over this observed serial developer loop.

The harness's `relay_at_exit` is sampled after process exit and a local stats
request; it is not an instantaneous exit snapshot. Its drain-wait timer starts
after that bookkeeping and subtracts a 200 ms stability window. The complete
block duration includes bookkeeping and that final window, and is the stronger
end-to-end boundary. Neither measurement establishes Cloud UI/search visibility.
Synchronous `Pending=0` describes the absence of a durable queue, not absence
of active HTTP exports: its post-exit snapshots can still contain 1–2 requests
in flight. The actual last-CLI-exit to drained/stable observation is 0.630 s
synchronous and 9.961 s asynchronous, including the observation window.

Connections were reused for every request in both measured burst blocks, with
zero new TCP/TLS setup recorded. Request-to-response-header time averages about
114 ms synchronous and 98 ms asynchronous. Setup is not the dominant observed
cost; these client counters cannot separate network RTT from server processing.
Parallel request-duration sums must not be added to CLI wall time.

Finally, **1,864 asynchronously accepted requests were delivered**, the queue
and pending bytes reached zero, and all recorded HTTP responses succeeded.
There were no retries, terminal/storage/transport errors or partial-rejection
errors. The owned relay was stopped after drain. Counter equality establishes
the measured handoff/delivery accounting, not global exactly-once delivery.
The [complete follow-up and raw counters](collections-qa-performance-data/next-bottlenecks/telemetry-relay/load-v2/report.md)
supersede the earlier approval-blocked status; this packet-spooling prototype
is still not a sustainable production solution at the observed offered load.

A local, deterministic experiment does validate one possible source of request
amplification. The payload processor normally coalesces for 5 ms; a fast local
acknowledgement can prevent records from accumulating behind a slower HTTP
export. An isolated option keeps local delivery at 5 ms and gives only Cloud
the existing 100 ms log/span interval. Forty synthetic records spaced 11 ms
apart produce **40 → 4 export calls**, with identical delivery. Existing and
new processor tests pass, including immediate explicit flush/shutdown, ordering,
batch bounds and unchanged retry backoff.

This is a modeled request-count result, not measured Cloud throughput or command
latency. Cloud payload visibility can be delayed another 95 ms, and a wider
window could move work into the final synchronous flush. The
[coalescing prototype](collections-qa-performance-data/next-bottlenecks/cloud-coalescing/README.md)
remains isolated until live comparison and Cloud UX validation justify enabling it.

The follow-up source review also shows why a universal 100 ms default is not
justified: a short direct-to-Cloud command can lose useful overlap and defer its
only request into final shutdown. A durable queue of records in the engine can
instead form bounded remote batches after local durable acceptance, while the
current packet spool preserves its already-small requests. That architecture
still needs persisted acknowledgement cursors, GC pins, credentials and producer
completion; it is not a detached goroutine or an existing durability guarantee.
See the [delivery and batching review](collections-qa-performance-data/next-bottlenecks/cloud-coalescing/correctness-review.md).

Independent local tests found another prototype defect: always selecting from
the start of the writer list can starve later writers. A separate rotating-cursor
patch fixes selection fairness while preserving each writer's FIFO and the
four-worker limit. The frozen measured version fails the gated regression; the
candidate passes the full fake-transport suite and three race-enabled repetitions
of the fairness tests. This [isolated correction](collections-qa-performance-data/next-bottlenecks/relay-fairness/README.md)
does not change the measured binary or prove that it fixes request amplification
or capacity. No additional live Cloud calls were made for it.

### Cold disk variability: deferred writes are not eliminated writes

The tmpfs scratch experiment runs four new engine volumes, reversing order.
Both variants take about 42–43 s under disk pressure and 26–27 s in the quiet
regime. All twelve cold/warm commands retain the exact listing. This does not
support changing the Go SDK default.

One candidate run appears to write 744 MiB less before exit, but ends with
740 MiB more dirty memory. It deferred writeback. Device writes plus net dirty
pages are approximately 1,977 / 1,971 / 1,975 / 1,983 MiB across the four runs;
this host-level cross-check is not precise per-command I/O accounting, but it
rules out the apparent halving of writes. Eliminate unnecessary compilation
and materialization first; don't trade correctness or memory headroom for an
attractive partial counter.

Static TypeScript metadata was also tested with fresh engine volumes. A clean
static/control/control/static sequence gives **36.13 / 46.04 / 26.65 / 25.45 s**.
The low-stall matched pair improves by 1.20 s, or 4.5%; it is only one pair.
The slower pair has unequal engine I/O-full stalls, 5.61 versus 14.11 s, so its
larger wall-time gap cannot all be credited to the code. The same control varies
26.65 → 46.04 s while its I/O-full pressure rises 0.082 → 14.108 s. All twelve
cold/warm outputs are exact. A separate initially contaminated run is retained
and explicitly excluded from the primary comparison.

This cold boundary starts with a ready engine and empty local volume; host page
cache is retained and remote result caching is disabled. Distributed cache can
avoid matching computations, while required snapshot transfer/materialization
still does I/O. It cannot be assumed to remove the measured storage stalls.

## What remains on the real critical path

With static TS registration, one profile still has a 630 ms module-discovery
query followed by a 745 ms expansion query. The latter contains roughly
266 ms of backend constructor/configured-base resolution, 290 ms of Go module
discovery and up to 120 ms of test discovery. Those nested/overlapping values
must not be summed as independent whole-command savings.

Two architectural candidates follow directly from those observations:

* Defer typed execution inputs until used. `UserDefault.Value` currently
  evaluates `Address.container` to obtain an ID, forcing the configured
  `backend/go-test-base` even when discovery only needs source. The solution
  must preserve the Container-typed argument, source invalidation, workspace
  authority and eventual service binding. Removing Kyle's base setting would
  change the workload and is not an optimization.
* Pipeline independent module loading and expansion. The current loader holds
  `client.modulesMu` across its parallel resolve batch and publishes only after
  every job finishes. Starting constructors under that lock can deadlock when
  a configured input resolves another module. A useful change needs explicit
  dependency readiness and safe publication; merely merging GraphQL requests
  does not remove the barrier.

CLI diagnostics on the static-TS fixture find approximately 1.9 ms loading
default labels, 58 ms starting the engine connection, 38 ms starting the
session and 2.6 ms subscribing to telemetry. Ten underlying source walks each
visit about 6,400 entries and take 9–16 ms. These are instrumentation samples,
not unprofiled medians. The earlier 220 ms Git-label measurement in a different
checkout does not describe this workload. Repeated source snapshots deserve
attention, but a TTL or mtime-only shortcut would invalidate the edit proof.

Commit `0b6a16f400` reuses the command's pinned workspace for selection, flags
and output while retaining global alias ambiguity rules. The comparison profile
removes one redundant `Workspace.artifacts` call (18.45 ms in that capture).
Eight full-command triples are flat/noisy: baseline 2.351 s, filesystem-prefix
prototype 2.353 s, prefix plus workspace reuse 2.410 s. No whole-command win is
claimed. Only workspace reuse is committed; the separate path-prefix shortcut
remains an unadopted prototype. Nested, filtered and ambiguous dimensions have
focused regression coverage.

## Generality and execution coverage

Kyle's repository is the realistic reference workload. Production candidates
must also preserve generic module behavior: SDK language, collection size,
nested dimensions, ambiguous flags, filtered selections and edits. The Batch
index and telemetry ownership work have no Kyle-specific dependency. The TS
sidecar proof does, and therefore remains a measurement fixture until a common
generator can emit it for arbitrary modules.

The execution matrix uses the current check path
`go/modules/tests/run`, not the historical thread's `go/modules/test`, which is
an ordinary method at the pinned Go-module revision. It retains Kyle's service
base and covers a selected unit test, a two-test batch, the six-test HTTP suite,
warm result reuse, an ordinary source edit, an intentionally failing selected
test, an unselected passing control and restoration. First execution after a
listing is explicitly distinguished from a fresh engine volume. A listing
speedup cannot stand in for this matrix.

### New baseline: edit application code, then execute a check

This is now a required benchmark alongside listing. Run from the application's
root using a fresh CLI process, for example:

```sh
dagger check --generated=false go/modules/tests/run \
  --go-module=. --go-test=TestFormatResponse
```

The measured source edit appends a comment to the **application's root
`main.go`**, not its test or Dagger module. A separate edit to `main_test.go`
tests failure propagation. `.dagger/modules/backend/main.go` defines the
Dagger build pipeline and is the location of the validated cache fix.

These results use the static-TS prototype engine and original CLI, direct Cloud
export, and Kyle's unchanged configured backend service. All eight warm samples
per selection start a fresh CLI. First execution follows discovery preflights
on a retained engine, so it is **not a fresh-volume cold result**.

| Operation | Full CLI time | Validation |
| --- | ---: | --- |
| First single-test execution after discovery | 40.075 s | Check passes; missing application/tools prepared. |
| Warm single selected test, median of 8 | 2.150 s | Successful result reuse. |
| Warm two-test batch, median of 8 | 2.144 s | One grouped check. |
| Warm all six tests, median of 8 | 2.130 s | First actual full run reports six passed, zero skipped; subsequent runs reuse results. |
| New application comment, immediately run single test | **11.778 s** | Check passes on changed source. |
| Restore application source | 2.350 s | Previously seen content is reusable. |
| Insert fatal sentinel in selected test | 11.261 s | Nonzero exit and expected sentinel. |
| Select the other test while failure remains | 2.665 s | Passes; unselected failure is not executed. |
| Select both tests while failure remains | 2.561 s | Batch propagates the sentinel failure. |
| Restore test source | 2.347 s | Passing result recovered. |

A separate, fresh-comment edited-pair profile takes 11.485 s. Its critical work
contains `go build -o greetings-api .` at **8.150 s**, nested inside
`backend.goTestBase` at 8.28 s. The actual selected `otelgotest` process takes
**411 ms**. These nested durations must not be added. Warm captures contain no
`go build`, `go-includes` or `otelgotest` execution: their fast result is a
Dagger cache hit, not a newly executed test process.

The backend's `goBase` imports the source into `golang:1.26-alpine` without
Go build or download cache mounts. The official Go module mounts its own
caches, but they do not apply to this independent backend builder.

### Validated improvement: cache the compiler's reusable work

The isolated candidate adds four ordinary cache-mount/environment lines to
that backend builder: module download cache at `/go/pkg/mod`, and Go build
cache at `/root/.cache/go-build`. It preserves the image, source, arguments,
service and test selection. Cache names stay stable across source edits; source
revisions must not become cache-volume names.

| Paired check benchmark | Original backend | Backend with compiler caches |
| --- | ---: | ---: |
| Warm unchanged, five pairs | 2.242 s | 2.226 s |
| Five distinct application comments → check, median | **11.446 s** | **3.559 s** |
| Edit range | 11.351–11.736 s | 3.353–3.671 s |
| Actual build in a separate edited wcprof capture | 8.217 s | 407 ms |
| Actual paired test-runner process in those captures | 429 ms | 380 ms |

All five edit pairs improve: **68.9% less full-command time**. Each timed
invocation runs the ordinary command with both `TestSelectGreeting` and
`TestFormatResponse` selected. The candidate's initial empty dedicated-cache
fill takes 13.554 s on a retained engine. That is deliberately excluded from
the warmed edit median and is not a fresh-engine cold comparison.

Correctness changes the application's `FormatResponse` to append a sentinel,
then runs the HTTP E2E check. Both control and candidate fail with the changed
response. Restoring behavior with another distinct source comment makes all
six tests pass, zero skipped, on both versions. The source edit still triggers
the build and tests; the compiler reuses valid internal work.

This uses Dagger's normal distinction between immutable exec results and
mutable compiler caches. A previous exec's output filesystem does not become
the input filesystem for a new source-backed exec. Explicit compiler cache
volumes bridge that gap. The change is suitable for the backend module recipe,
and the principle applies to other language toolchains. It is not a reason for
the engine to guess a language and inject mounts into arbitrary containers.

The benchmark, exact patch and invalidation evidence are in
[the backend cache report](collections-qa-performance-data/next-bottlenecks/backend-go-cache/report.md).
Original fixture hashes are unchanged; the patch is applied only to the
isolated candidate. The remaining ~3.56 s still includes actual compilation,
tests, service startup, module work and telemetry. The 500 ms target remains open.

An audited next candidate is constructor-only caching. The backend constructor
only stores its explicit content-hashed source, but build/service methods resolve
a mutable image tag. A blanket module-cache opt-in would alter that freshness
contract. The source-only proposal retains explicit session policies for all
five exported body functions; committed Go registration metadata must first be
regenerated and checked. It is unmeasured, with independent Go/TypeScript/Dang
source-invalidation fixtures proposed in the
[constructor audit](collections-qa-performance-data/next-bottlenecks/constructor-cache-audit/report.md).

## Reproduction and evidence

The reference execution driver runs in an isolated workspace copy, restores
edited files in `finally`, and defaults to a dry run. The original pinned app
and configured services remain intact. With a prepared, exclusively assigned
engine, the recorded matrix can be repeated using:

```sh
python3 hack/collections-qa-performance-data/next-bottlenecks/execution/benchmark.py \
  --app /path/to/pinned/greetings-api --cli /path/to/measured/dagger \
  --engine dagger-engine.my-perf --output /tmp/execution-new-run \
  --profile-port 6172 --include-full-module --run
```

The profiling port must belong to that engine. Engine preparation is outside
the timer; this command does not reset caches. Use the recorded cold driver
with a new engine volume when measuring that boundary. Timing samples exclude
profiling; profiles are captured in separate invocations.

* [Actual check execution driver and baseline](collections-qa-performance-data/next-bottlenecks/execution/report.md),
  [raw results](collections-qa-performance-data/next-bottlenecks/execution/measured/results.json).
* [Backend compiler-cache patch and results](collections-qa-performance-data/next-bottlenecks/backend-go-cache/report.md),
  [exact four-line patch](collections-qa-performance-data/next-bottlenecks/backend-go-cache/cache-mounts.patch).
* [TS static metadata measurements](collections-qa-performance-data/next-bottlenecks/ts-static/results.md),
  [generic emitter and freshness contract](collections-qa-performance-data/next-bottlenecks/ts-generic/README.md),
  [fresh-volume cold series](collections-qa-performance-data/next-bottlenecks/ts-static/cold/results.md).
* [Durable relay design, tests and driver](collections-qa-performance-data/next-bottlenecks/telemetry-relay/README.md),
  [engine-native handoff review](collections-qa-performance-data/next-bottlenecks/telemetry-relay/engine-handoff-review.md).
* [CLI workspace reuse](collections-qa-performance-data/next-bottlenecks/cli-workspace-reuse/report.md),
  [module load/expansion barrier review](collections-qa-performance-data/next-bottlenecks/cli-workspace-reuse/pipeline-review.md).
* [Batch-key scaling](collections-qa-performance-data/next-bottlenecks/batch-index-lazy/report.md),
  [Go path-helper change](collections-qa-performance-data/next-bottlenecks/go-module/report.md).

The [archive manifest](collections-qa-performance-data/next-bottlenecks/archive-manifest.json)
records hashes for explicit small source, test and numeric evidence files.
Large I/O sample JSON files use deterministic gzip; the manifest also records
their uncompressed size and hash, preserving every sample without bloating
the source diff. Load them with `gzip.open(path)` or decompress before analysis.
Frozen Go source copies end in `.go.txt` so they do not become packages under
the repository's Go module. The manifest records their original filenames;
remove the final `.txt` when reconstructing an isolated reproduction directory.
Binary profiles and engine executables stay in the lab with recorded provenance;
telemetry payloads, spool contents and credentials are excluded from publication.
