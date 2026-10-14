# Branching native compiler state between edits

The worker can start an edited build from the latest immutable compiler-state
snapshot instead of copying its incremental directories first. In the 102-crate
fixture, shared edits improve from 1.405 s to 1.344 s median across ten pairs;
nine pairs improve. Leaf edits show no reliable gain. The prototype stays
separate: its current compaction policy retains more snapshot data.

The later [three-way interval comparison](NATIVE_COW_INTERVALS.md) includes a
four-build policy and filesystem allocation measurements across the cycle.
It confirms a modest shared-edit gain and a remaining storage tradeoff.

The module branch is
[`grouville/dagger-rust:experiment/native-batch-cow`](https://github.com/grouville/dagger-rust/tree/experiment/native-batch-cow),
commit `9ea2e57`, based on `d1aaf93`. Both timing variants use the same engine,
`ba5861200`, with native
checkpoints, durable cache hints and the reviewed imported-hash persistence fix.
No executor or lock changes are part of this experiment.

## What changes

When the latest batch supplies every selected incremental seed and its artifacts
need no overlays, mount that batch directly at the worker's output path. The
engine creates a writable snapshot with the original as its parent. Before
starting compilers, remove the outputs of actions being rebuilt. Exact-hit
artifacts remain available, and rustc can reuse its private incremental state.

Keep completed-result selection separate from seed selection. Reverting to an
older result, combining seed generations or changing compiler configuration uses
the existing path. Every mounted directory remains an ordinary execution input;
no compiler input is excluded from Dagger's cache identity.

Track the number of consecutive builds on each batch. After eight builds, copy
the batch into a fresh directory before the next execution. Checkpointing closes
the producer recipe; this periodic copy also breaks filesystem ancestry. The
count measures builds since compaction, rather than the snapshotter's total
number of parents. The initial batch and compaction directory have their own
parents.

## Complete-command comparison

Each sample runs the normal `dagger check rust:check` command after a distinct
host edit. Each variant has its own source tree, project key and native Cargo
target directory. They share an engine and toolchain, receive two preparation
edits per scenario, and alternate order. Timing includes client startup and
shutdown. Telemetry stays enabled through the local receiver; wcprof is disabled
during timing. Compaction runs are included.

| Edited scenario | Pairs | Copying path | Snapshot branch | Native Cargo, before / after |
| --- | ---: | ---: | ---: | ---: |
| Shared library | 10 | 1.405 s | 1.344 s | 0.476 / 0.483 s |
| Leaf library | 6 | 0.861 s | 0.852 s | 0.086 / 0.085 s |

Nine of ten shared pairs improve, by 4.4% at the medians. The shared compaction
sample takes 1.492 s versus 1.383 s for the control. Only two of six leaf pairs
improve; overlapping ranges and slower individual samples do not establish a
leaf-build benefit. Every native Cargo edit checks the expected 102 or 2 crates,
and all 32 subsequent automatic-cache probes reuse 102/102 actions.

The host remains contended: maximum CPU stall is 28.5% during the shared series,
and maximum I/O stall is 27.7% during the leaf series. These are local prototype
results, not a production remote-engine comparison. Both scenarios still exceed
the Cargo-plus-0.5-second target.

The two diagnostic profiles confirm the intended work removal. Copy time on the
compiler helper's critical path falls from 150.95 ms to 9.79 ms, with two copies
becoming one. Both recordings have zero dropped events and zero unfinished
operations. The profiled candidate's complete command is slower, 1.516 s versus
1.468 s, and its CPU stall is higher, 22.4% versus 14.8%. Compiler/workload time
increases in that capture. The profiles prove the large preparatory copy is
removed; they do not establish an additional build speedup.

## Correctness and retained storage

Focused race tests pass for the model, replay, worker and compiler wrapper.
The new tests cover removing rebuilt outputs while preserving exact hits and
incremental state, unsafe output paths, and valid bounded compaction metadata.

Eighteen separate shared edits through the actual four-crate module pass, with
the independent crate reused and the other three rebuilt. Compaction occurs at
edits 9 and 17. A breaking shared-library type change fails without replacing
the retained cache; restoring valid source and reverting to a recent retained
version both reuse 4/4 actions. A subsequent new edit succeeds through the
fallback path. The diagnostic initially used an unavailable session-local
wrapper ID; restoring the native fields fixes that driver setup. Its first
expectation also omitted the fixture's independent crate. Those failed runs are
not counted as implementation failures or performance samples.

The writer/reader integration passes cold compilation, an app edit, reversion,
transfer to the second engine, 4/4 transferred reuse and another app edit with
3/4 reuse. Separately, a clean engine restart rediscovers the shared-edit cache
with 4/4 reuse and recompiles a new shared edit with 1/4 reuse, without any host
cache metadata.

Across 25 shared edits, pruning leaves the latest cache's graph at 293 results
and 55 snapshot references before compaction, or 294 and 56 just after it.
The same values recur at edits 8/16/24 and 9/17/25. Evicting the project hints
and pruning removes every Rust cache/result object.

Graph references do not count physical parent snapshots. A separate 17-edit
series reads the stopped engine's snapshot metadata to walk the actual parent
chains of the five retained compiler batches. A matched series measures the
original copying path:

| After 17 shared edits | Copying path | Snapshot branch |
| --- | ---: | ---: |
| Unique snapshots, including parents | 20 | 15 |
| Accounted snapshot bytes | 85,458,944 | 114,495,488 |
| Largest retained chain, including its root | 5 | 10 |
| Latest batch's chain, including its root | 5 | 3 |

The latest candidate batch has a short chain after compaction, but retaining
recent results also retains their older parent chains. Accounted bytes are
34.0% higher in this sample. These are the snapshotter's recorded usage totals,
deduplicated by snapshot ID; they are not a measurement of unique allocated
disk extents or a remote transfer size. The five-batch comparison excludes the
module/toolchain graphs that dominate whole-cache usage.

## Decision and next experiment

Keep the prototype isolated. It removes a measured copy and gives a modest
shared-edit improvement, but eight-build compaction adds retained data and tail
latency. Compare a shorter interval with the same edited CLI protocol before
selecting it. Measure peak storage across the compaction cycle, actual transfer
cost and compiler work as well as the median. Fresh-process startup, query and
module overhead, remote discovery, and registry/build-script/procedural-macro/test
coverage remain part of the original goal.

Artifacts live under `/tmp/rust-cache-sipsma-review`: `module-batch-cow-102`,
`batch-cow-correctness`, `batch-cow-transfer`, `batch-cow-retention`,
`batch-cow-ancestry` and `batch-copy-ancestry`. The corresponding scripts are
`measure_batch_cow_pairs.py`, `check_batch_cow.py`,
`check_batch_cow_retention.py`, `check_batch_cow_ancestry.py` and
`check_batch_copy_ancestry.py`. The offline inspector is `snapshot_ancestry.go`.
