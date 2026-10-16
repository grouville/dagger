# Avoid transitive output lists in native batch history

The later [artifact-input fusion](NATIVE_ARTIFACT_INPUT_FUSION.md) builds on this change and is the next experimental native-cache baseline. Measurements below describe the original deep-artifact experiment.

The batch path no longer recopies every ancestor's output paths into every crate's retained view. A 1,000-action chain drops from 125 ms to 28 ms of local graph construction after an edit, with 52 MB fewer allocated bytes. Complete 512-crate collection checks near the end of the chain improve by about 75 ms in both history assignments. The shared edit and small workloads do not establish a general speedup.

Use this as the next experimental native-cache baseline. The removal of quadratic output-list work and the repeated tail-edit improvement justify the change, with explicit coverage of cached artifact restoration. The official module's native backend remains opt-in. No PR is opened.

The fork has two reviewable commits: [tests and benchmarks](https://github.com/grouville/dagger-rust/commit/c748e82), then [production change f73c561](https://github.com/grouville/dagger-rust/commit/f73c5614a89968afa6f6000328e96ea33745fd93). Both start from the previous native baseline, `e63b6a2`. The production diff adds 54 lines and removes 51, largely by moving worker setup into the branch that actually compiles.

## Change and correctness

The existing worker prepares transitive dependency views from graph edges. Retained batch targets therefore only need each action's own outputs. The previous implementation also copied and sorted all ancestor output paths for every action, even when the worker would reconstruct that information independently. On a chain, those lists grow quadratically.

An entirely cached batch now assembles its retained targets directly instead of entering the per-action container builder. Old artifact overlays are applied even when no new compiler action runs. This matters when reverting source: the most recent batch root may contain newer files than the selected cached results. The non-batch path keeps its existing transitive views.

Compiler commands, worker binary, per-crate result keys, seed compatibility, cache format and snapshot retention policy stay unchanged. The change adds no API, shared state, lock or dependency.

The integration test compiles and runs a three-crate binary after an initial build, a middle edit, an entirely cached reversion, an app edit using retained transitive inputs, and a mixture of an older dependency with a new compilation. It checks the binary's output and exact compiler reuse. Both the reference and candidate pass. A deliberately incorrect variant that omits overlays on cached reversions fails by printing 12 instead of 2; this verifies that the test detects stale artifacts.

The main package compiles, and model/replay/worker suites pass with the race detector. Both new 512-action histories subsequently reuse 512/512 results and retain exactly the preceding 256-action batch. All six earlier histories also retain 130/130, 1,026/1,026 and 6/6 results.

## Local constructor benchmark

Six fresh-process A/B and B/A pairs use identical benchmark sources. The baseline overlays only `history.go` and `batch.go` from `e63b6a2`. Fixed GraphQL responses isolate local construction; this benchmark performs no engine filesystem work or compilation. Every measured operation constructs a new graph. “Empty history” describes the builder input, not a cold engine.

| Shape and input | Before median | Candidate median | Allocated bytes before → candidate | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Chain, 100 actions, edited tail | 3.91 ms | 2.85 ms | 2.41 MB → 1.90 MB | 6/6 |
| Chain, 1,000 actions, empty history | 122.33 ms | 24.82 ms | 72.52 MB → 20.18 MB | 6/6 |
| Chain, 1,000 actions, edited tail | 124.51 ms | 27.93 ms | 72.74 MB → 21.09 MB | 6/6 |
| Wide, 1,000 actions, edited tail | 27.66 ms | 28.31 ms | 21.05 MB → 21.25 MB | 3/6 |

The targeted output-list duplication disappears in batch mode. This is not a claim that every part of graph construction is linear or that wide workspaces improve.

## Complete edited commands

The real workspace contains 511 libraries in a chain and one application. A tail edit recompiles two actions; an edit at library 256 recompiles 256. Every native command uses the normal `rust:packages/check` collection. Cargo verifies those expected compiler counts.

Each series has eight rotating baseline/candidate/Cargo pairs per edit. The confirmation exchanges implementations between the physical histories. Each command has a fresh used-source edit and a fresh CLI/helper process. Engine and compiler state are warm after two preparation rounds. The first history preparations take about 68 seconds per native arm and 28 seconds for Cargo; they are excluded from edited-command timings.

Both arms use the same engine, `a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa`, with source snapshot seeds, compact scalar restoration, batch telemetry metadata reuse and the attribute-array decoder. Telemetry stays enabled. Profiling and wcprof are off during timing. Cargo uses incremental Rust 1.77.2 and eight workers.

| Series | Edit | Before median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Paired | Tail | 1.352 s | 1.273 s | 1.240 s | 38 ms | 6/8 |
| Paired | Shared middle | 21.903 s | 21.663 s | 21.311 s | 310 ms | 7/8 |
| Crossover | Tail | 1.313 s | 1.237 s | 1.255 s | 69 ms | 6/8 |
| Crossover | Shared middle | 21.801 s | 21.810 s | 21.242 s | 158 ms | 5/8 |

Tail medians improve in both series, with 12/16 faster pairs. Shared-edit column medians do not confirm the first series' improvement. Column-median differences and medians of paired differences measure different things. Median paired candidate-minus-Cargo overhead is 44/-25 ms for tail edits and 442/653 ms for shared edits across the two series. The full Cargo +0.5-second target remains unmet.

Launches require an idle engine and a quiet one-second admission window. Every admitted sample remains included, including later stalls. Maximum measured host I/O pressure is 20.59% in the first series and 8.34% in the crossover; engine-only I/O maxima are 7.77% and 4.88%.

## Controls and profiles

Eight pairs also repeat the older workloads: direct 130-crate checks are 0.630 → 0.634 s, wide 1,026-crate checks 1.555 → 1.566 s, and small collection tests 0.986 → 1.030 s. Win counts are 4/8, 4/8 and 2/8. The possible small-test regression is checked with a dedicated history crossover: 0.954 → 0.956 s, 5/8 faster, 13 ms median paired saving. It does not reproduce the earlier 44 ms median difference. No general improvement is established for these controls. A 26.339-second baseline wide-check outlier remains included; host I/O stalls reach 32.56% in that control series.

Eight separate wcprof captures contain no dropped events or open operations. Each executes the Go compiler helper once. Tail helper calls take 726/731 ms before and 655/672 ms after, while the nested worker workloads stay around 298–304 ms. Shared worker workloads take roughly 20–24 seconds. Source imports, package hashing, mount preparation and publication remain separate costs. The critical-path report labels a broad `dang.invoke` interval because cross-client blocker linkage is incomplete; that interval includes nested helper and engine work and is not interpreter CPU.

The [CPU accounting clarification](CPU_ACCOUNTING.md) distinguishes engine-only counters from the Docker total. The new profile data records both plus the sibling workload cgroup. Two shared candidate captures have higher engine CPU, and their 30-second engine profiles include substantial post-session pruning: 5.98 cumulative sampled CPU seconds across both recordings enter `gcAfterSessionCompletion`, including 4.21 seconds under `measurePruneState`. Those captures include work after command completion, so they do not establish the cause of each timed outlier or a compiler CPU regression. They identify cache accounting as a concrete next investigation.

Evidence includes all timed samples, admission/pressure records, exact source revisions, the integration-test mutation check, raw CPU profiles, compressed wcprof captures, critical paths and reproducible fixture/benchmark drivers: [deep-artifact-closures](experiments/deep-artifact-closures/). Paths in the drivers and overlays must be adjusted when reproducing elsewhere.
