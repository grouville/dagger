# Encode a routed span once

Preparing shared span rows before the destination writers start does not establish a complete-command improvement: the latest Go comparison measures **37.38 → 43.35 seconds median**, faster in **one of four pairs**. Both slow candidate runs overlap cache pruning; the two remaining pairs disagree. The refinement stays disabled.

An earlier version shares rows lazily with `sync.OnceValues`. Its **39.49 → 35.87 seconds** comparison improves only two of four pairs and also stays disabled. That version uses less CPU and allocation in all four pairs: separate column medians are **30.01 → 28.05 GB allocated** and **198.13 → 177.30 CPU-seconds**. These are cumulative allocation and concurrent CPU totals, not resident memory or elapsed-time savings.

## Lazy sharing: complete listing

`dagger check --module go --check test --list --all` uses source `ff0b029a`, Go module `7568cd0`, CLI `e7ba08d0` and controlled engine `75824d8c`. Every command starts a fresh CLI and receives a fresh source comment on the same warm engine and volume. Both arms retain the selected dimension-key projection. Both search projection switches remain disabled. Telemetry and ordinary GC stay enabled; profiling and diagnostic counters are off during timing. The local telemetry receiver does not model production Cloud latency. Cold startup is unmeasured.

| Pair | Original encoding | Shared encoding |
| --- | ---: | ---: |
| 1, candidate first | 36.94 s | 38.46 s |
| 2, control first | 35.76 s | 38.12 s |
| 3, candidate first | 47.47 s | 33.63 s |
| 4, control first | 42.03 s | 33.59 s |

All ten commands return the expected ordered rows and exit successfully through cleanup. An excluded initialization pair adds a real test and finds 4,399 rows; measured pairs remove it and find 4,398. Median paired saving is 3.46 seconds, with two regressions retained.

The third control's class-slot count falls **853,554 → 690,551**. Its 13.84-second gap cannot be attributed entirely to span sharing. The first candidate has 3.38% host I/O pressure versus 0.17% for its control. The second candidate regresses by 2.36 seconds under low I/O pressure without a compaction. Measured host CPU pressure reaches 25.6%. These observations are why the favorable column median is insufficient to select the change.

The first attempted cohort completes its control initialization in 38.78 seconds, then fails the existing 120-second idle-admission limit before starting a candidate. A subsequent observation finds zero sessions and active requests, negligible engine CPU and 27.46% host I/O pressure. That terminal attempt is retained. A new cohort begins only after three consecutive samples meet the unchanged idle criteria. No cache reset or forced collection is used.

## Repeated work and the prototype

The session exporter routes a span to its client and ancestors. Each destination currently serializes that same snapshot into the same stored fields. The prototype shares those encoded fields within one export. Every destination still receives its row and assigns its own row ID. Blob slices are immutable after append under the existing store contract; each destination receives a separate row value.

The first version uses a per-span `sync.OnceValues` so encoding stays inside the existing destination recovery boundary. It retains routing, payload delivery settlement, retry behavior, storage format, cache keys and collection granularity. Every new export gets fresh wrappers, so later snapshots of the same span are not reused accidentally.

The real mechanism capture records **150,548 source snapshots, 150,548 encodings and 228,037 destination writes**: 77,489 repeated encodings are avoided relative to encoding each destination independently. All destination writes are accounted for. The complete listing returns the correct rows and exits successfully in 47.94 seconds with profiling enabled. Its 397,873 wcprof events have none dropped or open. That single diagnostic is not a latency comparison.

## Components and refinement

Four alternating fresh-process pairs use the actual session exporter, including route resolution and store append. Destination stores stay open, as a live client runtime keeps them. The original closed-store cohort is also retained: repeatedly reopening and replaying history obscures the encoding cost and supports no latency claim.

| Destinations / spans per batch | Original | Shared with `OnceValues` | Faster pairs |
| --- | ---: | ---: | ---: |
| 1 / 1 | 50.06 µs | 53.40 µs | 1/4 |
| 1 / 128 | 3.095 ms | 3.160 ms | 1/4 |
| 3 / 1 | 105.42 µs | 114.96 µs | 1/4 |
| 3 / 128 | 4.741 ms | 4.432 ms | 4/4 |

The bulk three-destination case allocates **4.60 → 2.79 MB** and makes **87,897 → 41,832 allocations** per batch. Those savings do not establish faster listing; small batches regress.

