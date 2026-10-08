# Rust compiler cache experiment

`rcexp` records Cargo's actual compiler commands and replays each compilation as
a Dagger operation. Package source and dependency artifacts are explicit inputs;
compiled artifacts are immutable outputs. No compiler cache volumes are used.

This follows the Go package replay described in
[dagger/dagger#14555](https://github.com/dagger/dagger/pull/14555) and
[#14557](https://github.com/dagger/dagger/pull/14557).
Erik's `gcexp` implementation was unavailable when this experiment was written.

The existing [dagger-rust module](https://github.com/grouville/dagger-rust) is
the Cargo-facing layer: checks, toolchain selection and final artifact publishing.
This experiment explores a possible native compiler-cache backend for that
module. It currently supports a smaller set of projects, so integrating it should
start as an explicit experimental option while the module keeps its normal Cargo
execution for other projects. The cache-transfer integration test lives here
because it uses Dagger's internal test fixture.

Users should install one Rust module for their workspace. Compiler operations and
dependency edges are internal to its backend; no module per crate is needed.

## Run

Run from the repository root. Build the matching CLI so the Go SDK uses this
checkout's API and engine:

```sh
go build -o /tmp/dagger-rcexp ./cmd/dagger
export _EXPERIMENTAL_DAGGER_CLI_BIN=/tmp/dagger-rcexp

go run ./hack/rust-cache capture \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json

go run ./hack/rust-cache replay \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-cold \
  --report /tmp/rust-cold.json

go run ./hack/rust-cache replay \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-warm \
  --report /tmp/rust-warm.json --previous /tmp/rust-cold.json
```

Artifacts preserve their paths relative to `/target`; the fixture executable is
under `debug/deps/app-*` (without a file extension). Replay reports include
per-action artifact digests and execution markers. A matching marker means that
the cached filesystem was reused; the marker is excluded from dependency inputs.
`--previous` counts matching operations, rather than inferring hits from elapsed
time. Capture time is reported separately and excluded from replay measurements.
New captures also record each compiler process's elapsed time. These timings are
diagnostic and do not enter replay identities.

Copy the fixture outside this checkout to try edits. Changing only the application
source should preserve all library compilation markers. Changing `base` should
preserve `right` while rebuilding the affected branch. Adding or deleting package
resources also changes the corresponding package input.

Pass Cargo build options after `--`, for example `-- --features left/extra` or
`-- --release`. Use repeatable capture `--env KEY=VALUE` flags for environment
inputs, for example `--env RCE_LABEL=custom`. These are recorded in the plan;
recapture to change build options or environment. `--image` selects a toolchain
at capture time; its resolved digest is recorded. The default matches the
repository's pinned Rust SDK image. Diagnostic evaluation concurrency defaults
to eight. Add `--artifacts-only` to replay to demand and export the artifact
directory directly, without marker/digest queries or a report. This models the
artifact-returning path a Rust module would use; it cannot be combined with
`--report` or `--previous`.

Plans record the compiler invocations and graph, not source or build artifacts.
Replay reads the current package sources. Cargo manifests, lockfiles, `.cargo`
configuration, and toolchain files are fingerprinted: changes require recapture.
Keep plans, reports and exported outputs outside the source directory.

## Supported boundary

This first experiment supports Linux/amd64, path-only workspaces contained in the
source directory, and library/binary compilation with incremental compilation
disabled. Source resources must be regular UTF-8 files. Source inputs outside
their package roots, registry/git dependencies, build scripts, proc macros,
test compilation, custom targets and symlinks are rejected. `target` and `.git`
directories are excluded. Package inputs are deliberately coarse: every file
owned by the package participates in its cache identity.

The toolchain image must provide `/usr/bin/env` with `-u` support, as the default
Bookworm image does. Captured environment variables and removals are passed as
exec arguments instead of individual container configuration operations. They
still enter the cache identity, and literal values are never parsed as shell
source. An explicit removal takes precedence over a captured assignment.

This is a compiler replay experiment, not a replacement for normal Cargo builds.
Build-script execution, dependency downloads, proc macros and test execution are
the next stages. The capture wrapper forwards Cargo probes and normal compiler
diagnostics, and records successful compilations only. Replay rebuilds from an
empty target directory using native dependency files, without the capture's
build state. Compiler flags, relevant Cargo environment and `env!`/`option_env!`
dependencies enter the operation; jobserver and Dagger transport data do not.

The Go package under `replay` separates recipe construction from evaluation. Tests
can construct the same graph on different engines. Evaluation reads filesystem
outputs only: requesting a transferred container's private exec metadata could
rerun its compiler despite its artifacts already being available remotely.

## Performance work

The user-facing target is native Cargo time plus at most 0.5 seconds for an
equivalent command, including connection, source transfer, evaluation, output
transfer and process shutdown. A cached compiler operation alone does not meet
that target. The native backend, its integration into the Rust module, and the
module's command UX need separate measurements and end-to-end tests.

The backend remains unfinished. It reuses whole compiler invocations and does
not yet preserve rustc's incremental state within an edited crate. Native Cargo
enables this by default for development builds, so disabling it cannot establish
parity on larger edited crates. Registry dependencies, build scripts, proc macros
and test actions also need support before general module integration.

Replay reports separate source reading, connection, graph construction,
evaluation and export. `driver.ready_seconds` stops when artifact export
finishes; it excludes report writing and process shutdown. Per-action
`demand_seconds` includes Dagger's recipe and filesystem work as well as any
compilation, while `digest_seconds` measures the subsequent digest queries.

Use a prebuilt driver to measure full process time in independent CLI sessions:

```sh
go build -o /tmp/rcexp ./hack/rust-cache
python3 hack/rust-cache/benchmark.py \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --replay-bin /tmp/rcexp \
  --dagger-cli /tmp/dagger-rcexp \
  --out /tmp/rust-benchmark --runs 5
```

The benchmark warms results once, then checks that each measured command reuses
all compiler markers and preserves artifact digests. Its wall times include
shutdown and artifact export. Preparation and capture are excluded from warm
measurements. Logs, reports, artifacts and a summary are kept under `--out`.

Add `--artifacts-only` to the benchmark to time the artifact-returning command.
After each measured command, it compares exported bytes and permissions with
preparation, then runs a separate diagnostic command to verify every compiler
marker and digest. The summary stores that command under `verification`; its
time is excluded from the artifact-only measurement. A changed marker detects
a compiler rerun by either command. The default benchmark includes diagnostics
in the measured command.

For a native Cargo comparison, recapture with the current wrapper and add
`--cargo /path/to/cargo --rustc /path/to/rustc`. The script requires the captured
compiler version and matching Cargo version, uses the captured Cargo arguments
and environment overrides, and exits unsuccessfully if median replay overhead
exceeds `--budget` (default 0.5 seconds). Native Cargo retains its project/default
incremental setting; the summary records this difference from replay. These are
warm unchanged-build measurements. Source edits, realistic dependency graphs,
the Rust module itself, and remote-engine latency need additional comparisons.

Package sources are indexed once and directory recipes are reused across actions
in a package. Ownership lookup walks directory ancestors instead of scanning
every package. This removes the previous repeated workspace sorts and quadratic
package-root scans. Compare source grouping at 10, 100 and 300 packages with:

```sh
go test ./hack/rust-cache/replay -run '^$' \
  -bench '^BenchmarkPackageSources$' -benchtime=1x -count=3
```

Execution markers live in a small `/rcexp-meta` directory. On engines without
[#14555](https://github.com/dagger/dagger/pull/14555), a root-level marker can
trigger a walk of the entire toolchain filesystem. Dependency and exported
artifact bundles use `Directory.withFiles`, which benefits from
[#14557](https://github.com/dagger/dagger/pull/14557). Further engine changes
should follow measured bottlenecks and retain filesystem-only remote reuse.

The first performance pass on 2026-10-08 found:

- Source grouping at 300 synthetic packages with 16 files each took 9.68 seconds
  median with the old scan and 2.58 milliseconds with the index (three runs).
  This measures grouping, excluding directory recipes and compiler work.
- Five unchanged replays using the same Rust 1.77.2 compiler as native Cargo
  took 700 milliseconds median end to end, versus 14 milliseconds for Cargo.
  All compiler operations were reused. The 686-millisecond overhead failed the
  500-millisecond budget. Replay includes diagnostic marker and digest queries;
  the eventual module need not collect these on every build.
- Alternating fresh application edits before and after the marker change gave
  overlapping results around three seconds. They do not establish a consistent
  edit-latency improvement from that change on the tested engine.
- In a fresh capture, compiler-process times were approximately 112 milliseconds
  for the application and 19–22 milliseconds per library. These are capture
  measurements, not a paired Cargo/replay edited-build comparison.

These are tiny-fixture results on a shared host and the compatible development
image `localhost/dagger-go-taskforce:review`
(`v1.0.0-beta.15+5939a5d3.dirty`), not a general Rust performance claim. Source
grouping now scales better; cached-result demand, command startup/shutdown,
edited-build overhead and rustc incremental-state reuse remain work to do.

### wcprof follow-up

The next pass used engine and CLI source at `ea21cf49162d1eb9ae5749ea38813ee84cee7537`
on `main` (development version `v1.0.0-beta.17`), with the installed beta 16
runtime. This includes the merged file-checksum fix. The Rust driver was built
with that checkout's SDK. Both profiler engines were isolated from other work;
the underlying host was shared.

- A warm diagnostic replay issued 41 engine queries and traversed 821 cached
  `Container.withEnvVariable` calls for four compiler actions. Moving environment
  setup into exec arguments removed those calls. In nine alternating before/after
  runs, median graph evaluation fell from 125 to 83 milliseconds. All compiler
  markers were reused, and all 11 artifact digests matched the Cargo capture.
- Nine artifact-only commands took 535 milliseconds median versus 33 milliseconds
  for matched native Cargo. The 502-millisecond overhead still missed the
  500-millisecond budget. Exported contents, permissions and all compiler markers
  were checked after each measurement.
- Nine alternating runs per transport against the same warmed engine took
  535 milliseconds through Docker's exec tunnel and 429 milliseconds through
  direct loopback TCP. Compiler results were shared across transports. This
  isolates roughly 100 milliseconds of connection cost; it does not establish
  performance for remote TCP engines. Post-export time remained about
  290–310 milliseconds, so transport alone does not account for teardown.
- The artifact-only wcprof capture contained 26 engine queries across a
  66-millisecond interval, within a 477-millisecond full command. wcprof currently
  instruments queries and execs rather than the complete CLI lifecycle.
  Summed concurrent self times must not be treated as wall time.
- In the fresh app-edit capture before the environment change, the compiler
  process took 133 milliseconds and container runtime startup took 36 milliseconds.
  Only the application recompiled; the three library markers were reused.
  This is a phase breakdown, not a paired native Cargo edit benchmark.

The filesystem-only cache-transfer regression also passed against this `main`
engine: captured Cargo artifacts matched replay, source/resource/flag/environment
changes rebuilt the expected operations, and a second fresh engine reused all
four compilation markers from transferred filesystem parts.

A subsequent warm benchmark failed its reuse check after the engine pruned the
unchanged compiler results. Logs showed free-space-pressure pruning on the shared
host. The pruning target did not honor `reservedSpace` for `minFreeSpace` pressure;
the accompanying engine fix caps that target at cache usage above the reserve.
Regression tests reproduce both the incorrect target and removal of a cache
already below its reserve. This addresses retention, rather than warm query
latency. Keep the reuse checks enabled when benchmarking: byte-identical rebuilt
artifacts alone do not establish a cache hit.

With explicit retention on another isolated, unpatched `main` engine (4 GiB
reserved, 8 GiB maximum, `minFreeSpace: 0`), all nine artifact-only replays through
loopback TCP reused all compiler markers. Median full-command time was
684 milliseconds versus 21 milliseconds for matched Cargo: 663 milliseconds
overhead, still outside the budget. The shared host was under substantial I/O
pressure; this run is not comparable to the earlier alternating transport run.
Median artifact-ready time was 262 milliseconds and time after that was
432 milliseconds. A follow-up warm wcprof recording saw 26 queries over
76 milliseconds within a 506-millisecond command, with no compiler executions.
These measurements locate remaining work in the surrounding command lifecycle;
they do not establish edited-build or module-level parity.

### CLI lifecycle follow-up

Cloud export measurements found a 100-millisecond wait for the first trace batch,
followed by connection setup and requests that could remain on the shutdown path
of a short command. The CLI now flushes its first live Cloud span asynchronously
while connecting to the engine. Later batches and final shutdown keep their
existing policy; the initial flush has the Cloud request timeout. Commands without
Cloud export are unaffected.

- Nine alternating, uninstrumented diagnostic replays per implementation took
  511 milliseconds median before and 480 afterward through loopback TCP;
  through Docker they took 566 and 515 milliseconds. Compiler markers and all
  11 artifact digests matched on every run.
- Separate nine-run artifact-only comparisons with the change took
  477 milliseconds through TCP versus 35 for matched Cargo (442 overhead), and
  529 through Docker versus 35 for Cargo (495 overhead). Both met the
  500-millisecond budget for this tiny unchanged fixture. The Docker margin is
  small, and these separate runs do not measure the improvement by themselves.
- Seven fresh application edits through Docker took 601 milliseconds median
  versus 147 for matched Cargo (454 overhead). Each edit changed executable
  behavior; only the application recompiled, all three libraries were reused,
  and the replayed executable's output matched Cargo's. Replay ranged from
  530 to 1,145 milliseconds, so this median does not promise the budget on every
  edit. Native Cargo kept its default incremental setting; replay disabled it.
- In nine instrumented before/after pairs, Cloud span requests increased from
  19 to 22 total; log requests remained 18. Starting earlier can send an extra
  live update that would otherwise be coalesced. This is the cost of overlapping
  the first request with command work.
- Successful and failing commands still delivered their final root status,
  output, EOF records and execution metrics to a local OTLP receiver. A focused
  regression and its race run also verify delivery of completed spans when the
  initial request is blocked and the command context is canceled.
- Five alternating captures per transport located remaining Docker connection
  cost: 106 milliseconds median for connection versus 6 through TCP. Initial
  client creation and session setup each took about 40 milliseconds through
  Docker versus about 2 through TCP. These are diagnostic phase timings with
  an additional OTLP exporter, rather than an unprofiled latency comparison.
- A fresh-edit wcprof capture saw one compiler execution: 133 milliseconds in
  the compiler process and 38 in container runtime startup. Its 26-query window
  spanned 253 milliseconds within the 630-millisecond full command. The
  remaining command time includes connection and telemetry drain; concurrent
  query and wait totals should not be added to this wall-time breakdown.

This pass used the same `main` source and Rust toolchain as the wcprof follow-up,
with explicit cache retention on a fresh isolated engine. Keep the CLI pinned
with `--dagger-cli` or `_EXPERIMENTAL_DAGGER_CLI_BIN` when benchmarking. The helper
records its version and refuses an unpinned run, avoiding the SDK's download/PATH
fallback. Runs that selected another CLI or overlapped test compilation were
excluded. These tiny-fixture results do not establish performance for larger
edited crates, remote engines or the official Rust module.

### Larger edited crates

`benchmark_scale.py` generates many source modules inside one application crate,
with the same three path-library dependencies. It compares full artifact-only
commands with native Cargo using incremental compilation both on and off.
All builds use the same explicit codegen-unit count: Cargo otherwise changes
that default with incremental compilation, as described in the
[Cargo profile reference](https://doc.rust-lang.org/cargo/reference/profiles.html#codegen-units).
Each edited run uses a fresh random constant, recorded in the summary, so a repeat
on the same engine cannot accidentally measure a previously compiled edit.

The initial five-run comparison used 128 source modules with eight functions
each, 16 codegen units, Rust 1.77.2 and the same `main` engine/modified CLI as the
lifecycle pass. Median full-command times were:

| Scenario | Native Cargo, incremental | Native Cargo, full | Original replay |
| --- | ---: | ---: | ---: |
| Unchanged | 25 ms | 14 ms | 479 ms |
| One source-file edit | 487 ms | 2,341 ms | 4,149 ms |

Every edit changed executable behavior. All three library markers were reused,
and replay output matched both Cargo controls. The result shows two costs:
rustc's missing incremental state and avoidable source preparation.

A fresh-edit wcprof capture found 128 `Directory.withNewFile` snapshots taking
1.08 seconds before compilation. The flat recipe invalidated every subsequent
file after an early source edit. Source recipes now form a balanced tree with at
most 64 files per leaf. For an existing-file content or permission edit, unchanged
subtrees can be reused. File additions/deletions may also change the partitions.
The smaller sources retain their existing recipe.

A 16-file-leaf experiment reduced edited replay from 4.25 to 3.03 seconds in five
alternating pairs, but increased unchanged replay from 504 to 619 milliseconds.
The chosen 64-file leaves reduced rebuilt file snapshots from 128 to 30, with four
directory merges and six extra queries (32 versus 26). Its later wall-time runs
had substantial host-load drift and do not establish a reliable latency gain.
The filesystem regression checks nested paths, repeated basenames, empty/UTF-8
files, permissions and immutable old snapshots. The compiler regression now uses
a larger source tree and verifies filesystem-only reuse on a second engine.

Reproduce with a prebuilt driver and matching CLI; keep the generated workspace
and captures outside the checkout:

```sh
python3 hack/rust-cache/benchmark_scale.py \
  --dagger-cli /tmp/dagger-rcexp --replay-bin /tmp/rcexp \
  --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-scale --runs 5 --modules 128 --functions 8
```

### Native incremental snapshots

Replay can now enable rustc incremental compilation for one named crate. It
mounts a previous native `Directory` at `/rcexp-incremental` and retains the next
state through a persistable `Directory.withDirectory` operation. This is native
Dagger filesystem cache: rustc owns the state format and decides which internal
queries to reuse; Dagger owns the immutable snapshots and compiler-result cache.
No compiler `CacheVolume` is used.

```sh
# Prepare state once, then edit the source.
/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-artifacts --artifacts-only \
  --incremental-crate app --state /tmp/rust-state-before.json

/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-edited-artifacts --artifacts-only \
  --incremental-crate app --seed /tmp/rust-state-before.json \
  --state /tmp/rust-state-after.json
```

The state JSON contains a compatibility fingerprint and an engine-local result
handle, not compiler-state files. The handle remains usable while the engine
retains that result; it is not a portable reference or an automatic seed index.
The fingerprint excludes source contents and output digests, while keeping the
captured compiler configuration and dependency graph configuration fixed. A
different crate, toolchain, manifest configuration, flags or environment requires
new state. The seed is still an ordinary exec input: selecting a different seed
can change the result cache identity. Automatic seed selection and preserving
exact hits independently of the seed remain future work.

On the same 128-module fixture, five rotating-order fresh edits on the isolated
Docker engine produced these medians:

| Edited build | Full command |
| --- | ---: |
| Cargo, incremental | 535 ms |
| Cargo, full | 2,643 ms |
| Dagger replay, full | 3,496 ms |
| Dagger replay, native incremental seed | 1,723 ms |

Both replay variants reused all three libraries, recompiled the application,
and matched the behavior of both Cargo controls. State materialization and the
next reference write are included in the seeded command. The 1.77-second saving
is a comparison within this run, rather than against the earlier 4.15-second
baseline. The remaining median overhead versus Cargo incremental is 1.19 seconds.
On an eight-module smoke fixture, seeded replay was slightly slower than full
replay, so retaining state is not a universal win for small crates.

A fresh seeded-edit wcprof capture took 1.39 seconds overall, with 617 milliseconds
in rustc, 50 in runtime startup, and 30 rebuilt source-file snapshots. The query
window spanned 989 milliseconds. These are one diagnostic capture, not an additive
breakdown of the benchmark medians. Source import and command overhead still
need work. The measured source-construction cost belongs to `withNewFile`
snapshots, not filesync; compare native source-directory inputs before treating
it as a filesync implementation problem.

Reproduce the edited-build comparison by adding `--incremental` to
`benchmark_scale.py`. It only measures fresh edits; initial builds prepare and
verify the cache without serving as performance scenarios.

### Many-crate workspaces

The same helper accepts `--crates 100 --shape fanout` or `--shape chain` instead
of a multi-file application. It measures a leaf-library edit and a shared-library
edit separately. The fanout application depends on every leaf; each leaf depends
on the shared library. A leaf edit must compile exactly that leaf and the app,
while a shared edit must compile every action. The chain fixture uses the last
library as its editable leaf. Every edit changes executable behavior, and the
helper checks output against both Cargo controls and verifies execution markers.

Three runs with 100 fanout libraries (102 compiler actions) exposed a separate
scaling gap:

| Edit | Cargo incremental | Cargo full | Dagger replay, full |
| --- | ---: | ---: | ---: |
| Leaf library | 298 ms | 249 ms | 4,443 ms |
| Shared library | 903 ms | 812 ms | 24,403 ms |

A fresh leaf-edit profile recorded 911 engine queries while executing only two
compilers. Dependency and output assembly each expanded `Directory.withFiles`
into chains of individual `withFile` operations. A fresh shared-edit profile
took 19.47 seconds and showed an 8.82-second artifact-copy chain beneath export,
plus runtime-start contention (102 starts, 641 milliseconds median). Concurrent
query and runtime totals are not full-command wall time. These profiles identify
artifact assembly, repeated query work and execution concurrency as candidates
for the next experiments; they do not establish the benefit of an unimplemented
optimization. The chain generator has not yet supplied a performance result.

These remain synthetic workloads on Rust 1.77.2 with 16 explicit codegen units.
They do not establish performance for the official Rust module or real projects
with registry dependencies, build scripts, procedural macros or tests.

Use an isolated engine with its debug endpoint enabled and a matching CLI.
Warm the workload before capturing it. The helper records the full command's
wall time and fetches the engine recording after completion, leaving captures
outside the workspace:

```sh
python3 hack/rust-cache/profile.py \
  --debug-url http://127.0.0.1:6060 --out /tmp/rust-warm-profile -- \
  /tmp/rcexp replay --source /tmp/rust-workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-profile-artifacts --artifacts-only
```

Repeat after a fresh source edit with a different capture directory. The helper
also captures failed commands and returns their exit status. Profiled wall times
are diagnostic; use unprofiled alternating runs to compare implementations.
Analyze `profile.ndjson` with the engine-lab `wcprof-report` helper built from
the same engine source. Start with `classes`, then `critpath` filtered to
`^session.serveQuery$`, and `waits`. The
[engine-lab workflow](../../.dagger/modules/engine-lab/skills/engine-lab/SKILL.md)
describes those views and their limits. Capture dumps and temporary CLI probes
are not committed.

## Verify

```sh
go test ./hack/rust-cache/...
dagger api call engine-dev test --pkg ./core/integration \
  --run='TestRemoteCacheTransferSuite/TestRustCompilerReplay'
```

The integration scenario checks Cargo/replay artifact equality, executable
behavior, unchanged and edited builds, resource changes, feature/flag/environment
invalidation, and reuse on a second clean engine through the repository's remote
cache transfer fixture. Only the test infrastructure uses persistent volumes.
