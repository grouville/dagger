# Own the Dang nested HTTP client's transport

## Problem and causal evidence

Ordinary standalone Rust checks sometimes took over six seconds even when the
Cargo action was an exact cache hit. Complete wcprof OTel captures localized
5.8–5.9s to opaque `Rust.check` self-time, after its nested queries completed.
The earlier [module experiment](project-toolchain-results.md) retained these
outliers rather than claiming its median was the whole user experience.

A temporary connection-state diagnostic on the real engine confirmed the
shutdown boundary. In an identical-configuration 30-command diagnostic loop,
one check took 6285.589ms. Its complete trace had 169 operations, one root,
154/154 declared spans, no missing/open/orphaned spans, unresolved waits or
dropped links, and replay drift rounding to -0.0%. Process boundaries were
27.335ms before the root, 6249.092ms inside, and 9.163ms afterward. There was no
Cargo execution.

The matching server shutdown started with one `StateNew`, zero `StateActive`,
and one `StateIdle` connection. The unused new connection was 30.414ms old.
`Server.Shutdown` itself took **5.802325612 seconds**, returning with nil error.
Its immediate post-return state snapshot still showed the new connection aged
5.833s: the asynchronous `ConnState(StateClosed)` callback had not yet run, so
this diagnostic does not claim to have observed that callback.

This matches Go's graceful-shutdown behavior: a new connection gets five seconds
to send its first request before the server can treat it as idle. Concurrent
HTTP requests can reuse a newly idle connection while another dial completes
unused. The old code used a process-global HTTP client for an invocation-local
server, leaving that unused client connection open during server shutdown.

Local diagnostic evidence (not headline before/after timing):

- Engine: `sha256:c3f9ffa84ee337399e193fd46b3a6f42115afee95a44a281f0437c235970b32c`.
- Parent: `21671ac5ff8f006ed04572a1b58afa59b924e199`, plus the diagnostic patch.
- Patch: `/tmp/dagger-rust-nested-shutdown-diagnostic.patch`, SHA256
  `6f3fc9224945bd0e41aaf84d406d56567ea7ea76e9a600eda3698cf3f1ef7461`.
- Run: `/tmp/dagger-rust-cli-pair-yb8zqmr9`, slow label `before-4`.
  Both labels use the same configuration; label medians are not an A/B result.
- Trace: `94c543a9b9fb8edadf086b933f4fa4bf`, extracted artifacts
  `/tmp/dagger-rust-nested-diag-slow-{trace.jsonl,boundaries.json,analysis.txt,gate.txt}`.
- Engine log: `/tmp/dagger-rust-nested-diag-engine.log`, matching
  `DANG_SHUTDOWN_PROBE` records at 2026-09-11 01:56:10.338640280 UTC and
  01:56:16.141234926 UTC. Diagnostics are removed from the candidate.

## Change and ownership

Each nested invocation now owns a clone of the default HTTP transport and gives
that transport explicitly to its GraphQL client. On callback completion it
closes only its own idle connections and cancels unused in-progress dials,
before the existing graceful server shutdown.

The invocation-local helper extracts the existing listener/server lifecycle so
tests exercise the actual supplied GraphQL client. It does not change the API
handler, session metadata, Dagger cache identity/egraph, module evaluation or
telemetry flushing. It retains the ten-second graceful deadline using
`context.WithoutCancel`, callback-error precedence, and existing serve-error
handling. Active admitted requests still drain. It does not close a global
pool, disable keepalive, shorten the deadline or force-close active requests.
As before, callers must not start requests after the callback has returned.

## Regression tests

From the repository root:

```sh
GOCACHE=/tmp/dagger-rust-go-cache go test -race -count=1 \
  -run '^TestNestedClientServer' -v ./core/sdk/dang/shared
```

Four top-level tests/seven leaf cases pass, package 1.310s (28.17s command wall
including the initial compile). Tests cover unused accepted connections on
success/error/cancellation, cancellation of a still-blocked unused dial,
active-request draining with live/canceled parent contexts, and independent
overlapping invocations. Dial and request barriers deterministically create the
race; the supplied production GraphQL client must use the owned transport to
reach those barriers. Fallback test cleanup runs after assertions.