A separate refinement prepares shared rows before launching the destination writers, eliminating per-span synchronization. A decoder panic is captured and replayed inside each affected destination's existing recovery boundary, retaining the original stack in a diagnostic log. Healthy, unrelated routes in the same batch still commit.

| Destinations / spans per batch | Original | Prepared shared rows | Faster pairs |
| --- | ---: | ---: | ---: |
| 1 / 1 | 50.12 µs | 60.04 µs | 2/4 |
| 1 / 128 | 3.067 ms | 3.064 ms | 1/4 |
| 3 / 1 | 103.66 µs | 90.25 µs | 3/4 |
| 3 / 128 | 4.780 ms | 3.918 ms | 4/4 |

The refined bulk case allocates **4.60 → 2.78 MB**, lower in all four pairs. Single-destination results remain mixed; the favorable bulk result is not a general speedup. The refinement introduces no per-span lock or global cache.

## Prepared rows: complete listing

The refinement is built and deployed on the same retained volume. The protocol, source, module, CLI, telemetry, GC and other feature switches match the lazy-sharing study. Every command again starts a fresh CLI and receives a fresh source edit. Profiling and diagnostic counters remain off during the timing cohort.

| Pair | Original encoding | Prepared shared rows |
| --- | ---: | ---: |
| 1, candidate first | 41.81 s | 49.25 s |
| 2, control first | 35.71 s | 61.58 s |
| 3, candidate first | 38.69 s | 36.86 s |
| 4, control first | 36.07 s | 37.46 s |
| Median | **37.38 s** | **43.35 s** |

All ten commands return the correct ordered rows and exit successfully through cleanup. The excluded initialization pair takes 49.02 → 37.14 seconds and finds 4,399 rows; all measured commands find 4,398. Median paired saving is **−4.41 seconds**. Engine CPU medians are **188.65 → 197.16 CPU-seconds**, and cumulative allocations are **29.18 → 30.00 GB**.

The first candidate's class slots fall **730,038 → 713,679**, and the second's fall **703,907 → 549,186**. These maintenance overlaps prevent attributing their full regressions to encoding. No class-table reduction occurs in the last two pairs: the candidate saves 1.84 seconds in one and loses 1.39 seconds in the other. Neither removing those observations nor keeping only quiet pairs would justify selecting the prototype. Maximum measured host I/O pressure is 0.32%; CPU pressure reaches 27.3%. Ordinary maintenance remains part of the observed command cost.

The separate diagnostic returns the correct rows and exits 0 in **40.62 seconds**, with **397,871 wcprof events**, none lost or open. It records **150,859 source snapshots and encodings**, accounting for all **228,444 destination writes**. The 77,585 avoided encodings confirm the mechanism, not an elapsed-time gain. Its main query takes 36.81 seconds; 27.45 seconds are attributed to API requests including backend processing and waits, not transport alone. The CPU capture contains substantial allocation, garbage collection and telemetry conversion work. Its windows extend beyond command completion, so CPU totals and critical-path durations must not be added.

## Validation and retained state

The complexity regression fails on the original path: one snapshot is encoded four times for four destinations. The candidate passes. Stored fields are compared with the original exporter, destination row IDs remain independent, separate updates remain separate, and later exports observe new state. Concurrent export, malformed input, routing, retry, stream and Cloud-publishing checks pass under the race detector for both variants. The refinement also verifies that one malformed route does not discard an unrelated healthy route.

All six retained Rust histories reuse every compilation action before each replacement, on their first candidate-enabled calls afterward and after each completed cohort: **130/130, 1,026/1,026 and 6/6**, twice each. The replaced engines exit gracefully in **205.62 seconds** for lazy sharing and **211.62 seconds** for prepared rows, retaining the same volume. Engine replacement is setup, separate from measured command cleanup. The primary Rust timing manifest is unchanged.

Both variants are disabled after measurement. Neither is a standalone-ready upstream proposal, and no PR is opened. This telemetry study adds no proposal. The subsequent [workspace-search regression](NATIVE_WORKSPACE_SEARCH_OVERLAY_PATHS.md) brings the review queue to seventeen Dagger descriptions and one Go-module description.

[Lazy-sharing evidence](experiments/span-row-sharing/) includes exact overlays and copied sources, failed admission and closed-store attempts, component cohorts, race checks, native-cache histories, outputs, profiles and final selection. [Prepared-row evidence](experiments/span-row-sharing-eager/) includes its source, expected control failure, races, failure-isolation check, four component pairs, full-command cohort, profiles and final selection.
