# Comparing compiler-state compaction intervals

Compacting after four builds reduces the eight-build experiment's retained data
and slightly improves its shared-edit median. It still does not establish a
leaf-edit benefit, and its sampled peak filesystem usage remains about 50% above
the copying path. Keep both branching policies isolated.

The new module branch is
[`grouville/dagger-rust:experiment/native-batch-cow-four`](https://github.com/grouville/dagger-rust/tree/experiment/native-batch-cow-four),
commit `a761a75`, based on `9ea2e57`. The implementation changes only the compaction interval and
its condition. The engine remains `ba5861200`; no executor, filesync or lock code
changes in this comparison. The [eight-build report](NATIVE_BATCH_COW.md) explains
the native inputs and result-selection design.

## Edited commands

All three variants run on the same engine, with separate source trees, project
keys and Cargo target directories. Run order rotates across the variants. Each
scenario receives two preparation edits, followed by 16 shared edits or eight
leaf edits. Every edit is fresh. The normal `dagger check rust:check` command
includes startup and shutdown, telemetry stays enabled through the local
receiver, and wcprof is disabled during timing. Compaction samples are included.

| Median complete command | Copying | Eight-build interval | Four-build interval |
| --- | ---: | ---: | ---: |
| Shared edit | 1.413 s | 1.366 s | 1.350 s |
| Native Cargo, shared edit | 0.481 s | 0.479 s | 0.483 s |
| Leaf edit | 0.855 s | 0.851 s | 0.862 s |
| Native Cargo, leaf edit | 0.088 s | 0.087 s | 0.086 s |

The four-build variant beats copying in 13/16 shared rounds and the eight-build
variant in 13/16. Its median is 4.5% below copying. For leaf edits, it beats
copying in only 3/8 rounds. Both scenarios still exceed Cargo plus 0.5 seconds.

Four-build compaction samples take 1.486, 1.426, 1.474 and 1.461 s. The two
eight-build compaction samples take 1.451 and 1.487 s. One copying sample takes
2.387 s; it remains included, and the cause was not profiled. Maximum CPU stall
is 22.6% in the shared series and 12.2% in the leaf series; maximum I/O stall is
2.6% and 4.6%. This is a local comparison, not a production remote benchmark.
Every Cargo run checks the expected 102 or two crates. All 72 subsequent
automatic-cache probes reuse 102/102 actions.

Diagnostic wcprof captures show critical-path directory copies of 132.61 ms
for copying, 10.11 ms for the eight-build variant and 9.47 ms for the four-build
variant. The compiler helper's critical path is 981.62, 906.53 and 915.74 ms.
All captures have zero dropped events and zero unfinished operations. These
single captures confirm removal of the large preparation copy; the four-build
profile does not establish a further compiler-helper improvement over eight.

## Physical retention

A separate study makes 25 shared edits in each four-crate fixture. At edits
17, 19, 20, 23, 24 and 25, prune, stop the idle engine cleanly, copy its snapshot
metadata and walk the parent chains of the five retained compiler batches.
After restart, measure those snapshot directories with `du`, counting hard
links once. The selection comes from native Directory fields returned by the
module, rather than a whole-cache size that includes the toolchain and module.

| Across the six measured stages | Copying | Eight-build interval | Four-build interval |
| --- | ---: | ---: | ---: |
| Filesystem usage, minimum | 57.4 MB | 57.2 MB | 57.2 MB |
| Filesystem usage, observed peak | 57.4 MB | 124.0 MB | 85.9 MB |
| Snapshot accounting, observed peak | 85.5 MB | 133.5 MB | 95.4 MB |
| Longest observed chain, including root | 5 | 10 | 6 |

Four-build compaction reduces the sampled filesystem peak by 30.7% relative
to eight builds, but remains 49.7% above copying. Eight builds reach 116.1%
above copying. Their minimum occurs when older history finally leaves the
retained set, so measuring only that point would hide the cost.

Directory-copy profiles describe operations, not the bytes newly allocated.
Snapshot accounting counts each snapshot separately; filesystem usage counts
shared inodes once. Neither measurement is a remote transfer measurement or a
general proof of unique physical extents on other filesystems. These samples
exclude the module/toolchain graphs.

## Compatibility and correctness

Keep the accepted metadata depth at eight while setting the producer's interval
to four. Compact when the selected depth is **at least** the current interval.
Lowering the validator's limit would reject previously valid caches; comparing
depth only for equality would skip compaction when loading an older depth-eight
batch. The interval does not enter the exact-result compatibility key, because
it changes storage policy rather than compiler inputs or outputs. Mounted seeds
remain ordinary execution inputs.

The real module loads a depth-eight cache under the four-build policy and reuses
4/4 exact results without changing its manifest. Its next shared edit compacts
to depth one. Subsequent shared edits stay within the four-build interval.
A breaking type change leaves the prior cache usable; valid reversion and a
retained older version both reuse 4/4 results, and a new edit succeeds afterward.
Focused compiler race tests pass. In the storage study, every new edit reuses
the independent crate, and all 18 cache probes after six clean engine restarts
reuse 4/4 actions without host cache state.

## Next experiment

The gain is too small to justify selecting either interval with its storage
and compaction costs. Test constructing one fresh input snapshot per build,
using the complete selected batch where appropriate and removing rebuilt outputs
inside the worker. This could avoid repeated filtering and intermediate
directory construction while retaining short physical chains. Measure it rather
than assuming a directory copy always duplicates file bytes.

The broader goal remains edited commands within Cargo plus 0.5 seconds, native
cache discovery across engines, retention/transfer policy and support for real
Cargo dependencies, build scripts, procedural macros and tests.

Artifacts: `/tmp/rust-cache-sipsma-review/module-cow-intervals-102`,
`batch-cow-four-compat` and `cow-interval-storage`. Scripts:
`measure_cow_intervals.py`, `check_batch_cow_four_compat.py` and
`check_cow_interval_storage.py`. `native_cache_inspect.go` records native fields
for diagnostics; `snapshot_ancestry.go` reads the stopped engine's metadata copy.
Sipsma's latest 12 public PRs were rechecked on October 14; the result is
`sipsma-latest-oct14-cow-intervals.json`. That check changes no measured engine
dependencies.
