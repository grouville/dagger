# Current native package-discovery evidence

[The report](../../NATIVE_DISCOVERY_CURRENT.md) gives timings, controls, correctness and remaining work. The isolated module branch is `grouville/dagger-rust:experiment/native-discovery-current`, revision `da1ae47b6c96a3117de303b7584d028e35166530`, based on `3cd40e5928563ade3ea1cd21ab9924cd03d88fc3`. No PR is open.

`source/` preserves both module files, dependency files and the patch. `validation/compiler-source-audit.json` establishes the identical complete compiler tree. Inspector source is compressed to avoid introducing Go packages. `validation/client-and-inspector-provenance.json` records executable hashes and build information; binaries are excluded.

## Measurements

`paired/` and `confirmation/` each contain eight three-arm rounds for four workloads: the 1,026-crate collection check, 130-crate direct check, small workspace tests and expanded 1,026-package listing. Preparation round -1 is excluded. Every arm changes a Rust value, using one physical source/history per workload. The confirmation reverses each arm order. All admitted commands, logs, heap/Go-GC counters, pressure and cgroup CPU remain included. Parent Docker counters overlap engine and compiler child counters.

Telemetry stays enabled with the local receiver. Engine/compiler caches are warm; processes are fresh. Rust is 1.77.2 with eight workers. Wcprof is off during timing. Ordinary collection remains enabled, without forced Go/containerd collection or scratch snapshots. Source snapshot seeds, scalar restoration, batch metadata and attribute decoding are identical between arms. Root dedup and direct protobuf forwarding stay off.

The drivers record local paths for the CLI, toolchain, fixtures, modules, receiver and engine. Recreate those revisions/fixtures or adjust paths before rerunning. `validation/pooled-summary.json` preserves per-pair differences; differences between medians are not paired savings.

## Validation

`validation/native-discovery-current-validation-full/` contains the final sixteen-case Cargo oracle, returned names, hint-save counts and execution counts. Both earlier attempts are preserved. One encountered a GC operation outliving global recording; the final recorder drains existing operations and saves every raw chunk. The other had an incorrect oracle expectation for an excluded dependency. No events are discarded to make traces pass.

`validation/native-discovery-current-compile-validation-validated/` records successful ordinary checks, invalid-Rust rejection, repair, reversion and exact 2/2 action reuse. Earlier directories and driver versions remain. The first fixture inherited the ambient /tmp/.git marker, imported /tmp and was interrupted. The Directory probe and workspace-root commands in validation/no-git-workspace-default-path-directory/ establish the expected boundary behavior; subsequent fixtures use their own Git marker. This is not an engine defect. An earlier File probe failed in both layouts and did not isolate this boundary behavior. Other attempts imposed incorrect batch-layout expectations. Compiler action/hit assertions remain exact. Restored results can have no current batch, so reversion does not require one.

`validation/native-discovery-retained-oct16/` prepares the current input, then demands strict reuse across all six older histories: 130/130, 1,026/1,026 and 6/6 twice. A benchmark's final Cargo/listing edit may not have been compiled by Dagger. Unchanged calls verify correctness, not performance. Fixture Git metadata is excluded.

## Diagnostics and engine

`profiles/` contains twelve sequential captures: engine/CLI CPU, CLI runtime trace, wcprof and goroutine snapshots. Profiling affects timing, so these observations do not enter the cohorts. All final wcprof captures have zero dropped events and open operations. `operation-summary.json`, CPU summaries and critical-path reports separate filesystem discovery, publications and telemetry conversion. Aggregate/cumulative durations overlap.

Engine `e174ad0a118c3312cebae1333d4dbaf1f2a1d3f56656a337629830bbe18092e8` is unchanged. Build provenance and overlays are in `../containerd-root-dedup-followup/` and referenced archives. The existing buffered API is documented in `../../NATIVE_FINGERPRINT_BUFFER.md`; this module comparison adds no engine patch.

`validation/final-engine-state.json` verifies the binary hash, ordinary collection, restored controls, profiling off and no clients. No engine volume or cache was deleted. Decompress logs, wcprof data and runtime traces before analysis. Verify contents with `sha256sum -c SHA256SUMS` from this directory.
