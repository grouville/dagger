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