A Go overlay removing only `s.transport.CloseIdleConnections()` makes the
speculative-connection success test fail at its three-second cleanup bound.
That bound is functional, not a microbenchmark threshold. Negative control:

```sh
GOCACHE=/tmp/dagger-rust-go-cache go test -race -count=1 \
  -overlay=/tmp/dagger-rust-nested-client-red.1QHLJP/overlay.json \
  -run '^TestNestedClientServerSpeculativeConnection$/^success$' \
  -v ./core/sdk/dang/shared
```

It failed as expected in 3.257s package time (11.29s command wall). Production
files were not changed by the control. Logs:
`/tmp/dagger-rust-nested-client-shared-{race,red}.log`.

## Uninstrumented ordinary-CLI comparison

Both engines were built through the repository's pinned dev workflow. The
comparison retains CLI SHA256
`315466126e450f25806d61b8ae2a58b9c53e60337c200594812334f4eb8df34f` on both sides.
Before image:
`sha256:002684688952b4ce87736c29effecdb97f2d5e530f9df88833b7c3dba03d70b8`;
after image:
`sha256:45fc239ecb9dcff9f1fd8c1014aa75d42f769d41cc9da2be15b84d3c7d270e82`.
The code comparison is on upstream `731bea2d61026bc6dfc029bd0803d7b4995cb71d`
plus stack branches 01–13; branch 13 changes only the interpreted fixture/tools.
The candidate has the owned-transport fix and no connection-state diagnostic.

Candidate build (use the parent stack worktree and a distinct name/output for
the baseline; the dev loader's stopped-placeholder requirement is documented
in the preceding HTTP-input experiment):

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call \
  dev --docker=unix:///var/run/docker.sock deploy \
  --name=dagger-engine.rust-nested-fix-21671ac5 \
  --image=localhost/dagger-engine.rust-nested-fix-21671ac5 \
  --platform=linux/amd64 --debug-endpoint=false \
  --output /tmp/dagger-rust-nested-fix-bin
```

New, separate empty engine state volumes were created for each image. Each
received one retained but excluded warmup check, then 60 alternating ordinary
standalone CLI invocations. Both use the same configured ripgrep workspace,
compiler, module settings and Cargo action. No resident/watch session is used.
Images/host filesystem/network caches outside those volumes are not reset.
Toolchain/registry/Cargo setup occurs in the warmups, not covertly before them.
No build, test or analyzer process from this work ran during timed trials.

```sh
python3 hack/bench-rust-loop/compare-cli.py \
  --before ./bin/dagger --after ./bin/dagger \
  --before-engine container://dagger-engine.rust-nested-ab-before-21671ac5 \
  --after-engine container://dagger-engine.rust-nested-ab-after-21671ac5 \
  --workdir /tmp/dagger-rust-loop-kk7kixl4/dagger --samples 60 \
  -- check rust:check
