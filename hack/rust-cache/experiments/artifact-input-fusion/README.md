# Compiler artifact-input fusion evidence

[The report](../../NATIVE_ARTIFACT_INPUT_FUSION.md) separates complete edited-command results, copy diagnostics, controls and cache compatibility. The isolated Rust-module branch is `grouville/dagger-rust:experiment/native-fused-artifact-inputs`, revision `3cd40e5928563ade3ea1cd21ab9924cd03d88fc3`, based on `f73c5614a89968afa6f6000328e96ea33745fd93`. No PR is open.

## Source and validation

`source/before/` and `source/after/` preserve both production files and the module files. Go source is compressed so this artifact directory does not create packages in the Dagger repository. `validation/provenance.json` records exact revisions and hashes. The sixteen-line addition/eight-line deletion is confined to replay's private automatic-input state and batch placement. `validation/worker-source-audit.json` checks fourteen unchanged worker build inputs, plus unchanged module state and compiler entrypoint.

From the candidate's `compiler/` directory:

```sh
go test -race -count=1 ./model ./replay ./worker
```

To run the real Rust integration test in a session connected to the compatible experimental engine:

```sh
go test -tags=integration -run '^TestBatchHistoryRestoresRevertedArtifacts$' -count=1 -v ./replay
```

`validation/integration.log.gz` contains the ordinary run. `validation/history-native-fresh_test.go.gz` is the test overlay with a unique base-source comment, preventing old worker execution hits from hiding an incorrect copy. `validation/integration-overlay.json` records its logical path; adjust it to your checkout before rerunning. `validation/integration-fresh.log.gz` records six binary-output/cache-reuse stages. Worker code and the test's behavioral expectations are unchanged.

`native-error-repair/` records a new 130-action cache, full reuse, a used-source edit, invalid Rust, repair and reversion, with actual collection after every phase. `native-retained-confirmed/` verifies complete reuse of all six older histories through the candidate. Large inspection JSON files are compressed.

The initial retained-history check is intentionally preserved in `native-retained-initial/`. It gets 2/6 hits on the small `before` fixture because the benchmark's final Cargo case edited that physical source after its last Dagger command. That check compiles four previously unseen actions. Its unchanged rerun gets 6/6, and the complete six-history validation passes. It is a setup failure, not a passing first attempt. Unchanged calls here verify correctness; they are not claimed as performance wins.

## Timed cohorts

`paired/` contains eight baseline/candidate/Cargo rounds each for the wide 1,026-crate check, 130-crate direct check and small workspace tests. `confirmation/` repeats the wide check and small tests with reversed case orders. Pair `-1` is preparation and excluded from summaries. No admitted measured observations are discarded.

Each workload uses one physical source and native-cache history for both implementations and its native Cargo control. Every arm makes a distinct used-source edit. Processes are fresh; engine and compiler state are warm. Telemetry stays enabled. Wcprof and CPU profiling are disabled. Ordinary collection stays enabled, with no scratch snapshots, forced containerd collection or forced Go collection. Per-command engine heap counters, Go GC counts, disjoint engine/exec cgroup CPU counters and host/engine pressure are saved in `samples.json`. The Docker parent overlaps those child counters and must not be added to them.

The drivers have local paths for the CLI, Rust toolchain, fixtures, collector and module worktrees; recreate or adjust them before rerunning. `metadata.json` records module revisions and engine identity. The default CLI is the existing buffered CLI, and native Cargo is Rust 1.77.2 with eight workers and incremental state outside the imported source. Cargo leaf checks assert exactly two crates checked. Logs and admission records are retained.

## Diagnostics

`baseline-profiles/` and `profiles/` contain three separately profiled edited commands per module: engine CPU, CLI CPU and runtime trace, wcprof and two goroutine captures. Profiling and stack dumps affect timing, so these observations do not enter the benchmark cohorts. All wcprof captures have zero dropped events and open operations. `validation/copy-profile-summary.json` verifies five copy operations become four and records each duration. The last candidate capture contains a Go GC cycle and remains included.

The CLI's existing `CPUPROFILE` environment variable enables its CPU and runtime-trace captures. Runtime traces and wcprof data are compressed in the archive; decompress them before passing them to `go tool trace` or wcprof-report. Engine CPU profiles include a five-second window around the command and may include later background work. Allocation and CPU scopes must not be added blindly to wall time.

## Engine and final state

Both arms use engine `e174ad0a118c3312cebae1333d4dbaf1f2a1d3f56656a337629830bbe18092e8`, with the exact code and provenance in `../containerd-root-dedup-followup/` and its referenced archives. The root-dedup experimental switch stays off throughout these cohorts. The module change requires no engine rebuild. The selected source snapshot, scalar restore and telemetry settings are identical in both arms.

`validation/final-engine-state.json` records ordinary collection enabled, all measurement switches restored, profiling off and no active sessions. No engine volume or cache is deleted. Large executable binaries are excluded. Verify archive contents from this directory with `sha256sum -c SHA256SUMS`.
