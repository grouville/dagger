# Collections performance: current findings

The 500 ms end-to-end target is still open. The latest matched local module
experiment reduces expanded greetings-api listings from 1.392 to 1.138 s through
Docker, and a new application comment followed by listing from 1.409 to 1.106 s.
It explicitly defers a configured execution Container through an Address; it is
not automatic in existing modules. Several smaller commands and native edit
loops are already below 500 ms locally. These use the retained experimental
SDK/engine stack and disable Cloud; they are not production Cloud timings or the
result of building the branch without its experimental artifacts.

## Keep the changes that remove measured work

| Change | Evidence | Delivery status |
| --- | --- | --- |
| Read ancestor metadata directly, without listing siblings | Expanded checks 1.468 → 1.373 s, five observations per arm under a wide ancestor directory; a lower-width control is flat | Engine/CLI commit `0d1c32e29f`, pushed to the performance branch |
| Keep pure Go-module path normalization inside its private helper | Earlier eight-pair warm listing comparison: 2.630 → 2.546 s; discovery and lookup correctness checks pass | Go module commit `93d0f1b5288`, pushed to `grouville/go:perf/discovery-path-normalization` |
| Skip Docker start when the existing inspection reports exactly `running` | Native generation 293 → 280 ms; core wall medians flat at 244 ms; paired process-tree CPU reduced 13–18 ms | CLI commit `e6e723145e`; 32/32 local outcomes correct |
| Separate serving nested-session files/sockets from engine provisioning | Heavy helper startup 9.114 → 6.357 ms over twelve pairs; binary shrinks by 6.3 MB; no whole-command speedup established | Commit `fef89b56e0`; normal/race gates, full CLI/engine builds and ten real SDK/check/exec outcomes pass |
| Scope artifact tree construction to selected modules | Repeated Address metadata requests 195 → 18; full warm check median flat, distinct app-comment listing 1.483 → 1.356 s over four observations per arm | Commit `093e161255`; 42 local correctness outcomes and focused normal/race gates pass |
| Let a module retain a configured Address until execution needs its Container | Warm checks 1.392 → 1.138 s and distinct app-comment listing 1.409 → 1.106 s, four observations per arm; two backend executions removed | Generic Address argument fix `36e4939021`; Go module commit `c5e29463b6` on `grouville/go:perf/discovery-base-address`; separate execution/generation gates pass |
| Replace Docker exec connections with a local Unix connector, retaining Docker admission | `ws ls` 163 → 74 ms; distinct native source edit → check 282 → 182 ms; distinct input edit → generation/full exit 371 → 249 ms | Isolated prototype; automatic endpoint provisioning and platform/access compatibility remain to implement |

The [filesystem report](collections-filesync-performance.md) includes cold,
low-width and mixed-version controls. The [transport report](collections-local-transport-performance.md)
includes all paired samples, output checks, boundaries and upstream requirements.
These gains come from separate matched experiments and must not be added together.
The Go helper is not installed in the fixture used for the latest transport trial.

A [targeted artifact-tree pruning trial](collections-qa-performance-data/artifact-static-pruning-runtime/report.md)
removes metadata work before building unrelated trees for a literal module path.
Warm check listing is flat/slightly worse, 1.361 → 1.390 s over four observations
per arm. Distinct app-comment edits give 1.483 → 1.356 s over four observations
per arm, and artifact listing gives 1.377 → 1.320 s over two. These are correlated
ABBA blocks, not a general speedup claim. Separate wcprof captures confirm
195 → 18 TypeDef requests per repeated Address lookup; the three overlapping
lookups shrink from about 32 to 9 ms. Their durations must not be added, and the
profile does not distinguish which tree builder contributed those requests.
All 38 outcomes pass, followed by
[four selected-generator and real-generation controls](collections-qa-performance-data/artifact-static-pruning-generate/report.md).
The prototype keeps loading, entrypoints, pattern fallback and final matching;
its deliberate scope change omits late validation of unrelated already-served
modules, aligning targeted lookup with existing narrowed loading. This is now
commit `093e161255`. The
[expanded normal/race gates](collections-qa-performance-data/artifact-static-pruning-validation/error-scope.md)
exercise a real served empty module, including retained errors for selected and
unfiltered discovery.

