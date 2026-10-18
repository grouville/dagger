# Batch Go test-name discovery through native workspace search

Complete Go collection listing improves **36.43 → 34.99 seconds median**, faster in all four measured pairs. The prototype stays isolated: cumulative allocation and CLI peak memory increase, and host overlays require the separate engine fix described below. It adds no ready Go-module proposal.

This is a Go-module change written in Dang. One native `Workspace.search` reads each package's exact selected test files together. The module restores filename order, preserves source order within each file and removes duplicate names as before. Individual package/test collections and test execution remain the same. The search remains an engine operation with tracked workspace input; compiled-result keys are preserved.

## Complete command

`dagger check --module go --check test --list --all` runs against dagger/dagger `ff0b029a`, the same CLI `e7ba08d0` and engine `00166f29`. Both arms keep every selected engine optimization and the overlay-search fix; span sharing and the two unsuccessful search-projection experiments stay disabled. The control module is `7568cd0`; the candidate's measured source is committed as `d17c973`.

Each invocation starts a fresh CLI and receives a fresh Go source comment on the same warm engine and volume. Telemetry and ordinary GC remain enabled. Profiling and diagnostic counters are off during timing. Cold startup is unmeasured; the local telemetry receiver does not model Cloud latency.

| Pair | Per-file search | Workspace search |
| --- | ---: | ---: |
| 1, candidate first | 38.48 s | 35.39 s |
| 2, control first | 35.97 s | 34.59 s |
| 3, candidate first | 36.66 s | 36.51 s |
| 4, control first | 36.20 s | 34.46 s |
| Median | **36.43 s** | **34.99 s** |

Median paired saving is **1.56 seconds**. All ten commands return the expected ordered rows and exit 0 through cleanup. The excluded initialization pair adds a real test, takes 40.95 → 37.73 seconds and finds 4,399 rows; measured pairs remove it and find 4,398. The source and configuration are restored afterward.

## Work and memory tradeoffs

| Separate column medians | Control | Candidate |
| --- | ---: | ---: |
| Engine CPU | 188.15 CPU-seconds | 182.82 CPU-seconds |
| Cumulative allocation | 29.11 GB | 29.55 GB |
| CLI maximum RSS | 653 MiB | 756 MiB |

CPU falls in three pairs, allocation rises in three, and CLI maximum RSS rises in all four. These allocation totals are not peak resident memory. Class slots grow by 24,018 per ordinary control and 25,357 per candidate; the first control grows by 24,126. No measured command shows a class-table reduction. The candidate therefore removes requests without reducing every kind of retained work.

Measured host I/O pressure reaches 5.04%, CPU pressure 27.34% and memory pressure 0.0067%. All observations remain included. The earlier [Directory-search candidate](NATIVE_GO_PACKAGE_SEARCH_RECHECK.md) is a different implementation and remains rejected; its times must not be mixed with this cohort.

## Wcprof verifies the mechanism

Separate captures run after the unprofiled cohort, with the same engine flags and fresh source edits. Both return the correct rows and exit successfully. Their 386,037 and 348,489 events have none dropped or open.

| Recorded operations | Control | Candidate |
| --- | ---: | ---: |
| Engine queries | 7,845 | 6,884 |
| API requests from Dang | 7,820 | 6,859 |
| `Workspace.file` calls | 1,129 | 80 |
| `Host.directory` calls | 1,295 | 246 |
| `File.search` calls | 1,049 | 0 |
| `Workspace.search` calls | 239 | 327 |
| `GoPackage.tests` calls | 800 | 800 |
| `Artifact.items` calls | 4,398 | 4,398 |

The candidate removes **961 queries** and **1,049 per-file import calls** without coarsening collections. Those are measured query counts; chained fields in one query must not be counted as separate requests. These captures observe 1,150 → 0 backend snapshot commits, but their warmed cache states also differ, so that count is not a general cold-import saving.

Profiled command times are 37.77 and 38.17 seconds; they establish no profiling-time speedup. The candidate's main query lasts 35.41 seconds. Wcprof attributes 27.34 seconds to API requests, including backend processing and waits, and package discovery takes 18.11 seconds. Those intervals overlap and must not be added. This remains the larger target; fewer requests alone do not explain the remaining time. The next useful checks are allocation attribution for this prototype and backend attribution within package discovery.

## Correctness, engine dependency and review

The first collection check exposes an existing engine failure: an explicit file created only in a host overlay is sent to host ripgrep before overlay results are merged. The failed check is retained under `attempt-0-overlay-source-error`. A direct GraphQL reproduction confirms it independently of the Go module.

The [standalone engine fix](NATIVE_WORKSPACE_SEARCH_OVERLAY_PATHS.md) passes a regression on current main and enables the existing collection checks. The module checks cover Unicode, filename/source order, overlays, a retained package used with edited contents, selected execution and module-boundary rebinding. All six retained Rust histories reuse every compilation action before engine replacement, on their first calls afterward and after the Go cohort: **130/130, 1,026/1,026 and 6/6**, twice each. The primary Rust timing manifest is unchanged.

[The Go prototype is pushed separately](https://github.com/grouville/go/tree/experiment/workspace-package-test-search). Its commit records the required engine fix. Released-engine compatibility and the allocation/RSS tradeoff need resolution before proposing it for merge. The selected default Go module remains `7568cd0`; the prototype is retained for follow-up. No PR is open.

[All sources, attempts, tests, timings, profiles and restored state](experiments/go-workspace-package-test-search/).
