# Experiment: prepare Rust support tools in ordinary OCI images

This branch publishes experimental source and measured evidence. It does not
change Dagger's engine, install an image, or select a new production default.
It is not the finished official Rust module or a portable end-to-end benchmark.

## Context and change

An ordinary first `dagger check rust:check` for pinned ripgrep waits for image
delivery, source-sync tools, requested Rust components and Cargo. The candidate
prepares the exact rsync packages and requested rustfmt in two normal OCI
layers. It adds no project source, dependency archive, Cargo cache or compiled
project output. The user still downloads all image layers on an empty engine.

`module-base` installs checksum-pinned rsync packages during preparation.
`module-prepared` starts from the known prepared image instead. Both preserve
the same Cargo command, source exclusions, Cargo caches and root-config-keyed
rustup preparation, so changed project requirements still invalidate normally.
The prepared module is a fixture, **not** a safe generic installation opt-out
for arbitrary images. Both module sources are byte-identical to those measured.

This uses normal immutable Container/image composition and Dagger-owned File
inputs. No new cache, egraph identity shortcut, listener, persistent session,
lazy snapshotter, host toolchain mount or weakened verification is introduced.
It moves tool packaging to image production; it does not make delivery free.

The measured fixture is Linux/amd64, Debian bookworm, Rust 1.97.1. Native uses
the exact same original compiler image, flags, workspace and root rustfmt
requirement. Other versions, architectures, arbitrary build scripts/native
requirements, macOS/remote engines and the full command matrix need validation
before this becomes an official-module packaging policy.

## Build the image artifacts

From this repository root, with its supported Go toolchain and Dagger CLI:

```sh
rust_package_output=$(mktemp -d)
rust_package_tools=$(mktemp -d)
(cd sdk/go && go build -o "$rust_package_tools/image-builder" ../../hack/bench-rust-toolchain-packaging/image-builder.go)
dagger api with-session -- "$rust_package_tools/image-builder" --output-dir "$rust_package_output"
```

The helper exports `base.oci.tar`, `prepared.oci.tar` and `build.json`, checking
for existing outputs before starting. Use the fresh, exclusively owned output
directory shown above, with no concurrent writers; this preflight check is
not atomic reservation of every export name. It never publishes to a registry. It compares compiler,
Cargo and native C-compiler versions and checks installed components. Source
uses the existing Go SDK and ordinary Dagger APIs. Its build-ignore directive
keeps this standalone helper out of repository package discovery.

The measured helper had a fixed output path. The published helper adds only
an explicit output-directory option and argument checks; the image recipe is
unchanged. Re-export validation is recorded in RESULTS.md. A future image
build may differ in timestamps/OCI descriptors; inspect and record actual
digests rather than assigning the historical digest to new artifacts.

To exercise the module, serve the chosen OCI artifact through an owned registry
accessible to the engine, record its actual digest, and configure an isolated
copy of the project with a local module source and settings:

```toml
[modules.rust]
source = "/absolute/path/to/hack/bench-rust-toolchain-packaging/module-prepared"
[modules.rust.settings]
image = "registry.example/rust-toolchain@sha256:<actual-prepared-manifest-digest>"
cacheKey = "<unique-fixture-cache-namespace>"
pinnedSourceSync = true
prepareProjectToolchain = true
```

Use `module-base` with the base image for the control. Copy the included
`rust-toolchain.toml` only into fixture copies without an existing toolchain
file. Run ordinary standalone `dagger check rust:check`. This example does
not configure a registry or reset an engine, and is not a timing result.

## Recompute the recorded statistics

```sh
python3 hack/bench-rust-toolchain-packaging/summarize.py
```

`measurements.json` retains all twelve non-HTTP-logged first-check samples,
including losing pairs, and source report hashes. The script recomputes six
paired differences; it does not execute Cargo or validate telemetry anew.

Full capture validation used the maintained external wcprof analyzer. Neither
that executable nor private raw traces/HTTP logs is distributed here. The
historical runtime/analysis adapters and exact local commands are identified
in EVIDENCE.md; those paths are evidence locations, not portable dependencies
silently installed by this branch. A portable reset/demo harness and public-
registry scorecard remain part of the larger unfinished task.

## Acceptance boundary

Six paired local-registry comparisons show a 500 ms median full-CLI saving,
four of six favorable. Reduction in paired overhead relative to native is
264 ms, not 500 ms. Cargo itself was slower in five of six pairs. These are
modest, variable results, not native parity or a first-installation solution.
See RESULTS.md for each cohort and retained non-wins. No maintainer approval,
production readiness or public-network speedup is asserted.
