# Reuse span resource encodings within an export batch

Complete Go listing does **not** establish a latency improvement: medians are **45.47 → 46.38 seconds**. Three of four pairs improve slightly, but one regresses by 3.26 seconds. Every command returns the same 4,398 rows and exits successfully. The experiment remains disabled; the selected listing result stays [46.72 seconds](NATIVE_GO_WIDE_TRACE_INDEX.md).

| Pair | Original exporter | Resource reuse |
| --- | ---: | ---: |
| 1, reverse order | 43.38 s | 42.64 s |
| 2, forward order | 47.56 s | 46.77 s |
| 3, reverse order | 43.12 s | 46.38 s |
| 4, forward order | 47.81 s | 46.38 s |

The median paired saving is 0.76 seconds, despite the slower candidate column median. Report both rather than selecting the favorable statistic. Engine CPU medians are 233.95 → 224.94 CPU-seconds; cumulative allocation is 36.78 → 35.65 GB. These reductions do not demonstrate faster listing.

Both arms use the same engine, CLI and Go module, with a fresh CLI and source comment on a warm engine. Telemetry, normal GC and session cleanup remain enabled. Profiling and counters are off in measured pairs. The first candidate has 11.7% host I/O pressure versus 2.0% for its control; later pairs remain below 0.3%. The third-pair regression occurs under low I/O pressure and is retained. Host CPU pressure is 22.0–26.0%.

An excluded initialization pair adds a real test, returns exactly 4,399 rows and succeeds in 47.68 → 54.70 seconds. Its diagnostic counter records 292,385 resource encodings for 292,385 original span rows, versus 54,680 encodings for 293,072 candidate rows. Measured pairs remove that test and disable recording.

## Small, isolated engine change

`clientSpans.ExportSpans` serializes each span's resource separately. The candidate reuses the encoded bytes for the same immutable resource pointer within one export call. The map ends with that batch. It adds no lock, shared cache, dependency, persistent format or telemetry suppression, and retains the existing malformed-resource behavior. Both the experimental engine and recorded upstream base `ff0b029a4` have the identical original exporter.

Tests compare stored resources against the original protobuf encoder across repeated, interleaved, nil and malformed resources and across batches. Concurrent exports retain all rows. These tests pass against the original and candidate. Candidate race checks and existing store/Cloud routing and stream-framing checks pass.

Four sequential component runs in alternating order measure the real exporter, including store append. For 128 spans sharing a resource, median time is 768 → 256 µs and allocations fall from 7,770 → 1,975. With 128 distinct resources, time increases 578 → 592 µs and allocated bytes increase about 2.8%; a one-span batch is essentially unchanged. The component result is not a complete-command speedup.

The engine replacement exits gracefully, preserves its volume and retains all six Rust compiler histories: 130/130, 1,026/1,026 and 6/6 cached actions in each history. The replacement itself is setup, excluded from listing timings. The candidate switch is off after measurement.

[The archive](experiments/span-resource-batches/) preserves the pure patch, compatibility tests, component runs, every complete-command attempt, controlled engine sources and cache-retention checks. No PR is opened. The [subsequent CLI profile](NATIVE_GO_CLI_PROFILE.md) follows the remaining command cost.
