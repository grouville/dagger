# Field sorting improves locally; complete commands remain mixed

Both Protobuf experiments remain disabled. Small-message fast paths and a typed sorter reduce component time and allocations, but two complete-command cohorts per variant do not establish a consistent Rust-command speedup. The selected engine is restored, all six native histories remain reusable, and the upstream batch stays at eight proposals.

## Correct the size of the opportunity

The [earlier allocation profile](NATIVE_LISTING_ALLOCATIONS.md) put `RangeFields` on 17.6% of sampled allocation stacks. That cumulative frame includes the visitor's encoding work. Source-line analysis attributes **93,850,996 bytes**, about **3.9% of the broader capture**, to `sort.Slice` itself. Treating the cumulative percentage as removable sorting overhead overstates the opportunity.

The installed Protobuf v1.36.11 implementation matches the [current upstream source](https://github.com/protocolbuffers/protobuf-go/blob/master/internal/order/range.go), fetched directly during this study. Its ordered field traversal collects fields, uses reflective sorting, then calls the visitor. Map sorting is a separate path and remains unchanged in both experiments.

## Component results

The first variant skips sorting zero/one-field messages and compares two fields directly. The second also uses a private `sort.Interface` implementation for larger messages. It keeps the existing comparator, scratch-buffer pool, ownership and traversal behavior. The plain candidate has no diagnostic switch, new cache or lock.

Six balanced fresh-process triples compare the original implementation, small-field fast paths and the typed sorter:

| Fields | Original | Small-field fast paths | Typed sorter |
| --- | ---: | ---: | ---: |
| 1 | 153 ns | 107 ns | 107 ns |
| 2 | 267 ns | 130 ns | 134 ns |
| 8 | 1.14 µs | 1.13 µs | 0.67 µs |
| 32 | 2.66 µs | 2.57 µs | 1.85 µs |
| 128 | 4.21 µs | 4.19 µs | 3.35 µs |

For two fields, allocated bytes decrease **184 → 64**, with **6 → 3 allocations**. For larger messages the typed sorter decreases **184 → 96 bytes**, with **6 → 4 allocations**. The real client-database encoding fixture improves **21.37 → 18.96 µs**, **13,909 → 12,346 bytes**, and **170 → 125 allocations**. That fixture mostly exercises small messages, so it gains little from the larger-message sorter.

A separate six-pair comparison tests the plain small-message production patch without the diagnostic branch. One/two-field cases improve; 8/128-field controls stay close, while the 32-field median is about 4% slower. The later triple comparison reverses that 32-field timing difference. All raw observations and pressure measurements remain available; neither screen establishes a general larger-message latency penalty from the small-field branch.

Tests and benchmarks run with Go 1.26.6, linux/amd64, `GOMAXPROCS=8`, and 150 ms per benchmark case. The dependency's declared minimum stays Go 1.23; the local benchmark uses `B.N`. This is not a test run on the Go 1.23 compiler.

## Complete edited commands

Each variant has two independent-order eight-pair cohorts on the same physical sources and native history. Every command edits a used source value. Engine/compiler caches are warm, CLI processes are fresh, telemetry is enabled, and snapshot collection and Go GC remain ordinary. The Rust module stays `da1ae47`, with Rust 1.77.2 and incremental Cargo controls.

The table gives the median of paired differences across both cohorts; positive values mean the candidate is faster. It does not subtract separately computed column medians.

| Command | Small-field saving | Faster pairs | Typed-sorter saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 1,026-crate collection check | 68 ms | 11/16 | 33 ms | 9/16 |
| 130-crate direct check | −11 ms | 6/16 | −10 ms | 7/16 |
| Small collection tests | 16 ms | 8/16 | 11 ms | 9/16 |
| 1,026-package listing | 97 ms | 9/16 | 4 ms | 8/16 |

The small-field collection-check saving falls from **95 ms in the first cohort to 10 ms in confirmation**. Its direct checks are slower in both cohorts. The typed listing saves **11 ms initially** and **loses 10 ms in confirmation**. This is insufficient evidence for selecting either variant as a complete-command improvement.

Listing allocation is more consistent: the small-field variant saves **66.5 MB per pair**, lower in **13/16 pairs**; the typed variant saves **79.1 MB**, lower in **14/16 pairs**. These are useful allocation reductions, but they are much smaller than the original cumulative profile percentage suggested. The typed variant's extra larger-message benefit is correspondingly small in this workload.

Go-GC cadence differs between some arms, and pressure or background collection can rise after admission. Every admitted observation is retained. Per-cohort medians, exact source values, CPU/allocation counters, pressure and collection overlaps are in the archive. Diagnostic CPU/wcprof captures are separate from timing cohorts and have no dropped events or open operations. These generated path-dependency workspaces do not establish registry, build-script or procedural-macro support.

## A separate attribute-list screen

After the sorting results, a Dagger-only prototype encodes a complete attribute list with one existing Protobuf repeated-field wrapper and returns its JSON array. The current readers accept the resulting whitespace and values; no library fork is needed. Compatibility and full client-database race tests pass, including nil elements, Unicode, invalid UTF-8, nested values and attribute scanning.

The six-pair component screen rejects it: **20.86 → 21.64 µs**, with **170 → 173 allocations**, despite **13,907 → 13,258 bytes**. The existing append-based encoder already reuses its output buffer. Adding the wrapper does not provide the expected saving, and the prototype is never installed in the engine.

## Correctness and final state

Both field-sort variants pass the affected Protobuf order, JSON, text and core package race suites, plus Dagger's full client-database race suite. Differential tests check field order, field/value association, early stopping, nil comparators, exact JSON bytes, errors and deterministic wire encoding. The candidate retains the existing pool and introduces no production lock or shared mutable state.

Each engine variant also passes strict full reuse in all six native histories: 130/130, 1,026/1,026 and 6/6 actions in both histories. Preparation first compiles any final source edit left by a Cargo control or listing. Those unchanged checks are correctness evidence only.

The original selected engine `f73ec4d9…` is restored through a clean preserved-volume restart. Temporary controls and profiling are off, direct dimension-key getters remain on, and no sessions are active. No new PR or dependency fork is created. These library changes may be useful independently, but they do not close the complete Rust-command performance gap.

[Archived evidence](experiments/protobuf-field-sorting/) contains both complete-command studies, component controls, reference/encoding tests, full race logs, source mirrors and hashes, CPU/runtime/wcprof captures, the rejected list encoder and the final engine state. Initial generator mistakes and the GitHub metadata API rate-limit response are retained; direct raw-source verification succeeded. Binaries, volumes and target directories are excluded.
