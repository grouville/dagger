# Reuse the listing command's workspace

Measured 2026-09-25 on the static-TypeScript experimental engine. This is an isolated CLI change, independent of the batch index and SDK prototypes.

## Outcome

The generic CLI change removes a redundant global artifact discovery and keeps selection/alias formatting on the same workspace snapshot. **No whole-command speedup was established in eight matched triples.** Keep that distinction when reporting it.

| CLI | Warm median | Range | Samples |
| --- | ---: | ---: | ---: |
| Existing baseline | 2.351 s | 2.153–3.937 s | 8 |
| Source-prefix filter only | 2.353 s | 2.050–3.251 s | 8 |
| Prefix filter + workspace reuse | 2.410 s | 2.262–2.560 s | 8 |

Prefix-only was faster in 6/8 matched comparisons, with a median paired difference of −171 ms, despite its overall median being flat. Adding workspace reuse was faster in only 2/8 comparisons with prefix-only, with a median paired difference of +108 ms. Against baseline, the combined candidate was faster in 4/8 pairs and the paired median difference was +33 ms. These eight samples do not justify a whole-command gain claim for either candidate.

Each CLI is CGO_ENABLED=0 and built with -buildvcs=false. The two candidates were built with the same settings as the supplied baseline; an earlier prefix executable had CGO enabled and was deliberately excluded from this comparison. The test used fresh CLI processes, the normal direct Cloud path, one retained engine, two warmups per CLI, and eight triples in rotating permutation order. No compilation overlapped the timed commands. The complete experimental engine includes Dang and TypeScript optimizations; these results are not the unmodified collections branch.

The command was `dagger --engine container://dagger-engine.collections-disk-abba-2 check -l --all`, from `/tmp/collections-perf/sdk-edit-audit/ts-static/greetings`. All 24 timed commands returned exactly the same 14 rows, SHA-256 `c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`.

Full host I/O pressure stalls were only a few milliseconds per sample. The wall-time outliers are not proven to be Cloud delays. Separate wcprof captures also show variation in the initial module/schema/network phase.

## What wcprof proves

Profiles were captured separately from timing, one baseline and one combined candidate; both report zero dropped events.

| Fact | Baseline profile | Combined profile |
| --- | ---: | ---: |
| Workspace.artifacts call_exec count | 2 | 1 |
| Late redundant global catalog | 18.45 ms | absent |
| Engine operation count | 21,399 | 20,759 |
| Initial Workspace.artifacts | 587.55 ms | 815.31 ms |
| Artifacts.__itemsJSON expansion | 638.10 ms | 634.84 ms |
| Operation envelope | 1,290.26 ms | 1,502.44 ms |

The candidate removes the intended repeated catalog work. It does not explain or eliminate the remaining initial metadata variation. Both profiles retain seven Git public-advertisement probes, around 80–200 ms apiece and overlapping; their durations must not be added as if they were all on the critical path. No network response or permission result is retained by this CLI change.

## Change and correctness contract

`commandArtifactsWithFlags` pins the live workspace once before resolving flags and returns it with the selected Artifacts. `listArtifactSelection` uses this same pinned workspace for global aliases instead of calling `dag.CurrentWorkspace()` again. The old pin inside `commandArtifacts` is removed, so there is no second pin RPC. The workspace is not saved across commands: a later CLI invocation observes source edits normally.

Formatting still reads the unfiltered artifact catalog. Reusing only selected dimensions would be incorrect: a different Go, TypeScript or Dang module can make an otherwise short flag ambiguous. All helper callers are wired: check, up, generate, shell and agent; composition-only callers discard the workspace result.

Focused existing artifact/selection CLI tests pass. New transport-level regression tests model global Go/TypeScript/Dang dimension collisions, path-filtered listings, a nested module/test collection, and a dimension-free listing. They assert one currentWorkspace read, use of that workspace identity for all projections, global rather than filtered alias resolution, and no needless alias catalog for dimension-free output. They are CLI-unit fixtures, not three SDK integration runs.

The real filtered command `check -l --all go/modules/tests/run --go-module=. --go-test=TestFormatResponse` returned the same one row for all three executables, SHA-256 `d970362779286df20ff90dd031cc2914a35166ee6de3db4431d3660e3e2088dc`. Source hashes for main.go, main_test.go and dagger.toml were unchanged. Both task-owned engines were stopped before the performance slot was released.

## Evidence

- `measured/manifest.json`: CLI hashes, engine provenance, workspace and source hashes.
- `measured/results.json`, `summary.json`, `paired-summary.json`: raw timings and comparisons.
- `measured/profile/{baseline,reuse}/run.wcprof`, `profile-summary.json`: profiling evidence.
- `test.log`: focused test results.
- `workspace-reuse.patch`: isolated CLI patch, excluding the prefix optimization.
- `pipeline-review.md`: why per-module discovery/expansion pipelining is a larger change requiring loader publication and dependency work.

There is no cold-start or real-edit timing claim from this experiment. The parent is running actual execution and edit checks separately.
