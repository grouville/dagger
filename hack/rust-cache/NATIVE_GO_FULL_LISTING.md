Latest filesync follow-up: [walk literal includes directly](NATIVE_FILESYNC_LITERAL_WALKS.md) improves complete listing **55.81 → 52.03 s** in two balanced pairs. CLI CPU falls **39.50 → 26.81 CPU-seconds**. Metadata, ordering and real test additions/removals are verified. A diagnostic reduces visited entries **5.58 million → 237,287**; the populated development host amplifies this cost. This is a separate comparison and must not be added to earlier gains.

Latest CLI follow-up: [prune host glob walks by their literal directory prefix](NATIVE_HOST_GLOB_PREFIX.md) improves complete listing **58.10 → 53.76 s** in two balanced pairs, with identical 4,398 rows and successful exits. CLI CPU falls **75.96 → 39.45 CPU-seconds**. This is a separate cohort with identical current-main-based CLIs; its gain must not be added to earlier measurements. A more complicated traversal bound shows no additional complete-command benefit and remains unselected.

Latest module follow-up: [retain discovered module ownership](NATIVE_GO_PACKAGE_MODULE_OWNERSHIP.md) improves complete listing **68.37 → 56.81 s** in two balanced pairs, with identical 4,398 rows and successful exits. SDK invocations fall **1,762 → 963**. Adding/removing a real test produces exactly one added/removed row. Full listing remains too slow.

Latest follow-up: [shared restored cache postings](NATIVE_SHARED_RESTORED_POSTINGS.md) removes a quadratic startup index and greatly reduces memory. Two full listings still take 66.42 and 65.86 s, exit successfully and return the same 4,398 rows. The remaining discovery latency is unresolved.

# Full Go test listing on dagger/dagger

The latest direct comparison improves median listing time **88.65 → 67.11 seconds** with two small Go-module changes: ordered parallel module validation and per-module package discovery. Every arm starts a fresh CLI and source edit on a warm experimental engine, returns identical 4,398 rows and exits successfully. Total engine CPU increases about 3.4% and allocation about 1%; listing still takes over a minute. Both source identities completed their initial full listing before this confirmation. [Results, source and next engine bottleneck](NATIVE_GO_PARALLEL_DISCOVERY.md); [prepared PR description](PR_GO_PARALLEL_DISCOVERY.md). Both commits are pushed to the grouville/go fork; no PR is opened.

The older diagnostics below retain their original configurations and engine histories. Their timings must not be added to the latest gain.

The full listing is slow even after the collection index and the Go discovery changes. A completed diagnostic takes 133.59 seconds and lists 4,398 test checks. An unprofiled fresh-edit command with the selected performance settings enabled takes 101.02 seconds. These are observations from different diagnostic configurations, not an estimate of profiler overhead.

The source fixture is a clean `dagger/dagger` checkout at `ff0b029a4d270a651b9a8c7286babc79089066e4`. The module is `grouville/go` at `b5dd9434a52972787171a016a8aa9d8910c17c38`. The engine is the existing diagnostic engine `08a1f13ae88c61f3dadea8d834132d71a52d77ccf3a7d91f91ad760ef4702197`, with the earlier selected collection lookup changes present. This is not an unmodified upstream-engine measurement.

## Where the time goes

The completed wcprof capture separates the two discovery phases:

| Phase | Time | Work |
| --- | ---: | --- |
| Discover packages | 52.89 s | 80 modules; validation, file ownership, package markers |
| Expand package test collections | About 56 s | 800 `GoPackage.tests` evaluations |
| Result handling and command shutdown | Remaining command time | Collect and format 4,398 rows; close the session |

The second phase begins after the first. The durations of its concurrent child calls must not be added together. `dang.invoke` includes awaited API requests, so its duration is not a measure of interpreter CPU.

Across the command, wcprof records 800 `Gomod.module` executions, 1,762 Dang evaluations and 8,642 engine queries. Resolving a package's module starts another Dang invocation, even though package discovery already established which module owns it. Each invocation prepares schema and language state before performing its work. The sampled heap reaches 16.49 GB and cumulative engine allocation rises by 59.94 GB. The command starts no container workloads for compilation or test execution.

A ten-second CPU window during package discovery spends 37.6% of sampled CPU in Go's background garbage collector. Another diagnostic, with allocation profiling, attributes about 11.8 GB of sampled allocations to preparing and evaluating Dang module source. Its total sampled allocation is about 61 GB; sampling and the recording interval differ from the memstats counter. These are cumulative allocation volumes, not resident-memory requirements.

Collection expansion starts one goroutine for every parent receiver, without a concurrency limit. With 800 packages, many interpreter environments can remain live together while waiting for API work. The same fan-out exists in both recorded upstream source refs, `ff0b029a` and the diagnostic engine's base `19eda924`.

