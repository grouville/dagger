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
repository's pinned Rust SDK image. Replay concurrency defaults to eight.

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
