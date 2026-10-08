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
