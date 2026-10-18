# Batch immutable Go discovery facts

Complete edited Go test listing on real `dagger/dagger` improves **25.45 → 19.21 seconds median**, faster in all four alternating pairs. The Go module batches path and selection queries and retains the owning module it already discovered. All commands return identical ordered rows and finish cleanup. Three seconds remains unachieved.

## Complete command

Both arms use the same experimental engine, CLI, retained volume and source checkout. Typed artifact metadata and generic immutable-data projection are enabled in both arms. Only the Go module changes. Every invocation starts a fresh CLI and adds a fresh Go source comment. Telemetry, ordinary GC, session cleanup and final log flushing remain included. Profiling is off during timing; no reset, forced GC or budget changes occur.

```sh
dagger check --module go --check test --list --all
```

| Measured pair | Previous module | Batched facts |
| --- | ---: | ---: |
| 1, candidate first | 24.28 s | 20.81 s |
| 2, control first | 25.50 s | 20.57 s |
| 3, candidate first | 28.05 s | 17.51 s |
| 4, control first | 25.41 s | 17.85 s |
| Median | **25.45 s** | **19.21 s** |

The median paired saving is **6.24 seconds**, approximately a 25% improvement by column medians. All eight measured commands return the same ordered 4,398 rows. An excluded initialization pair adds a real test; both arms see 4,399 rows. The measured pairs remove it. All ten commands succeed, and source and configuration are restored afterward. No observations are discarded.

Median engine CPU falls **114.74 → 93.28 CPU-seconds**, lower in three of four pairs; the first candidate uses 5.26 additional CPU-seconds. Cumulative allocation falls in every pair, with medians **18.01 → 17.13 GB**. Allocation is not peak memory. Maximum observed host CPU pressure is 21.2%, and I/O pressure is 0.15%. Ordinary cache maintenance remains enabled and all overlapping observations are retained.

The engine is warm; cold startup is unmeasured. These are matched observations on a development stack, not stock upstream. The result must not be added to gains from earlier cohorts.

## Change and correctness

The shared `gomod` library exposes two bulk operations. One returns normalized paths, path prefixes and test-selection flags for discovered modules. The other selects a list of candidate binary directories using the existing policy. It preserves ordering, duplicates, normalization and exclusions; it introduces no second selection implementation.

The Go module retains its own `GoModule` objects during package discovery. Packages reuse those owners after the existing `go.mod` layout-digest check. An execution workspace with different module boundaries still performs normal ownership lookup. Legacy construction paths keep their existing fallback. Current source contents and test names are still read from the supplied workspace.

The change is 77 added lines and 12 removed lines across three files, including tests. It adds no engine lock, dependency, host memo, TTL, opaque payload or change to native cache identity. The main risks are stale ownership and selection behavior; the retained layout guard and the existing integration checks cover both. Retaining owners also adds a scan of the discovered module list per package; it is not an indexed lookup. The measured allocation nevertheless decreases, and this is not proposed as the final graph-scaling design.

All **24 Go-module checks** and **three targeted library checks** pass. They cover workspace overlays, nested modules, retained-package rebinding after a new `go.mod`, selection, binaries, generation and toolchain settings. The library's selection check now exercises bulk results against the established policy, plus normalization, Unicode, empty lists, ordering and duplicates. Early harness mistakes and the missing Git workspace root in the isolated copy are retained with their corrections.

## What the profiles establish

Separate wcprof captures return the correct 4,398 rows, with no dropped events or unfinished operations. Nested SDK requests fall **7,820 → 4,845**, a reduction of **2,975 requests (38%)**. The two leading old shapes were 1,576 selection requests and 1,479 path-prefix requests. Most disappear; binary selection now uses bulk calls. Total recorded events fall **709,464 → 493,738**.

The candidate's diagnostic command takes 18.42 seconds. Its main query lasts 17.95 seconds: package discovery takes about 8.28 seconds and the longest package test-collection call about 9.02 seconds. These are profile observations, not additional benchmark samples.

Wcprof assigns approximately **4.19 seconds** of the critical path to waiting on session lifecycle admission, **2.44 seconds** to configuration-stat intervals, **1.28 seconds** to configuration-read intervals and **2.33 seconds** to host-directory calls. These intervals include scheduling and contention; they are not filesystem CPU or guaranteed removable savings. CPU samples still show substantial garbage-collection work. Typed metadata projection itself contributes about 49 ms on that path.

The next order-of-magnitude opportunity is shared, correct preparation of module and query state across collection expansion. There are still 800 `GoPackage.tests` executions and 800 layout-digest SDK requests; the latter hit an existing result, but still pass through query setup. Earlier parallel-admission and schema-reuse experiments have mixed results or correctness counterexamples. This profile does not justify re-enabling them unchanged or skipping fresh configuration checks.

## Review state

The module commit is [0b487434](https://github.com/grouville/go/commit/0b48743446cd6121f71141598022bc69700dbf26), on `perf/batch-discovery-facts` in the fork. Its parent is the previously selected ownership prototype `7568cd0`, rather than current upstream main. No PR is opened. The [prepared description](PR_GO_BATCHED_DISCOVERY_FACTS.md) states that boundary.

The source checkout remains `ff0b029a`, engine `1a514c53` and CLI `97f7d82d`. No engine binary or cache volume is replaced. Experimental controls return to their previous state. [Sources, checks, matched measurements and lossless captures](experiments/go-batched-discovery-facts/) preserve the evidence.
