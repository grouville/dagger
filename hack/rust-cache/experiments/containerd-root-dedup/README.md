# Containerd duplicate-root experiment

The candidate remains under validation: concurrent collection improves, but the second idle control cohort slows in all eight pairs. See [the report](../../NATIVE_GC_ROOTS.md) and [draft description](../../upstream-prs/containerd-root-dedup.md). No PR is open.

## Standalone upstream regression and patch

`upstream-source.patch` applies to containerd main `c787e39387ec2de521a14985f6785c53dfefaad7`. It contains only the root-loop fix and an addition to the existing GC test file. No dependency, diagnostic or Dagger change is required. In a checkout of that exact revision, apply only the test first:

```sh
git apply --include=pkg/gc/gc_test.go /absolute/path/to/upstream-source.patch
go test -mod=mod -count=1 -run '^TestTricolorDuplicateRoots$' ./pkg/gc
```

The test fails because each duplicated root's references are visited twice. Then apply the production hunk:

```sh
git apply --include=pkg/gc/gc.go /absolute/path/to/upstream-source.patch
go test -mod=mod -race -count=1 -v ./pkg/gc
go vet -mod=mod ./pkg/gc
```

All three package tests pass, with no skips, on Go 1.27.0. `upstream-revision.json` records the source and patch hashes. `validation/upstream-baseline.log.gz`, `validation/upstream-race.log.gz` and `validation/upstream-vet.log.gz` are the raw outputs. Repository-wide lint was not run; `golangci-lint` is unavailable. The patch is provided for human review, rather than submitted to containerd.

## Component measurements

`component/` contains six alternating fresh-process comparisons on Dagger's actual retained metadata. `source/` contains the exact original and candidate GC files, graph exporter, independent-oracle check and read-only metadata benchmark. `graph/retained-graph.json.gz` preserves the logical roots, edges and expected marked set; `graph/capture.json` identifies the consistent database copy. Raw database and executable binaries are excluded.

Repeating the database timings requires a consistent metadata copy from another engine. The exported logical graph supports inspection of the repeated roots, but does not preserve database page layout or reproduce the database lookup timings. The component driver records local paths and binary hashes; rebuild its four benchmark binaries and adjust those paths for another machine. Do not run the readonly benchmark against an actively changing database.

The measured production candidate decompresses from `source/production-gc.go.gz` to hash `9794e395f644f597cfebeeaf1f82d4b2c8da5ae8f1590ad794ce4047775c87a5`. This is byte-for-byte the patched current-main GC source. The diagnostic variant used by the live engine is different and is stored in `engine/diagnostic-gc.go.gz`. Go sources are compressed so this evidence directory does not introduce packages into the Dagger build.

## Complete edited commands and profiling

`commands/` contains the eight-pair 10,000-file cohort. `one-file/` contains its eight-pair confirmation with reversed case order and one-file scratch snapshots. Preparation quartets have pair `-1` and are excluded from the summary. No timed observations are discarded. Each directory retains command logs, admission checks, CPU/pressure counters and every sample; `analysis.json` includes the paired results. Command and whole-case times have different scopes: the latter includes teardown and final collection.

Both arms defer ordinary containerd collection and drain it after each case. The concurrent arm forces an additional collection immediately before starting the command. The selected algorithm also runs during preparation and final cleanup. These measurements show interference when collection overlaps compilation, rather than natural collection frequency or a scheduling-policy benefit. The idle confirmation slowdown remains unexplained.

`wait-profiles/` contains separate wcprof traces, goroutine captures and the engine CPU profile locating the foreground lease wait. These diagnostic runs used the preceding engine, before installing the candidate. Profiling is disabled in both timed command cohorts.

The native module is `grouville/dagger-rust` revision `f73c5614a89968afa6f6000328e96ea33745fd93`. Native correctness runs in `native/` cover cold compilation, reuse, a used-source edit, invalid Rust, repair and reversion, with real collection after every phase.

## Engine source and final state

The diagnostic engine is based on Dagger `19eda924854e7f22582f3a7430272aa729cbeb5f` with 44 overlays recorded in `engine/overlay-manifest.json`. Source paths are relative to this experiment directory; identical files reuse `../snapshot-gc/overlay-source/`. The matching local Dang dependency is archived as `../snapshot-gc/dang-build-input.tar.gz`. `engine/engine.go.mod` records the local containerd replacement and exact other dependencies.

`engine/source-audit.json` verifies that `pkg/gc/gc.go` is the only changed non-test Go file in that containerd replacement. The diagnostic flag defaults to false. The engine restarted cleanly while preserving its existing volume. At capture, the candidate is disabled, ordinary collection is enabled, profiling is off and there are no active requests; see `engine/final-engine-state.json`. No selected module code or native result key changed.

Verify archived file contents with `sha256sum -c SHA256SUMS` from this directory. Large binaries and the 544 MB raw metadata database are intentionally excluded.
