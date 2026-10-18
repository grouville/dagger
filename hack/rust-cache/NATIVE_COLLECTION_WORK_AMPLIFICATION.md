# Separate Go discovery from collection listing

The complete real-repository listing remains **35.12 seconds median** on the controlled development stack. Two diagnostic controls show why improving one small component cannot reach three seconds: returning real test names without artifact rows still takes **25.02 seconds**, while listing frozen names through ordinary nested collections takes **9.40 seconds**. These are different command and module shapes, not independent phases or an optimized implementation. Their times must not be added or subtracted to predict a gain.

The next engine experiment should reduce the graph work needed to project listing metadata. Discovery needs a separate substantial reduction in repeated module and filesystem requests. No new implementation is selected and no PR is opened.

## Complete commands

All three paths run on the same retained engine and source checkout. Every invocation starts a fresh CLI and adds a fresh Go source comment. Telemetry, native telemetry storage and ordinary GC remain enabled. Timing includes CLI exit, session cleanup and a final log flush. No profiler, reset, forced collection, cache-budget change or cleanup deferral runs in the timing cohort.

| Path | Complete-command median | Engine CPU median | Allocated bytes median |
| --- | ---: | ---: | ---: |
| Normal Go collection listing | **35.12 s** | 162.52 CPU-s | 26.03 GB |
| Concurrent real discovery, returning paths and names | **25.02 s** | 111.02 CPU-s | 19.53 GB |
| Frozen names in normal nested collections | **9.40 s** | 53.28 CPU-s | 8.96 GB |

There are four measured blocks in fixed balanced orders after one excluded initialization block: **15 successful commands**, each returning the expected 4,398 names. Every normal command matches the complete ordered baseline row text. The frozen fixture preserves package/name order; discovery output is compared as a complete multiset because its filename order differs from CLI display order.

| Measured block | Normal listing | Discovery output | Frozen-name collection |
| --- | ---: | ---: | ---: |
| 1 | 33.59 s | 27.80 s | 8.76 s |
| 2 | 33.67 s | 26.84 s | 21.07 s |
| 3 | 37.90 s | 22.58 s | 9.25 s |
| 4 | 36.58 s | 23.21 s | 9.55 s |

The 21.07-second frozen run overlaps ordinary maintenance and a shrinking class table. It remains included. Host CPU pressure reaches 39.7%, and I/O pressure 8.2%; quiet admission cannot guarantee those conditions persist. These diagnostics establish substantial work in both paths, rather than a precise saving or statistical speedup.

The engine and compiler caches are warm. Cold startup is unmeasured. The frozen fixture deliberately removes discovery and cannot execute tests; its checks raise an error if invoked. It is a diagnostic control, not a proposed Go module or an edited-build benchmark.

## What each control does

The real Go module discovers **800 package keys**, with named tests in 88 packages. The discovery probe constructs the same package receivers and lets GraphQL evaluate their existing `tests` functions concurrently, selecting normalized collection keys. It returns all packages, including the 712 without named tests. It changes no test-name search, module selection or filesystem policy.

The initial probe used Dang's sequential `map` to read names. That changed the schedule and is excluded. The corrected probe returns the receivers before GraphQL resolves their test collections. A separate fixture embeds the discovered paths and names in the same two collection dimensions. Its fixed path branches add fixture work, and its module has fewer dependencies; it is not a perfectly isolated replacement for discovery inside the real module.

Other retained setup failures include the actual schema using `ID` and `keys`, an object-list CLI call that produced no JSON output, and a missing native module manifest. The latter makes the CLI report a skipped module and exit zero; exact row verification rejects it. None enters the completed cohort.

## Wcprof locates two distinct costs

Four subsequent captures return correct rows with zero dropped events and no open operations. They are diagnostics outside the timing cohort.

| Capture | Complete command | Main query | Nested SDK requests | Function evaluations |
| --- | ---: | ---: | ---: | ---: |
| Normal listing, after removing an added test | 40.06 s | 38.17 s | 7,820 | 963 |
| Real discovery, with the added test | 25.84 s | 25.60 s | 7,820 | 963 |
| Frozen-name collections | 9.66 s | 9.12 s | **0** | 801 |
| Frozen-name collections, with CPU sampling | 14.07 s | 13.61 s | **0** | 801 |

The added test is observed as row 4,399; the following normal listing observes its removal and returns 4,398. Source files and configuration are restored after each command. The real discovery probe retains the same 7,820 nested SDK requests as normal listing. Its longest receiver-construction call takes 13.90 seconds and its longest test-collection call 11.51 seconds. Concurrent child durations are not summed.

In the frozen capture without CPU sampling, `Artifacts.items` completes in **1.84 seconds**. The main query then continues to 9.12 seconds. Its critical path attributes 2.49 seconds to field invocation, 2.19 to `Artifact.dimensionKeys`, 1.69 to result publication and 1.04 to indexed artifact reads. Those are mutually exclusive path segments, not standalone CPU measurements or predicted removable savings. In particular, indexed item labels do not mean that the full list resolver executes for every row.

This control still records 3,202 configuration stats and reads, but they occupy only about 175 and 37 milliseconds of its critical path. Request counts alone would select the wrong target. Most remaining elapsed time follows collection expansion and concerns projecting metadata through the query graph.

Each of the three measured frozen runs without class-table compaction adds **19,401 class slots**, while retained results grow by only 806 and terms by 812. Class slots are not retained results; this is not a demonstrated leak. It shows why transient query bookkeeping and the size of the graph tables need measurement alongside persistent cache entries.

The source-aligned CPU capture samples **68.87 CPU-seconds** over 15.01 seconds. Background GC accounts for 19.85 CPU-seconds and allocation assists for 8.01, approximately **40.5%** together. These disjoint GC branches overlap their ancestors and are not elapsed savings. The final sample window extends slightly past command exit. All reports merge exactly three unique original profiles; no combined profile is fed back as an input. Initial focus filters used instrumentation labels rather than Go symbols, matched no samples, and are excluded from attribution.

## Next experiment and acceptance criteria

Prototype generic bulk metadata projection while keeping the existing collection expansion and selection behavior. The goal is to avoid creating and publishing a graph result for every intermediate piece of display data. Existing direct scalar getters already help and remain enabled; this experiment must remove a larger amount of work.

First compare the ordinary metadata selection with a typed bulk projection over the same expanded artifacts. Preserve addresses, descriptions, dimension order, aliases and views, errors, cancellation, object-field dimensions, resource ownership and IDs when requested. Keep the normal path for operations that need identities or arbitrary evaluation. A new opaque JSON payload or a Go-specific bypass is not selected by this study.

Only exact equivalence and a substantial complete frozen-fixture improvement justify moving to real-repository before/after measurements. Those must use the existing unmodified Go module, fresh source and test-name edits, telemetry and full cleanup. Discovery then needs its own batched operation over tracked native inputs: the same test files and module metadata should not require thousands of independent SDK requests. Prior per-package search, transport, schema and allocation experiments remain separate; their small gains cannot be added to these medians.

Three seconds remains a target, not an established result. This study changes the next action from isolated allocation tuning to reducing discovery and metadata work at their respective boundaries.

[Evidence and replay notes](experiments/collection-work-amplification/) include the full cohort, all setup failures, probe sources, frozen fixture, exact engine/CLI identities, four wcprof captures, CPU profiles, freshness checks and restored state. The engine remains `4b03eb19…`, CLI `e7ba08d0…`, source `ff0b029a…`, and selected Go module `7568cd0…`. The selected module, Rust cache implementation and engine binary are unchanged.
