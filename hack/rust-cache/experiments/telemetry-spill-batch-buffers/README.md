# Telemetry spill batch-buffer evidence

[The report](../../NATIVE_TELEMETRY_READ_BUFFERS.md) separates component performance, complete edited commands, correctness and remaining work. The standalone branch is `grouville/dagger:perf/telemetry-spill-batch-buffers`, revision `18f246dd1842faed187bffd637a35394951e7891`, based directly on main `717589c9ccacbba7d3cf902647aa5c9ca68085e8`. No PR is open.

## Sources and component checks

`source/before/` and `source/after/` preserve the two production/test files from those exact revisions. Go source is compressed so the evidence directory does not become a Go package. The branch adds four production lines and removes one in `readSince`, reusing the existing `nextInto` implementation and reader pool.

`runs/paired/` contains six fresh-process before/after comparisons. Test binaries are compiled before measurement, `GOMAXPROCS=8`, 150 ms per case. File creation and appends are outside the timer. Both one- and 512-row cases improve in all pairs. Pressure and raw logs are retained. `runs/component-provenance.json` records the revision, toolchain, host, paired savings and maximum pressure.

`runs/race.log.gz` is the complete client-database race suite. `runs/before-test.log.gz` proves the ownership test also passes on main. `runs/borrowed-fields-mutant.log.gz` records the deliberately broken decoder failing. Both engine-mode ownership tests pass in `engine/diagnostic-mode-test.log.gz`. The initial race invocation with cgo disabled is retained separately; Go requires cgo for the race detector.

From the standalone checkout:

```sh
go test -race -count=1 ./engine/clientdb
go test -run '^$' -bench '^BenchmarkSpillFileReadSince$' -benchmem ./engine/clientdb
```

## Complete edited commands

`runs/commands-stable/` and `runs/confirmation/` each contain eight rounds across four workloads and three arms: 1,026-crate grouped checks, 130-crate direct checks, small workspace tests, expanded package listings; baseline, candidate and Cargo. The confirmation reverses case orders. Preparation round -1 is excluded from the summary. All 192 admitted observations remain included.

Every arm changes a Rust value before a fresh process. Both engine modes use Rust module `3cd40e5`, the same physical source and native history. Compiler/engine caches are warm. Cargo is incremental Rust 1.77.2 with eight workers and an external target directory. Telemetry stays enabled with the local receiver; ordinary engine/Go collection remains enabled. Wcprof, added scratch snapshots and forced collection are absent from timing. CPU, allocation, GC counts, pressure and collection overlaps are saved. Parent Docker CPU overlaps engine/compiler counters and must not be added to them.

`runs/pooled-summary.json` retains individual paired differences. Listings allocate 108 MB less per pair in 15/16 pairs; complete latency and engine CPU remain mixed. This is an allocation improvement, not established faster Rust compilation or lower peak/resident memory.

The initial attempt in `runs/commands/` fails quiet admission before executing a command. `runs/post-restart-admission.jsonl` retains the later monitor; three quiet windows precede the unchanged driver. Initial failures and post-admission stalls are not discarded. The local script paths must be recreated or adjusted before rerunning.

## Correctness and diagnostics

`retained-cache/` explicitly prepares current inputs and then requires complete reuse in all six native histories: 130/130, 1,026/1,026 and 6/6 twice. A final Cargo/listing source edit may not have been compiled by Dagger, so preparing that input is intentional. Unchanged calls establish correctness, not timing wins.

`profiles/` contains four separately profiled edited commands, including engine/CLI CPU, CLI runtime trace, wcprof and bounded goroutine captures. All final wcprof files have zero dropped events and open operations. Profile timings do not enter the cohorts. Saved critical paths and CPU summaries identify publication, source import and telemetry conversion that remain after this change.

`allocation-discovery/` records how the active path was found. Initial unforced allocation snapshots lag earlier GC cycles and are preserved. The separate flushed snapshots force two GC cycles before and after a command to expose allocation stacks; their durations are diagnostic only.

`unselected-protobuf/` preserves a separate library experiment against Protobuf v1.36.11. The fully typed sort regresses large messages; the small-message variant improves a sample encoder but has no complete-command evidence. Its JSON/text/binary and client-database race suites pass. It is not installed in this engine or counted as a ready proposal. Dependency overlays point into a local source copy: Go forbids modifying the module cache through overlays.

## Engine and lifecycle

`engine/` contains exact build commands, the overlay manifest/hashes, modfiles, diagnostic switch source and installation records. Engine hash is `8e31c79773355d11bac9854a3a641534c7733171953c483993e5888a290b6734`. Existing overlay sources are shared with `../containerd-root-dedup-followup/` and its referenced archives. Only the spill-reader diagnostic and debug route are added; the Protobuf experiment is absent.

The old engine exits cleanly after 157.6 seconds; the volume is preserved. Its last goroutine dumps wait in `unix.Syncfs`. Those waits belong to the old binary. `runs/final-engine-state.json` verifies the new binary, restored controls, ordinary collection, profiling off and no active clients. The buffer switch is restored off between experiments. Large binaries and databases are excluded.

Logs, Go source, wcprof and runtime traces are compressed; decompress before use. Verify contents with `sha256sum -c SHA256SUMS` from this directory.