```

Use the configured ripgrep workspace described in the module experiment, at
revision `3fce3b5bb0236da2df6d99672afb8a719642eca7`. For this run,
credentials/config and OTLP headers were unset, `DO_NOT_TRACK=1`, CLI XDG
directories isolated, and complete OTel sent only to localhost:43185.
Native `--profile` was not enabled in these timing rows. Raw results:
[all pairs including warmups](nested-client-warm-pairs.csv), local directory
`/tmp/dagger-rust-cli-pair-tyzspp82`.

Reproduce that diagnostic environment in a dedicated shell, with a local
`hack/otlpdump` receiver already listening on 43185:

```sh
rust_bench_state=$(mktemp -d /tmp/rust-nested-bench.XXXXXX)
export XDG_CONFIG_HOME="$rust_bench_state/config"
export XDG_DATA_HOME="$rust_bench_state/data"
export XDG_STATE_HOME="$rust_bench_state/state"
unset DAGGER_CONFIG DAGGER_CLOUD_TOKEN DAGGER_API_TOKEN DAGGER_CLOUD_URL DAGGER_API_URL
unset DAGGER_SESSION_PORT DAGGER_SESSION_TOKEN _EXPERIMENTAL_DAGGER_RUNNER_HOST
unset OTEL_EXPORTER_OTLP_HEADERS OTEL_EXPORTER_OTLP_TRACES_HEADERS
unset OTEL_EXPORTER_OTLP_LOGS_HEADERS OTEL_EXPORTER_OTLP_METRICS_HEADERS
export DO_NOT_TRACK=1 OTEL_EXPORTER_OTLP_TRACES_LIVE=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:43185
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:43185/v1/traces
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:43185/v1/logs
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:43185/v1/metrics
```

These analytics/config overrides are diagnostic settings, not evidence for
default-analytics onboarding performance. Set the engine explicitly as shown
in each command; a debug URL alone does not select the CLI's engine.

| Whole-process metric | Before | After |
| --- | ---: | ---: |
| Samples | 60 | 60 |
| Median | 473.684ms | 473.459ms |
| Minimum | 430.699ms | 417.020ms |
| Maximum | 6813.160ms | 1119.883ms |
| Mean | 820.245ms | 531.677ms |
| p95, nearest rank | 1326.964ms | 908.715ms |
| Samples over 2s | 3 | 0 |

Median paired saving is **-0.893ms**: there is no demonstrated median win.
Baseline samples 13, 40 and 56 take 6813.160, 5736.102 and 5782.207ms. Their
tails are retained; candidate slow samples are also retained. This finite run
does not establish a zero future tail probability. The deterministic regression
tests establish the specific lifecycle mechanism separately.

Warmups take 22.526s before and 21.860s after. They are sequential one-off
setup observations, not a causal cold-onboarding speedup or the entire install
journey. Candidate build preparation took 1m44s in the dev deploy span; its CLI
was exported separately so it did not replace the comparison binary.

Six selected complete wcprof traces (nearest each median, both maxima, and the
other two baseline tails) pass structural gates: 169 operations, one root,
154/154 spans, no losses/open/orphaned spans. Replay drift is -0.0% on baseline
tails and -0.1% on ordinary/candidate-max captures. Baseline final nested query
to `Rust.check` completion takes 6329.655/5310.088/5239.853ms in the three
outliers; candidate median-nearest/max takes 9.213/8.468ms. No selected trace
executes Cargo. Artifacts: `/tmp/dagger-rust-nested-ab-{label}-*`.

The candidate's normal remaining envelopes include 133.776ms connecting,
58.6ms `ModuleSource.asModule` self-time, 57.4ms `Rust.check` self-time, and
16.4ms source-upload self-time. These are wall-clock envelopes, not CPU time;
do not sum nested spans. Connection setup includes Docker discovery, engine
Info, session attach and trace-subscription startup. The latter is not a flush.
The candidate maximum is distributed inflation: 100.725ms before the root,
959.299ms inside, 59.861ms afterward, including 339.555ms connecting. It is not
another multi-second module-shutdown stall.

## Real edits and external-library upgrade

Run the existing `run.py` harness with the same pinned image/ripgrep revision,
`--samples 5 --pinned-source-sync --prepare-project-toolchain`, the committed
rustfmt toolchain fixture, and `--dependency-upgrade`. Set each engine URI and
its debug URL; `--dependency-first dagger` for the candidate batch, `native`
for the baseline. Native/Dagger order alternates within edit scenarios. Batch
order is candidate then baseline, **not randomized per-edit engine A/B**.
Each batch has fresh source/target/registry/git keys but retains engine/image
and immutable toolchain caches. Native is matching Cargo via `docker exec`.

```sh
DAGGER_ENGINE=container://dagger-engine.rust-nested-ab-after-21671ac5 \
  DO_NOT_TRACK=1 python3 hack/bench-rust-loop/run.py --dagger ./bin/dagger \
  --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
  --samples 5 --debug-url http://172.17.0.33:6060 --pinned-source-sync \
  --project-toolchain hack/bench-rust-loop/fixtures/rust-toolchain-rustfmt.toml \
  --ripgrep /tmp/dagger-rust-ripgrep-reference --dependency-upgrade \
  --dependency-first dagger --prepare-project-toolchain
