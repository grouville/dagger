# Native string sorting: a modest full-listing result

Full Go test listing takes **48.06 → 45.98 seconds median** with three private insertion-sort helpers replaced by a native string sorter. Three of four paired comparisons improve; the last regresses. All commands return the same 4,398 rows and exit successfully. The experiment remains unselected: this is a small, variable improvement and requires a new Dang API.

The latest selected comparison remains [trace indexing, 53.58 → 46.72 seconds](NATIVE_GO_WIDE_TRACE_INDEX.md). These are separate cohorts; their gains must not be added.

## Complete command

Both variants run `dagger check --module go --check test --list --all` on the same persistent engine, with a fresh CLI and Go source comment every time. Engine and tool caches are warm. Telemetry and ordinary garbage collection remain enabled; profiling and diagnostic counters are off during timing. The selected span index is on and lazy Type maps are off in both arms.

| Pair | Original helpers | Native sorter | Outcome |
| --- | ---: | ---: | --- |
| 1, reverse order | 48.65 s | 45.36 s | Both succeed |
| 2, forward order | 47.47 s | 42.53 s | Both succeed |
| 3, reverse order | 49.09 s | 46.60 s | Both succeed |
| 4, forward order | 46.45 s | 47.61 s | Both succeed; candidate slower |

The median paired saving is 2.89 seconds. Engine CPU medians are 234.39 → 230.53 CPU-seconds; cumulative allocation is 37.24 → 36.82 GB. Sampled peak heap does not improve: 12.47 → 13.07 GB. These counters do not establish a major reduction in work.

Admission checks host CPU pressure before starting. Pressure can rise during a command: measured host CPU pressure is 22.3–25.9%. Host I/O pressure is below 0.2% in the first and last pairs, about 7.2% for the second candidate, and 8.1–11.0% in the third pair. Every observation is retained, including the quiet last-pair regression.

An initial excluded pair adds a real test and lists exactly 4,399 rows: 42.75 → 55.63 seconds. The measured pairs remove it and return exactly 4,398 rows. Both module source identities therefore complete initial population before measurement; the slower candidate initialization is retained.

## What changes

The existing helpers insertion-sort immutable lists. Even their already-sorted path copies a growing list on every append. The prototype adds one typed, pure `sortStrings([String!]!)` builtin that clones its input and sorts using Go's standard library. The Go module changes only three private helper bodies. Byte order, duplicates, source ownership and collection granularity are preserved.

The builtin name is provisional. The experimental Go branch does **not** work on stock beta.15, despite retaining that minimum version for this controlled comparison. It is not a release candidate or an upstream performance-only patch. The library patch is independent of Dagger's cache and adds no dependency or mutable shared state.

Tests cover empty and singleton lists, duplicates, Unicode, combining forms, newlines, `a.go` versus `a/b.go`, unchanged input and invalid argument types. Full Dang tests and race tests pass. Expanded Go file-policy checks, invalid-module filtering, discovery, real test collections and generation-glob checks pass on the prototype engine.

Component benchmarks run both algorithms through the same interpreter with identical argument binding. At 512 already-sorted strings, the helper takes 6.49 ms versus 0.19 ms; at 512 shuffled strings it takes 333.30 ms versus 0.25 ms. Those large component ratios do not translate into an order-of-magnitude improvement for full listing.

## Follow the remaining cost

A separate diagnostic capture succeeds in 59.74 seconds with identical rows. Profiling overhead and overlapping cache maintenance make that time unsuitable for comparison with the unprofiled cohort. Wcprof records 552,842 events, none dropped and none left open.

Package discovery takes 17.33 seconds and the collection expansion finishes around 34.63 seconds into the main query. The command still makes 963 Dang invocations and 170,551 API operations. Synthetic array-element operations inherit their parent field names: the 17,592 `ArtifactDimensionKey.dimensionKeys` operations are not 17,592 executions of that field's resolver.

Continuous CPU windows cover the command and some subsequent maintenance. Their percentages must not be compared directly with the older three five-second windows. The profile identifies substantial allocation and GC work, repeated telemetry conversion and pauses while publishing collection results. In the allocation sample, `clientSpans.ExportSpans` accounts for about 4.42 GiB cumulatively; about 1.75 GiB is attributed to the resource-encoding call at line 938 of the compiled overlay. The plain checkout has different line numbers. Encoding the same immutable resource once per export batch is the next isolated engine experiment; no gain is claimed for it here.

The [evidence archive](experiments/dang-native-string-sort/) retains every timing attempt, tests, benchmark inputs, source variants, engine identity, exact overlays and profiles. No PR is opened.
