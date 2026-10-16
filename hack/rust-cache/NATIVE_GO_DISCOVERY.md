# Go module discovery performance

The follow-up branch is [perf/module-discovery](https://github.com/grouville/go/tree/perf/module-discovery), code revision `b5dd9434a52972787171a016a8aa9d8910c17c38`. It builds on the earlier package-scoped test-name search at `9a1ea73ec6dffa72e3f450ea413ad93bc323ecd8`. These measurements compare those two revisions, rather than adding gains from different cohorts.

The changes stop module validation at the first owned Go file, index nested module roots for ancestor lookups, append already ordered sort entries directly, and request filenames when discovering which packages contain tests. The index is constructed inside each call; the measurements include building it. Sorting still copies accumulated lists and retains its original insertion fallback.

## Final measurements

On a separate clean `dagger/dagger` checkout at `ff0b029a4d270a651b9a8c7286babc79089066e4`:

| Command | Before | After | Engine allocations, before → after | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| List 80 module roots | 38.32 s | 12.85 s | 23.17 → 1.81 GB | 2/2 |
| List 2,495 owned root-module Go files | 23.36 s | 3.57 s | 21.25 → 1.56 GB | 2/2 |

Two balanced pairs on the final committed code. Every arm starts a fresh CLI and makes a new source edit. Both implementations return byte-identical module and file lists; the latter is checked for count and byte order. An earlier four-pair cohort on the preceding indexed prototype also improved every pair. Its exact source snapshots and observations are retained separately.

The complete edited test-collection command uses eight real unit tests per package:

| Packages | Before | After | Workspace batch | Native Go | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.94 s | 0.91 s | 0.85 s | 0.21 s | 3/4 |
| 16 | 2.39 s | 2.44 s | 0.94 s | 0.23 s | 2/4 |
| 64 | 8.53 s | 7.65 s | 1.16 s | 0.26 s | 4/4 |

Four balanced pairs per size. At 64 packages the median paired saving is 0.96 seconds. Allocations fall from 4.49 to 3.92 GB and engine-container CPU from 27.97 to 22.35 CPU-seconds. Allocations are cumulative over a command, not peak resident memory. Native CPU is outside the engine cgroup and is not compared to that counter.

Smaller latency controls are mixed. The 16-package median paired slowdown is about 100 ms. One package with 16 test files measures 1.33 → 1.41 seconds, a 96 ms median paired slowdown and 2/4 faster pairs, although allocations fall from 464 to 352 MB. These results do not establish a general small-collection latency improvement.

## Profiles and correctness

Separate wcprof captures of the final code contain no dropped events or unfinished operations. Search-result item reads fall from 1,024 to 576, file-path reads from 512 to 64, and matched-line reads from 1,024 to 512. Both captures execute two workspace searches and make 64 cached immutable-file searches. Workload starts remain 65 and engine queries remain 1,194. The five-second CPU windows are timestamped and cover part of each diagnostic command. `dang.invoke` includes awaited engine requests and execution; its wall duration is not interpreter CPU time. Durations summed across concurrent operations are not the command critical path.

Four targeted checks pass: owned-file discovery, module discovery, skipping non-modules, and test collections. They cover byte order, Go-ignored files, nested module ownership, working-directory lookup, Unicode test names, selected failures, and host-overlay addition/replacement. The declared minimum engine, beta.15, already pins Dang v2.1.4 and supplies the Map methods used here. That compatibility assertion is checked from its source tag, rather than through a second engine runtime.

The original final expanded listing of every Go test on clean `dagger/dagger` reaches the 90-second diagnostic limit. Package discovery completes, but test expansion remains expensive. The engine stays running without an OOM. Its complete trace includes subsequent cancellation cleanup, explicitly separated from the bounded command. This is not a reproduction or a fix of the reported engine crash. A [subsequent complete-command investigation](NATIVE_GO_FULL_LISTING.md) lets the listing finish: 133.59 seconds with profiling, and one successful 101.02-second command with profiling disabled and the selected performance settings enabled. It identifies repeated module evaluation and allocation as further costs; the additional filenames-only marker experiment remains unselected.

A delayed correctness run also caught containerd garbage collection blocking metadata updates. A goroutine dump and separate five-second CPU capture are saved. It is a follow-up bottleneck, not a fix included in this module branch.

## Reproduction and limits

The large-repository commands are `dagger api call go modules path` and `dagger api call gomod at --path=. own-files --glob=*.go`, with the respective local module installed in the temporary workspace configuration. Test collections use `dagger check go:packages/tests/test`; the workspace control calls `go module --path=. test`. The native control is Go 1.26.6 with eight build workers. The fixtures contain independent packages, not shared-dependency graphs.

The engine, compiler caches and toolchains are warm; the CLI process and source edit are fresh on every arm. Telemetry and ordinary GC stay enabled. CPU profiling and wcprof are disabled for timings. The diagnostic engine is `08a1f13ae88c61f3dadea8d834132d71a52d77ccf3a7d91f91ad760ef4702197`, based on `19eda924854e7f22582f3a7430272aa729cbeb5f` plus 65 recorded overlays. The earlier selected getter/index changes are present on both sides. Interface-field snapshots, directory-copy and span-fanout experiments remain disabled. This is not an unmodified upstream-engine comparison.

[The evidence archive](experiments/go-discovery-followup/) includes final and intermediate cohorts, source hashes, all observations and warmups, profiles, correctness logs, configuration restoration, and harness limitations. [The engine experiment archive](experiments/interface-field-snapshots/) records the exact overlays and build identity; its dependency context is shared with the earlier engine archive. Source snapshots live under `testdata` so Go does not discover them as new packages. The branch is pushed for review; no upstream PR is open.