The next execution-deferral experiment has an independent engine prerequisite:
commit `36e4939021` fixes configured arguments whose type is already `Address`.
It passes the caller-bound Address ID instead of selecting the nonexistent
`Address.address` field. The
[normal/race and parser gates](collections-qa-performance-data/address-default-validation/README.md)
cover workspace binding, IDs, scalar/list inputs and unchanged eager Container
behavior. An optional Go `baseAddress` setting can then defer its producer until
execution. That module option is not enabled by this engine commit. The
[nine-call correctness proof](collections-qa-performance-data/go-base-address-correctness/report.md)
passes real service consumption, changed-source failures and recovery, identical
listings and the strict greetings HTTP test. Ten retained-session RPCs distinguish
direct NEVER consumption from the ordinary cached outer `GoModule.base` result;
no transitive NEVER policy is introduced. Existing `base: Container` remains eager,
and explicit `baseAddress` moves producer errors to actual consumption.

The [three module-owned GoDev checks](collections-qa-performance-data/go-base-address-module-qa/README.md)
also pass constructor policy, deferred producer failure, required environment and
files, a bound HTTP service, real Go tests, generation and the existing Container
base behavior. Earlier QA setup/inference/proxy-equality mistakes remain recorded
separately. The implementation is pushed as
[`c5e29463b6`](https://github.com/grouville/go/commit/c5e29463b6ddfe95fe2d9c460e5436e3c16adaed)
on `perf/discovery-base-address`, based on upstream `1784ff37`. The final commit
adds a description correction and canonical QA formatting after the passing
checks; its implementation matches the measured candidate. QA image digests stay
pinned. This is an explicit module API option requiring the engine fix for
workspace settings, not an automatic change to existing configurations.

The [28-call module comparison](collections-qa-performance-data/go-base-address-runtime/report.md)
uses one engine and identical local module layouts in correlated ABBA blocks.
Warm expanded checks fall **1.392 → 1.138 s**, unique app-comment listings
**1.409 → 1.106 s**, and artifact listings **1.358 → 1.134 s**. There are four
observations per arm for checks/edits and two for artifacts; all outputs match.
These are local-only full CLI exit times, not actual-check execution gains or
normal remote-module branch timings. Module-owned generation gates are separate
from this comparison.

The subsequent [four first listings on fresh volumes](collections-qa-performance-data/go-base-address-cold/report.md)
give control **25.533 / 29.421 s** and candidate **21.142 / 20.918 s**. Each command
is the first Dagger call on its volume, without a primer; image layers, SDK blobs,
host pages and external caches remain available. Engine readiness adds about
0.25 s outside each CLI interval. Both comparison orders favor the module option,
but two observations per arm are not a stable cold distribution. CPU remains
87–89 CPU-s; these measurements do not establish compilation elimination.
The slower control coincides with 2.99 s of host full I/O pressure, versus
0.12–0.18 s in the other samples. Delayed writeback also shifts bytes outside
the command interval. All four outputs match; fixtures are restored and only the
four newly owned containers and volumes were subsequently removed.

Separate wcprof captures show expansion **600 → 374 ms**, four Address Container
lookups becoming zero, and two authored backend executions disappearing. Runtime
process count falls from six to four. Catalog loading instead rises **499 → 571 ms**
in this profile pair, with seven Git admissions in both; no catalog saving is
claimed. Commit `c1a34a011c` adds fixed tree-construction boundaries: module tree
interval union falls **52.40 → 10.38 ms**, while core tree construction was already
below one millisecond. A core-tree factory is therefore not the next useful
optimization. These savings overlap scoped tree pruning and must not be added to
its result. The [full diagnostic engine build](collections-qa-performance-data/address-default-build/README.md)
contains the Address fix and profiling markers; both comparison arms exclude the
separate pruning, helper extraction, split-init and Unix transport changes.

The [managed-engine comparison](collections-qa-performance-data/managed-engine-start-runtime/report.md)
uses five alternating pairs per flow. It includes the ordinary image driver's
container inspection and start path, with no Unix transport. Paused/restarting
containers, unknown status and non-Docker backends retain their previous start
behavior. Two stopped-engine controls resume successfully through the CLI. The
running-state observation is not an atomic guarantee against an external stop.

The direct metadata lookup changes ancestor work from sibling-dependent enumeration
to work proportional to path depth. It still reads the filesystem freshly. The Go
helper removes runtime/API round trips for a pure calculation. The connector removes
process launches. None introduces a TTL or a cache of workspace results.

## Experiments that did not justify integration

- Shared HTTP transport, including an improved shutdown schedule, regresses native
  generation in the matched trial. It remains isolated.
- Giving module-source resolution and registration separate concurrency limits
  starts the ninth source about 147 ms earlier in a wcprof capture. Actual warm
  check listing remains 1.382 → 1.389 s, and distinct app-comment edits remain
  1.426 → 1.436 s. All 42 outcomes pass, but the work moved is largely outside
  the critical path. Keep the existing scheduler.
- A [bounded Git v0/v2 comparison](collections-qa-performance-data/git-advertisement-v2-v2/report.md)
  transfers 96.5% fewer response-body bytes with v2, but shows no consistent
  response-wait improvement. Reference parsing is already below 0.6 ms. This
  host HTTP/1.1 trial does not justify a new engine admission protocol.

## The remaining larger costs

The [current catalog/expansion audit](collections-qa-performance-data/address-catalog-overlap/report.md)
finds a 571 ms catalog, a 43 ms handoff and 374 ms expansion in the separate
Address-candidate profile. Current root-load markers do not identify which
module became ready first; they cannot yet quantify a Go-specific overlap gain.
The final root resolves only 18 ms before catalog completion. Before removing
the batch barrier, measure named module readiness and preserve global validation,
entrypoint arbitration and nested workspace visibility. Speculatively executing
a NEVER collection before a later catalog error is a behavior change.

A smaller candidate is to append the hidden listing projection to the existing
SDK selection, eliminating its explicit ID request followed by a second request
for rows. The 43 ms gap is only an upper bound on that handoff, not a promised
saving. This keeps catalog-before-enumeration ordering and is being prepared
independently of dynamic overlap.

Two fully primed wcprof captures show roughly 385 ms of Git request-write to
first-byte waiting, using seven already-open connections. Local reference sorting
and validation total less than 0.5 ms. A faster map will not remove that network
wait. Any protocol experiment must preserve fresh repository admission, ref
semantics and fallback behavior.

Registration and module execution still launch runtime processes. Two Go calls
spend 58–67 ms between the runc monitor starting and the first dispatch query;
that includes container, init, language and nested-client startup. It is not a
measurement of the authored function body. The next prototype separates a small
PID1 program from the dependency-heavy attachables program, preserving their
process boundary and child-reaping behavior. Focused normal/race tests and a real
PID1 namespace/reaping test pass. In twelve alternating host-process pairs, startup
and exit with no selected command fall from 10.019 to 1.471 ms. This is a causal
startup witness, not a full Dagger command or a prediction of its saving. The
[source, correctness gates and startup measurements](collections-qa-performance-data/split-init-source/result-report.md)
record the exact binaries and remaining integration requirements. The subsequent
[ten integration/setup calls](collections-qa-performance-data/split-init-smoke/report.md)
pass real Go, TypeScript, Python, changed-test and ordinary-exec checks, including
the mounted init binaries. First SDK preparation is explicitly excluded from warm
comparisons. The first [36-call whole-command comparison](collections-qa-performance-data/split-init-runtime/report.md)
is mixed: warm checks fall from 1.423 to 1.346 s, while the two artifact observations
per arm rise from 1.405 to 1.479 s. The distinct-comment comparison is nearly flat.
All outcomes are correct, but the separate profiles do not attribute the check
gain to PID1 startup.

The subsequent [40-call confirmation](collections-qa-performance-data/split-init-confirmation/report.md)
finds artifact listing flat at 1.409 → 1.407 s, and first-seen app-comment listing
at 1.459 → 1.423 s, with six observations per arm. Fresh native generation again
improves, 399 → 357 ms full exit and 377 → 332 ms until the file is visible, with
two observations per arm. All outcomes and restoration checks pass. These are
correlated ABBA block observations, not independent randomized engine pairs.
The confirmation does not reproduce the artifact regression, but neither does it
establish a general discovery improvement. Keep the prototype isolated pending
platform, service/TTY and helper-mount compatibility gates; the implementation
also needs to share its PID1 code rather than maintain two copies.

The [source refinement](collections-qa-performance-data/split-init-refinement/report.md)
now shares one PID1 implementation and mounts the heavy session helper only when
nested-session setup or an explicit session token needs it. Ordinary execs keep
one injected mount; NoInit keeps none. Normal/race mount and process tests pass,
as does a separate isolated PID-namespace reaping and controlling-terminal gate.
This revision is still isolated: real SDK/service execution and packaging remain
to validate, and its changed mount topology has no whole-command measurement.

An [admission-order audit](collections-qa-performance-data/admission-order-audit/lock-graph-review.md)
found no safe dependency-prefetch shortcut in the existing lock file: it records
resolutions, not dependency reachability, and can contain unused historical refs.
Freshly admitted parent configurations determine which dependencies are relevant.
An [explicit reusable session](collections-qa-performance-data/admission-order-audit/reusable-session-note.md)
could change that lifetime deliberately, but must give each command fresh workspace
and environment state and define service/telemetry completion. An ordinary
`with-session` wrapper does not prove those semantics.

The [SDK/cache PR review](collections-qa-performance-data/upstream-review-2026-09-26/review.md)
keeps static SDK entrypoints in the existing upstream work and preserves dynamic
input and client-tree invalidation. Remote cache may avoid cached producer work;
it does not by itself eliminate local process startup, session admission or Cloud
completion. That distinction needs measurement on the eventual combined stack.

The existing Go SDK #36 JSON-contract adapter now passes its
[focused template and contract gates](collections-qa-performance-data/go-sdk-pr36-validation/report.md),
including race checks and both the upstream and engine's Dang versions. This is
not a completed engine migration or a performance comparison. Two
[real-fixture attempts](collections-qa-performance-data/go-sdk-pr36-failed-proofs/failed-proofs-report.md)
each stop after three calls: control generation and JSON/core-object dispatch
pass, then candidate generation fails. The first failure was an absolute SDK
reference in the harness; the corrected relative reference reaches the current
engine's SDK contract and exposes missing `findClientRoot` and `generateScope`
hooks. Both trials restore all resources and send no Cloud requests. A scoped
compatibility adapter subsequently reached the full SDK compile gate and exposed
two more obsolete core APIs: `CurrentModule.asSDK` and
`ModuleSource.generateLocalDependencies`. The
[compatibility report](collections-qa-performance-data/go-sdk-pr36-contract/compatibility-report.md)
also records a syntax error in our experimental bridge separately from those
upstream API differences. This migration is now parked; porting the complete SDK
would overlap the existing upstream effort. No candidate runtime-generation or
performance result was established.

The real-fixture
migration must be backend-only: the v2 manifest cannot replace the existing
dependency-bearing greetings module transparently. Preserve its session cache
policy through generated metadata, and compare both loaders' API changes before
and after generation. Live application-test discovery remains a separate gate.

A separate, committed startup change separates serving an existing session's
files and sockets from provisioning an engine. The
[attachables package extraction](collections-qa-performance-data/attachables-extraction/result-report.md)
removes 373 transitive packages from the nested helper and preserves the old
client's exported aliases. Five focused normal/race gates and both helper builds
pass. Twelve paired host-process starts measure 9.114 → 6.357 ms; the helper
shrinks by 6,295,552 bytes. This uses the original combined PID1/helper, without
the split-init prototype. The subsequent
[ten real SDK/session gates](collections-qa-performance-data/attachables-extraction-runtime/report.md)
pass Go, TypeScript, Python, changed-check and uncached-exec behavior. Full CLI
and engine consumer builds also pass. The extraction is committed as
`fef89b56e0`; the new Unix socket witness is restricted to Unix. It is not a
measured whole-command or cold-start gain. Reflected concrete Go type package
paths change even though ordinary source API use is preserved.

The latest fresh-volume filesystem pair is 24.938 → 24.568 s: insufficient to
establish a cold gain or explain earlier 27–45 s variability. Host image caches,
SDK artifacts and engine startup boundaries are explicit in that report. None of
these local measurements establishes equivalence with Kyle's 29.88 s cold run.
