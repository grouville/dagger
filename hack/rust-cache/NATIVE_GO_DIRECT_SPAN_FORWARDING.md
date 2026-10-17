# Direct span forwarding does not establish faster Go listing

The existing direct telemetry converter remains **disabled**. Four alternating complete-command pairs measure **41.12 → 40.70 seconds median**, with only **2/4 pairs faster**. The last candidate takes 49.80 seconds. All ten commands, including initialization, return the correct ordered rows and exit successfully through cleanup. The previously selected 39.20-second result remains the last validated improvement; this cohort adds no reliable speedup.

| Pair | Original forwarding | Direct forwarding |
| --- | ---: | ---: |
| 1, candidate first | 41.08 s | 38.78 s |
| 2, control first | 43.67 s | 39.03 s |
| 3, candidate first | 41.16 s | 42.37 s |
| 4, control first | 40.10 s | 49.80 s |

Median paired saving is 547 ms. Allocation falls by 969 MB at the median paired difference, lower in three pairs, but engine CPU rises by 2.15 CPU-seconds at the median paired difference. Two CPU comparisons improve and two regress. Separate column medians are 32.25 → 31.37 GB allocated and 214.51 → 215.19 engine CPU-seconds. These observations do not justify enabling the converter or repeating the cohort until it looks favorable.

## Why this experiment

The selected Go profile spends 17.10 cumulative CPU-seconds converting SDK spans back to Protobuf. The [older direct-forwarding experiment](NATIVE_DIRECT_SPAN_FORWARDING.md) had mixed Rust results. Its much larger Go caller provided a new workload to test, without changing the production implementation or replacing the engine.

The converter reuses decoded Protobuf attributes where the SDK round trip preserves them, retaining the original conversion for unsupported values. This removes an intermediate representation; every telemetry record is still forwarded. The helper and runtime selector are byte-identical to the historical measured source. No lock, dependency, cache identity or persistence format changes.

Both arms use engine `9123a6a5`, CLI `e7ba08d0`, Go module `7568cd0` and source `ff0b029a`. Each command starts a fresh CLI and edits a source comment on the same warm engine. Telemetry and ordinary GC remain enabled; profiling is off during timing. Both arms keep the selected scalar getters, configuration declarations, builtin receivers, usage sampling, span index, array decoder and batch metadata. Only forwarding differs. The excluded initialization pair adds a real test and correctly returns 4,399 rows; measured pairs remove it and return 4,398. Timings use the same local telemetry receiver as previous cohorts; they do not measure production Cloud network latency.

## Maintenance and remaining work

The first seven measured commands each add 41,610 class slots while net result and term counts grow much less. During the final candidate command, class slots fall from **1,396,992 to 638,617**. This coincides with its slower time and increased allocation, but the timing cohort has no profiler to attribute that delay. The command stays included. Measured host I/O pressure stays below 1.1%; CPU pressure reaches 27.3%.

A separate completed direct-forwarding diagnostic takes 46.15 seconds, returns the correct rows, and records **509,131 wcprof events with zero dropped and none open**. Its main query spends **31.67 seconds inside synchronous module API calls**; artifact metadata occupies roughly another **9.5 seconds**. The API intervals include backend work and waiting, not just interpreter execution or network time.

Ten completed CPU windows contain 214.98 sampled CPU-seconds over 50.06 seconds, including the end of the final window after command exit. The direct converter is active and accounts for 15.54 cumulative CPU-seconds. JSON marshaling still accounts for 24.00 and unmarshaling 17.93. These frames overlap and are not additive savings or a controlled CPU comparison. Removing the SDK round trip leaves substantial encoding, decoding and collection materialization work.

The subsequent maintenance experiment compares hash-based class remapping with an array and a compact bit index. It keeps the graph lock and collection policy unchanged. Component measurements are required before attributing any full-command benefit to that separate prototype.

## Correctness and state

The current client database suite passes under the race detector with both the default decoder and the decoder/batch settings used in timing. Existing differential tests compare complete exported Protobuf messages across scalar and array types, malformed values, flags, links, events, grouping and output ownership.

All six retained native histories reuse every compiler action in both modes before timing and again with the candidate after timing and profiling: **130/130, 1,026/1,026 and 6/6**, twice each. These are correctness checks, not unchanged-build performance results. The forwarding switch and temporary telemetry modes are restored afterward. The selected engine binary and primary Rust timing manifest remain unchanged. No new upstream proposal or PR is prepared.

[Evidence](experiments/go-direct-span-forwarding/) retains every admitted command, validation, source identity, maintenance observation and the completed diagnostic.
