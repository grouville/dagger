# Whole compiler-input snapshots

Reject this experiment as a performance optimization. Copying the complete
selected batch into one fresh input snapshot keeps filesystem chains short and
storage near the original path, but makes edited commands slower. The result
also argues against selecting a strategy from directory-copy counts alone.

The module branch is
[`grouville/dagger-rust:experiment/native-batch-whole-input`](https://github.com/grouville/dagger-rust/tree/experiment/native-batch-whole-input),
commit `8a229e2`, based on `a761a75`. When the latest batch supplies every selected seed and needs
no artifact overlays, copy that batch once without filters. The worker removes
outputs being rebuilt before scheduling compilers. Other cases retain the
existing path. Each new eligible batch has depth one; metadata from the older
eight-build policy remains accepted. Exact-result keys and ordinary mounted
compiler inputs remain unchanged.

The implementation removes periodic compaction and its depth selection from
this path. It changes no engine or lock code. All comparisons use engine
`ba5861200`, with telemetry enabled through the local receiver.

## Edited normal CLI commands

The original copying path, whole-input copying and four-build branching run on
the same engine, with independent sources, Cargo targets and project keys.
Order rotates. Each scenario receives two preparation edits, followed by twelve
shared edits or eight leaf edits. Every edit is fresh, timing includes startup
and shutdown, and wcprof is disabled. Native Cargo checks the expected 102 or
two crates, and all 60 later automatic-cache probes reuse 102/102 actions.

| Median complete command | Original copying | Whole input | Four-build branching |
| --- | ---: | ---: | ---: |
| Shared edit | 1.390 s | 1.413 s | 1.341 s |
| Native Cargo, shared | 0.472 s | 0.480 s | 0.471 s |
| Leaf edit | 0.859 s | 0.930 s | 0.898 s |
| Native Cargo, leaf | 0.086 s | 0.086 s | 0.086 s |

Whole-input copying beats the original in only 4/12 shared rounds and 0/8 leaf
rounds. Four-build branching beats it in 10/12 shared rounds and 2/8 leaf rounds.
Maximum CPU stall is 20.3% for shared edits and 10.9% for leaf edits; I/O stall
is 2.5% and 3.7%. This is a local prototype comparison.

The diagnostic helper critical path is 966.88 ms for original copying,
985.48 ms for whole-input copying and 943.31 ms for four-build branching.
Copy time on that path drops from 127.89 ms to 94.95 ms for whole-input copying,
but its profile also spends more time in process preparation. All three
captures have zero dropped events and zero unfinished operations. Less recorded
copy work does not establish a faster complete command.

## Storage and correctness

The separate storage study makes 25 shared edits per policy in the same
four-crate fixture. At six stages, prune, stop the idle engine cleanly, inspect
its copied snapshot metadata, restart and measure the selected batch snapshots
with `du`, counting hard links once.

| Across six stages | Original copying | Whole input | Four-build branching |
| --- | ---: | ---: | ---: |
| Filesystem usage | 57.4 MB | 57.7 MB | 57.2–85.9 MB |
| Physical snapshots, including parents | 20 | 12 | 9–13 |
| Longest chain, including root | 5 | 4 | 6 |

Whole-input usage is stable and 0.5% above original copying. Fewer snapshots and
shorter chains do not compensate for the measured command slowdown. These
figures exclude the module/toolchain graphs and do not measure remote transfer
bytes or general filesystem extent sharing.

Focused compiler race tests pass. The real module migrates a depth-eight cache
with 4/4 exact hits, keeps every subsequent eligible batch at depth one, and
passes failed type changes, valid reversion, recent-version reversion and a
new edit afterward. All 18 automatic-cache probes after six clean restarts
reuse 4/4 actions without host cache state. Native export/receiver integration
passes cold compilation, an app edit, reversion, automatic plan refresh and
unsupported-input rejection. The second engine reuses 4/4 transferred results
and supports a new app edit with 3/4 reuse. These checks are separate from timing.

## Continue the original scope

Keep this branch isolated. The current native backend handles `check`; the
normal `build` and `test` entrypoints still use Cargo's cache volumes. The next
implementation work should extend the native path to those entrypoints, while
preserving compiler results, incremental state and result correctness.

A new fixture under `/tmp/rust-cache-sipsma-review/native-tests-next/source`
has two path crates, unit and integration tests, and a runtime input outside
the crate directories. Native Cargo passes its four tests and correctly fails
after changing only that runtime input. This is a control fixture, not an
implemented native test backend. It will detect a cached test result whose key
omits workspace runtime files. Registry dependencies, build scripts,
procedural macros, remote discovery and the Cargo-plus-0.5-second performance
target remain unfinished.

Artifacts live under `/tmp/rust-cache-sipsma-review`: `module-whole-input-102`,
`batch-whole-input-compat`, `whole-input-storage`, `whole-input-transfer` and
`native-tests-next`. Scripts are `measure_whole_input.py`,
`check_batch_whole_input_compat.py` and `check_whole_input_storage.py`.