The earlier collection index accelerates schema-field ancestry lookup. It does not eliminate per-package evaluation, repeated module resolution or individual result queries. Source searching itself is only one part of the work: the package-discovery phase executes 81 `Workspace.search` calls totaling about one second, before accounting for result-field reads and processing.

## Why listing can use about 24 GB

The later unprofiled concurrency experiment observes up to 23.86 GB of engine `HeapAlloc`. This is a sampled heap size, including allocated objects that the garbage collector has not reclaimed yet. It is neither a measurement of live objects after collection nor the size of the test sources, compiled artifacts or disk cache. The persistent engine already has a heap before each command; the entire peak cannot be attributed to that command alone.

In one successful unbounded attempt, the command creates 669 million objects and allocates 53.55 GB cumulatively. Its first heap sample is 5.20 GB and its peak is 23.00 GB. Creating fresh interpreter types, environments and API values across hundreds of concurrent package evaluations produces both allocation volume and overlapping lifetimes. The earlier allocation profile identifies these paths, but does not establish their individual shares of peak live memory or prove that every transient allocation was released.

Two paired orders compare unbounded expansion with a per-parent limit of 32 on the same engine. Every attempt returns identical 4,398 rows:

| Order | Unbounded | Limit 32 | Sampled peak heap, unbounded / limited |
| --- | ---: | ---: | ---: |
| First | 102.84 s, success | 101.68 s, shutdown timeout | 23.00 / 12.16 GB |
| Reverse | 103.02 s, success | 97.80 s, success | 21.72 / 12.52 GB |

The limit clearly reduces peak heap, by about 45% across these attempts. Its latency improvement is modest and one candidate command fails during cleanup, so this is not a validated latency win. A pilot's larger speedup did not repeat. Smaller edited Rust and Go collection controls also give no basis for selecting a blanket limit. The experiment remains disabled: reducing concurrent work does not remove the repeated work that makes listing slow. The [concurrency experiment archive](experiments/go-collection-expansion-limit/) preserves the engine identity, source, focused race tests, complete attempts, memory samples and smaller-workload controls, including failed attempts.

## Filenames-only marker experiment

The experiment asks separate filenames-only searches for `package main`, ignore build tags and generation commands. The previous implementation reads all matching lines, then filters those results once for each marker kind. Existing checks pass for test collections, binaries, generation globs and package selection, including host overlays and nested modules.

Two before/after orders returned identical rows in every attempt:

| Order | Module | Full command | Exit |
| --- | --- | ---: | --- |
| First | Before | 101.02 s | Success |
| First | Filenames-only | 100.20 s | Success |
| Reverse | Filenames-only | 111.41 s | Success |
| Reverse | Before | 100.61 s | Shutdown timeout after listing |

The successful first pair saves only 0.83 seconds. The reverse comparison is not a successful pair because its control fails during cleanup. Allocations across all attempts are about 53.12 → 52.32 GB, but that small reduction does not establish a useful full-command latency improvement. The module change remains an unselected local experiment; no production change or PR is proposed from it.

An earlier unprofiled diagnostic also produced the listing but failed during session cleanup with a ten-second shutdown timeout. Both failed attempts are retained and excluded from successful timing claims. Neither completed profiled diagnostic reproduces an engine OOM or crash.

## Next experiments

Batching each package's immutable file imports and test-name searches passes the four focused module checks, but gives no successful complete-command improvement. The two candidate attempts take 115.97 and 167.83 seconds and both fail during cleanup. Controls take 107.50 seconds (success) and 117.68 seconds (cleanup failure). All attempts return identical rows. The reverse candidate's package discovery is unusually long, so its extra command time cannot all be attributed to test-file searching. Allocations do not establish a memory gain either. The [unselected experiment and its complete attempts](experiments/go-batch-package-test-search/) are archived; it is not a production change.

The next investigation isolates collection traversal from repeated SDK preparation using nested collections with no source discovery or test workloads. Reducing repeated package-module resolution can diagnose one part of that cost, but cannot alone deliver an order-of-magnitude improvement to collections generally. Investigate reusing prepared Dang code and schema state while keeping each invocation's clients, values and cancellation independent. A prototype that simply retained module roots was set aside because it could use stale ownership after a workspace adds or removes `go.mod`.

The full command is `dagger check --module go --check test --list --all`. Every measured arm starts a fresh CLI and adds a new Go source comment. The engine and toolchains are warm. Telemetry and ordinary garbage collection remain enabled; no engine cache is reset. The unprofiled timing cohort enables the previously selected telemetry metadata, attribute decoding and filesync seed changes on both sides, then restores their original settings. The profiled diagnostics leave those optional modes disabled.

[The evidence archive](experiments/go-full-listing/) contains the complete captures and cancellation-free command results, all timing attempts, CPU and allocation profiles, goroutine samples, source snapshots, correctness logs and reproduction drivers. Post-command GC end events are stored separately and identified when completing a capture. The [engine source archive](experiments/interface-field-snapshots/) records the exact overlays used by this engine.
