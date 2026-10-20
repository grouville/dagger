# Why the current full listing has not finished

A 90-second diagnostic of current main shows active package discovery, not a dead engine. It is deliberately interrupted and profiled, so **it is not a complete-command latency benchmark** and does not establish a speedup or total completion time.

## What the current run does

The command is `dagger check --module go --check test --list --all` on the real Dagger source, using the unchanged Go module and matched v1.0.0-beta.20 engine/CLI from the preceding comparison. A source comment and uniquely named test invalidate prior answers; both files are restored afterward. The stock main engine is used, without either configuration-cache patch. Telemetry and normal garbage collection stay enabled. Existing engines and volumes are preserved.

wcprof records 120,987 events, zero dropped events and zero open operations after interruption. The main `go:Go.packages` call is canceled after about 88.55 seconds. No `go:GoPackage.tests` execution appears: this run has not reached per-package test collection expansion. It executes `Gomod.modules`, 80 `Gomod.workspaceRootPath` calls, 69 `Gomod.at`, 69 `GomodGoMod.selected`, 59 `GomodGoMod.ownFiles` and 140 `Workspace.glob` calls. Counts describe executed operations, not number of source parses.

The engine does about 143.8 CPU-seconds of work and allocates about 41.4 GB cumulatively during the diagnostic. These allocations are not peak resident memory. Three simultaneous engine/CLI CPU windows, each 10 seconds long, sample the intervals starting at 10, 40 and 70 seconds:

| Sampled process work | CPU samples | Share of that process's sampled CPU |
| --- | ---: | ---: |
| Engine, Dang parser | 10.97 CPU-s | 27.4% |
| Engine, background garbage collection | 14.93 CPU-s | 37.3% |
| CLI, directory walking | 6.73 CPU-s | 80.2% |

The engine samples total 40.03 CPU-seconds across 30 seconds of windows; the CLI samples total 8.39 CPU-seconds over the same windows. These percentages are samples of CPU activity, not shares of end-to-end wall time. Nested profiler rows must not be added together. The allocation profile is sampled and can lag recent work; the cumulative allocation counter is the command-level allocation measure.

Goroutine snapshots at 10 and 70 seconds show `runtime.eval -> evalDangSource -> dang.RunDir -> parseDirBlocks -> ParseFile`. Current `core/sdk/dang/v2/helpers.go` invokes `RunDir` for each executed module function call. Many helpers have distinct arguments and execute despite ordinary function-result caching. Repeated loading of the Dang module therefore adds parsing, initialization and allocation work before useful helper work. The CLI is also repeatedly walking the host tree for glob requests.

## Why the earlier 45-second figure is a different setup

The older complete-command cohort is preserved in `config-content-declarations/evidence/testdata/full-command-paired/metadata.json`. It uses:

- The optimized Go module at `7568cd0e5309a716fc94f310a488978fd97ce0c3`, rather than current upstream Go `334136faaa1cd36ac26dfdc648eda907ce99c063`. Its retained `go.dang` and `gomod/main.dang` exactly match the hashes recorded in the measured cohort. That module includes parallel discovery, retained package ownership, sorting and test-name indexing changes.
- An experimental engine with module-declaration reuse enabled in both cache arms. It retains eligible prepared Dang declarations across calls, rather than repeating `RunDir` each time. The separate prepared-schema experiment is explicitly OFF in that cohort; the two features must not be conflated.
- The patched CLI from the host literal-path/glob investigation, rather than the current-main CLI.
- Older Dagger input revision `ff0b029a4d270a651b9a8c7286babc79089066e4`, API beta.15 and 4,398 test rows. The newer input is `c5456d9cbf47e432b89aba43e35211425e8e1f03`, API beta.20 and an expected 4,483 rows including the added test.

The earlier **45.51 -> 40.65 s** result is a valid isolated configuration-cache toggle *within that older optimized setup*. It is not a measurement of just the configuration cache on current main. The newer 180-second timeouts provide no completion time and cannot be treated as a 45-to-180-second regression.

This diagnostic identifies concrete repeated work consistent with the missing optimizations. **It does not attribute a measured fraction of the overall gap to any individual patch.** Doing that requires holding the repository, Go module, CLI and engine base fixed while changing one implementation. No production fix or new PR is introduced by this investigation.

Raw wcprof data, CPU/allocation profiles, stack snapshots, counts, reports, exact commands and the older-cohort identity comparison accompany this report. Profiling is disabled afterward, and all diagnostic jobs are finished.
