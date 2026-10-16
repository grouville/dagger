# Root-loop follow-up evidence

[The report](../../NATIVE_GC_ROOTS_FOLLOWUP.md) distinguishes the natural-command control, forced collection, preparation effects and noisy component comparisons. No PR is open. The experimental switch is disabled at the end.

## Standalone refined patch

`variants/upstream-single-lookup.patch` applies to containerd main `c787e39387ec2de521a14985f6785c53dfefaad7`. It changes the initial-root loop and adds a regression and control benchmark to the existing GC test file. In a checkout of that revision, apply the test first:

```sh
git apply --include=pkg/gc/gc_test.go /absolute/path/to/upstream-single-lookup.patch
go test -mod=mod -count=1 -run '^TestTricolorDuplicateRoots$' ./pkg/gc
```

The unchanged baseline regression fails; its raw output is in `../containerd-root-dedup/validation/upstream-baseline.log.gz`. Then apply the production hunk:

```sh
git apply --include=pkg/gc/gc.go /absolute/path/to/upstream-single-lookup.patch
go test -mod=mod -race -count=1 -v ./pkg/gc
go vet -mod=mod ./pkg/gc
```

The current-main outputs and source hashes are in `variants/upstream-single-lookup-*`. All three package tests pass with no skips on Go 1.27.0. Whole-repository lint is unrun because `golangci-lint` is unavailable. This remains a draft for human review. The original membership-loop patch is preserved in `../containerd-root-dedup/upstream-source.patch`; the two patches are alternatives, not a patch series.

## Component and complete-command experiments

`variants/paired/` contains eight rotating rounds of the original, membership, size-check and map-key loops. Each fresh metadata process marks a read-only copy and verifies the same 77,772-node live set against an independent oracle; fixture loading is outside the benchmark timer. Unique-root controls run separately in the GC binaries. Source files are gzip-compressed to avoid creating Go packages in this repository. The raw 544 MB database and compiled binaries are excluded. The logical graph, original source, metadata benchmark, exporter and probe module files are preserved in `../containerd-root-dedup/`; repeating database timings requires another consistent metadata copy.

`carryover/` crosses the first candidate's preparation algorithm with its command-only flag in 32 measured edited commands. The preparation quartet has pair `-1`. All commands assert zero actual collection overlap. Heap counters and Go GC counts are recorded per case. Profiling is off. This uses the preceding diagnostic engine, hash `ec800d4328413f4e3b4b514a4006183ac5d4daea15a2636a580aff574ab24823`.

`allocation-profiles/` contains four separately profiled commands with Go collection forced outside their timers, plus wcprof traces and before/after heap profiles. Difference profiles include profiler allocations; their byte totals must not be treated as exact unprofiled command totals. For example, compare `0-off-off-before.pprof` and `0-off-off-after.pprof` with `go tool pprof -sample_index=alloc_space -base BEFORE ENGINE_BINARY AFTER`. Raw binary is excluded; its hash matches the preceding engine archive. A sampled check of span-index CPU cost is also retained.

`natural/` measures eight rotating original/refined/Cargo rounds, after a warm-up round. Ordinary collection stays enabled, with no scratch snapshots, forced Go collection or forced collection between cases. Final event reconciliation checks collection overlap, including jobs completing after the command. Native Cargo uses the same physical source and Rust 1.77.2, with incremental state outside the imported directory.

`concurrent/` measures the refined loop against the original in eight rotating four-case rounds: each algorithm with and without a forced overlapping collection. Scratch snapshots have one file; ordinary collection is deferred in both arms and drained after each case. Command and whole-case scopes differ. All slower observations and post-admission stalls are retained. `analysis.json` contains paired results; `samples.json` contains all cases. The first candidate's older 16/16 wins are in the previous archive and do not describe this refined engine.

`native-cold/` verifies cold compilation, complete reuse, a used-source edit, invalid Rust, repair and reversion with actual collection after every phase. `native-retained/` verifies all six older histories after restart and collection: 130/130, 1,026/1,026 and 6/6 twice. Large cache-inspection JSON files are compressed. These are correctness checks, not unchanged-build performance claims.

## Engine and reproduction boundaries

The refined diagnostic engine is `e174ad0a118c3312cebae1333d4dbaf1f2a1d3f56656a337629830bbe18092e8`, based on Dagger `19eda924854e7f22582f3a7430272aa729cbeb5f`. All 44 Dagger overlays are identical to `../containerd-root-dedup/engine/overlay-manifest.json`. The only added overlay replaces the local containerd module's `pkg/gc/gc.go` with the decompressed `engine/gc.go.gz`. Module files, exact source hashes and final diagnostic state are saved in `engine/`. The matching Dang dependency is in `../snapshot-gc/dang-build-input.tar.gz`.

The same owned engine exits cleanly before installation; the volume is preserved. `install/` contains exit evidence and shutdown stacks. The old binary is still running during that shutdown. Telemetry receivers, fixture paths, CLI binaries and the SDK fallback are local harness dependencies recorded in the drivers; adapt those paths before rerunning. The Rust module is `grouville/dagger-rust` revision `f73c5614a89968afa6f6000328e96ea33745fd93` throughout. No compiler worker code, key calculation or incremental-state policy changes.

Run `sha256sum -c SHA256SUMS` from this directory to verify every archived input and observation. All executable binaries and the raw retained database are excluded.