```

Resolve the current owned engine IP rather than assuming that address remains
valid. Baseline uses its own engine URI/debug URL and `--dependency-first native`.

Milliseconds, median [min,max]; five samples for exact/application/library,
one external upgrade and its followup in each batch:

| Scenario | Native baseline batch | Dagger baseline | Native candidate batch | Dagger candidate |
| --- | ---: | ---: | ---: | ---: |
| Exact | 122 [120,126] | 476 [427,527] | 125 [123,142] | 457 [422,515] |
| Application edit | 299 [294,322] | 819 [807,874] | 300 [296,323] | 816 [799,870] |
| Workspace-library edit | 471 [464,500] | 1043 [972,1068] | 490 [463,533] | 1040 [992,1062] |
| External bstr upgrade | 1793 | 2115 | 1671 | 2266 |
| Upgrade followup | 122 | 443 | 134 | 542 |

Median paired candidate overhead: exact 315.780ms; application 504.934ms
[492.994,572.527]; workspace library 538.233ms [506.877,550.620]. The external
upgrade overhead is 594.900ms versus baseline 322.506ms; the candidate's
followup is also slower. These are single observations, with different native
times too. Neither improvement nor regression rates follow from them. The
ordinary edit medians are effectively unchanged; this is a lifecycle-tail fix,
not a claimed Cargo compilation improvement.

Both batches select bstr 1.13.0 after starting from 1.12.0, rebuild the same ten
packages, retain unrelated memchr, preserve locked manifests, and pass compile
failure/repair/old-failure revisit/repair revisit. The dependency resolution and
lockfile edit occur outside the check timer; this measures checking an actual
upgraded library, not the `cargo update` network operation. No whole-project
rebuild is substituted for the dependency scenario.

All five application edits per batch rebuild only ripgrep; all five library
edits rebuild grep-printer, grep and ripgrep, identically to native. Cached
`check-log` output describes its producing execution, not proof of a new run;
use the matching execution spans and new-input/failure assertions. Both sides
omit Git metadata in this fixture, yielding the same missing-commit-hash
limitation. This is not a semantics-preserving default for arbitrary build.rs.

First checks with fresh Cargo caches are 6.758s native/6.981s Dagger before,
7.443s/7.454s after. They are not cold onboarding: Dagger retains immutable
toolchain setup, while each native container installs its configured component
on that first check. No speedup is claimed from that cache-state difference.

Raw [invalidation rows](nested-client-invalidation.csv); runs
`/tmp/dagger-rust-loop-e5_cs8uy` (candidate) and
`/tmp/dagger-rust-loop-emdjm0pb` (baseline). Separate profiled calls are not
included in those headline rows. Twelve complete OTel captures across first
check, application, library, dependency, profiled application and profiled exact
pass gates: 169–238 operations, all declared spans present, one root, no loss.
Six native wcprof dumps have 12 roots each, no open/dropped events and near-zero
replay drift, but cover only 202–824ms windows, not entire CLI processes. Use
complete OTel plus recorded process boundaries for end-to-end interpretation.
For example, native wcprof attributes 610.8ms self-time to the candidate's
profiled application function, whereas complete OTel separates 54.2ms function
self from a 493.2ms shell envelope. The native figure is not 610.8ms of engine
overhead: its query-root causal coverage is narrower. The unprofiled candidate
application/library/dependency shell envelopes are 369.9/551.1/1813.8ms and
include both rsync and Cargo; no diagnostic phase flags changed these actions.
Artifacts: `/tmp/dagger-rust-nested-invalidation-{before,after}-*`.

## Integration and remaining scope

The focused Dang integration suite passes on the candidate: 12 selected groups
covering both major runtime versions, directives, enums, maps, scalars,
interfaces, workspace arguments and self-calls. Package time 55.464s; log
`/tmp/dagger-rust-nested-fix-integration.log`. The host launch unsets
`DAGGER_ENGINE`, sets `_EXPERIMENTAL_DAGGER_RUNNER_HOST` to the candidate and
`_EXPERIMENTAL_DAGGER_CLI_BIN` to the fixed CLI, and uses `-parallel=1`.

`test-toolchain.py` also passes eleven standalone checks and six direct
immutable component-manifest reads on the candidate, including component
addition, source/configuration failure and repair, configuration removal and
legacy-file precedence. Local run:
`/tmp/dagger-rust-toolchain-test-nqzaoejd`.

This change does not establish faster Cargo compilation, cold onboarding
success, macOS/remote validation, artifact-export performance, or completeness
of the official Rust module. Upstream moved to `f78bf2c58f` during this run;
the measurements above deliberately retain their original base, rather than
mixing revisions within a comparison. Post-rebase validation is separate.

## Post-rebase validation on f78bf2c58f

The entire 14-branch stack is now based on upstream
`f78bf2c58feec99030c5933c8c64c96de0eb87b1`. The measured old stack is retained
as `archive-rust-perf-before-f78bf2c58f` at
`42c3aee38d8f82e7e6ad135cb2920ed37907d838`. `git range-diff` reports all 15
commits unchanged. The rebuilt source tip is
`c09d6699075668c1ce812ae5e41974c5015c6fad`.

Main's intervening PR changes remote-module resolution/reporting and adds a
persisted Git source field; it does not overlap the stack's files. No old/new
samples are merged into one A/B result. Build command is the pinned dev deploy
above with name/image `dagger-engine.rust-main-f78bf2c58` and output
`/tmp/dagger-rust-main-f78-bin`. Engine image:
`sha256:da54e8c62153ee7cfcb6b5374d3479c972414d5467abd6144f579b9f39eefadf`;
new CLI SHA256:
`8423acd3b75cbd1fa25dee252b3c5f5a484585a319146ac38a106e19b1c1811e`.
Old binaries/engines and original experimental archives remain untouched.

Post-rebase race tests pass: five repeats of the seven nested-client cases
(package 1.959s); eight HTTPState tests (1.176s); and the private-field
producer-session-close retention test (1.202s). Focused integration passes
the 12 Dang groups plus main's three remote/local module-resolution cases
(package 138.144s). The locked public-install case takes 78.62s across its
two installs; this is neither a Rust onboarding benchmark nor a claimed win.
Logs: `/tmp/dagger-rust-nested-main-f78-*-race.log` and
`/tmp/dagger-rust-nested-main-f78-integration.log`.

The same toolchain correctness suite passes again with the new CLI/engine:
`/tmp/dagger-rust-toolchain-test-odpgwtns`. No benchmark overlaps a test/build.

A separate five-sample ripgrep validation uses the same harness/pins/settings,
the new CLI, `DAGGER_ENGINE=container://dagger-engine.rust-main-f78bf2c58`,
its current debug URL, and `--dependency-first native`. The engine had already
run integration tests, but had not materialized this Rust image; Cargo cache
keys are fresh. Native's Rust Docker image is already installed. This is not
an empty machine or an entire public Rust-module installation.

