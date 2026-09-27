# Collections performance: current findings

The 500 ms end-to-end target is still open. The latest local experiments put
expanded greetings-api listings near 1.4 s through Docker, or 1.24 s with a
prepared Unix socket. Several smaller commands and native edit loops are already
below 500 ms locally. These use the retained experimental SDK/engine stack and
disable Cloud; they are not production Cloud timings or the result of building
the branch without its experimental artifacts.

## Keep the changes that remove measured work

| Change | Evidence | Delivery status |
| --- | --- | --- |
| Read ancestor metadata directly, without listing siblings | Expanded checks 1.468 → 1.373 s, five observations per arm under a wide ancestor directory; a lower-width control is flat | Engine/CLI commit `0d1c32e29f`, pushed to the performance branch |
| Keep pure Go-module path normalization inside its private helper | Earlier eight-pair warm listing comparison: 2.630 → 2.546 s; discovery and lookup correctness checks pass | Go module commit `93d0f1b5288`, pushed to `grouville/go:perf/discovery-path-normalization` |
| Skip Docker start when the existing inspection reports exactly `running` | Native generation 293 → 280 ms; core wall medians flat at 244 ms; paired process-tree CPU reduced 13–18 ms | CLI commit `e6e723145e`; 32/32 local outcomes correct |
| Replace Docker exec connections with a local Unix connector, retaining Docker admission | `ws ls` 163 → 74 ms; distinct native source edit → check 282 → 182 ms; distinct input edit → generation/full exit 371 → 249 ms | Isolated prototype; automatic endpoint provisioning and platform/access compatibility remain to implement |

The [filesystem report](collections-filesync-performance.md) includes cold,
low-width and mixed-version controls. The [transport report](collections-local-transport-performance.md)
includes all paired samples, output checks, boundaries and upstream requirements.
These gains come from separate matched experiments and must not be added together.
The Go helper is not installed in the fixture used for the latest transport trial.

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

The latest fresh-volume filesystem pair is 24.938 → 24.568 s: insufficient to
establish a cold gain or explain earlier 27–45 s variability. Host image caches,
SDK artifacts and engine startup boundaries are explicit in that report. None of
these local measurements establishes equivalence with Kyle's 29.88 s cold run.
