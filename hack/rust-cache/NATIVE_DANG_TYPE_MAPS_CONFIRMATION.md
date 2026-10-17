# Scope-map allocation: less allocation, no material listing gain

Full Go test listing takes **48.83 → 48.74 seconds median** across three usable pairs. Every command returns the expected rows and exits successfully. Allocating Dang's scope maps only when needed reduces cumulative allocation by about 1 GB per listing, but does not establish a useful command-latency improvement. The candidate remains disabled.

This completes the [earlier comparison](NATIVE_DANG_TYPE_MAPS.md), which stopped during session cleanup. It uses the same tested library implementation on the current engine, with selected span indexing enabled. The controlled source matches the current binary's archived build manifest; no implementation change or engine restart was needed.

| Pair | Eager maps | Lazy maps |
| --- | ---: | ---: |
| 2, control first | 48.83 s | 49.62 s |
| 3, candidate first | 44.38 s | 42.79 s |
| 4, control first | 49.02 s | 48.74 s |

All six usable commands return identical 4,398 rows. Two pairs improve and one regresses; the median paired saving is 0.28 seconds. Median engine CPU is **235.73 → 236.95 CPU-seconds**, cumulative allocation **37.56 → 36.54 GB**, and sampled peak heap **14.38 → 13.81 GB**. A sampled heap peak is not a measurement of retained live memory. Host I/O stalls stay below 0.23% and engine I/O below 0.11%.

Each command starts a fresh CLI and edits a Go source comment on a warm engine. The module, CLI and engine are identical in both arms. Ordinary GC and telemetry stay enabled. Circular telemetry queues, resource reuse and profiling stay off; the selected span index stays on. These are complete command times, including cleanup, and are not additive to earlier gains.

The initialization pair adds a real test and returns identical 4,399 rows in 49.22 → 49.03 seconds; it is excluded as planned. An accidentally broad file search may have overlapped the first measured pair. Its exact overlap cannot be established, so the whole pair is conservatively excluded before evaluating the remaining results. That excluded pair takes 56.56 → 47.77 seconds and strongly favors the candidate; it is still excluded. Removing the added test restores the expected 4,398 rows in every measured attempt.

All ten commands succeed. The raw four-pair summary, excluded attempts, resource samples, declared exclusion and corrected three-pair analysis are retained. The observation establishes successful completion on the current stack, not a causal proof of the earlier cleanup timeout. Existing behavior and race checks remain applicable because the library implementation is unchanged.

The latest selected full-listing result remains **53.58 → 46.72 seconds** from the separate span-index comparison. The next diagnostic splits the broad `dang.invoke` interval into function evaluation, synchronous API calls, telemetry flushing and result encoding. An API-call interval includes client processing as well as backend work; it must not be treated as network delay alone.

[The evidence archive](experiments/dang-lazy-type-maps-confirmation/) contains every attempt and the corrected analysis. No PR is opened.