| Scenario | Native median | Dagger median | Median paired overhead [min,max] |
| --- | ---: | ---: | ---: |
| Exact, n=5 | 126.933ms | 440.408ms | 303.233ms [285.347,346.572] |
| Application edit, n=5 | 295.249ms | 855.880ms | 547.811ms [490.648,657.597] |
| Workspace-library edit, n=5 | 458.240ms | 1011.349ms | 543.831ms [522.412,560.020] |
| External upgrade, n=1 | 1653.216ms | 2155.252ms | 502.036ms |
| Upgrade followup, n=1 | 125.176ms | 476.401ms | 351.225ms |

First checks are **6.725s native versus 26.214s Dagger: +19.489s**. The cold
overhead target is not met. First-trace envelopes identify Rust image resolution
at about 1.32s, pulling 12.69s and unpacking 4.42s; toolchain setup is about
801ms. The three image phases do not overlap and sum to 18.430s (18.455s
start-to-finish including gaps). These are elapsed times, not CPU costs; do not
add nested HTTP requests again.
The completed first capture passes its structural gate (296 operations,
281/281 spans), but replay drift is **-2.8%, about 720ms**. Treat the replay
limitation explicitly; no first-use what-if saving is presented as measured.

Rebuilt sets, locked inputs, unrelated dependency reuse, and failure/repair
probes still agree. Six OTel captures and three native wcprof dumps accompany
this validation; narrower native-query coverage remains as described above.
Raw [validation rows](nested-client-main-f78-validation.csv), full run
`/tmp/dagger-rust-loop-t1v_7wrx`, profiler artifacts
`/tmp/dagger-rust-nested-main-f78-*`.

Next module experiments should target prepared toolchain delivery and retaining
the source-independent base Container in ordinary immutable object state.
Include the first constructor in timing, retain the configuration-sensitive
toolchain stage, and leave source reconciliation/Cargo together under their
locked caches. Neither experiment is implemented or counted as a gain here.
