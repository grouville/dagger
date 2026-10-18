# Native telemetry storage: lower CPU and allocation, promising listing time

The complete Go test listing measures **38.98 → 33.83 seconds median** across eight alternating pairs, about **13% faster**. Native storage wins **6/8 pairs**; two regressions of **0.13 and 0.35 seconds** remain included. Every command returns the exact ordered rows and exits successfully through cleanup.

Allocation and CPU are more consistent: both decrease in **all eight pairs**. Separate column medians are **29.76 → 25.16 GB allocated per command** and **190.32 → 150.70 engine CPU-seconds**. Allocated bytes are cumulative, not resident memory. These concurrent CPU totals are not elapsed-time savings.

**Native writing stays disabled pending confirmation and migration review.** Two slow JSON runs overlap cache compaction, later host I/O pressure rises, and cache state changes between arms. This first cohort supports further work but does not establish a reliable selected improvement. No new upstream proposal or PR is opened.

## What changes

Stored telemetry currently converts Protobuf values to JSON and back. The [earlier component screen](NATIVE_CONFIG_PREFLIGHT_PHASES.md) found substantially cheaper native encoding, but did not change the engine.

This prototype uses the existing generated Protobuf codecs for span/log attributes, span events and links, resource and scope metadata, and metrics. Every telemetry record, route, retry and ordinary flush remains. External telemetry exports retain the same OTLP messages. There is no additional dependency, global cache, pool, production mutex, telemetry suppression or deferred maintenance.

The reader audit matters: call-frame lookup, check/test discovery, archive recovery and the Cloud published-record filter inspect stored attribute bytes. They now understand both encodings. Native call-digest extraction uses the generated decoder; marker searches remain prefilters and actual readers validate values.

Each native payload identifies its format version and message kind. Readers also accept existing JSON fields. The outer telemetry store moves from **v1 to v2**, so a v1-only engine rejects incompatible new files. A valid legacy store is recovered before its header is upgraded and new records are appended. Dump remains read-only and accepts either version.

This is a storage-format migration, with corresponding review cost. An old engine cannot read v2 telemetry files. Turning the experimental writer off does **not** undo that migration: the controlled engine keeps dual-format readers and v2 support. Native compiler-cache records do not use this format.

## Complete repository listing

Command: `dagger check --module go --check test --list --all`.

Both arms use source `ff0b029a`, selected Go module `7568cd0`, CLI `e7ba08d0`, Go 1.26.6 and the same controlled engine binary, `4080ad95`. The engine and caches are warm; each command starts a fresh CLI and receives a fresh source-comment edit. Telemetry, ordinary Go GC, snapshot collection and cleanup stay enabled. Profiling is off during timing. The local telemetry receiver does not model production Cloud latency. Cold startup is unmeasured.

Both arms have the same dual-format readers and outer-store support; **only the writer codec changes**. All other unselected experiments remain off. Measured time includes CLI exit and an explicit final engine-log flush. Timing admission is benchmark setup and is not part of the Dagger command.

| Pair | JSON storage | Native storage |
| --- | ---: | ---: |
| 1, native first | 35.59 s | 35.71 s |
| 2, JSON first | 35.99 s | 33.98 s |
| 3, native first | 38.77 s | 29.49 s |
| 4, JSON first | 39.20 s | 29.90 s |
| 5, native first | 51.49 s | 32.61 s |
| 6, JSON first | 35.59 s | 35.94 s |
| 7, native first | 50.59 s | 36.54 s |
| 8, JSON first | 43.65 s | 33.67 s |
| Median | **38.98 s** | **33.83 s** |

All sixteen measured commands find **4,398 rows**, in the expected order. The excluded initialization pair adds a real test, correctly finds **4,399 rows**, and takes **37.47 → 41.26 seconds**. Initialization is excluded by the protocol, not because of its result. All eighteen commands succeed. No admitted observation is discarded or rerun to obtain a better number.

Median paired saving is **9.29 seconds**. That is a different statistic from the **5.16-second difference between column medians**; neither should be presented as the other. The large paired gaps coincide partly with maintenance and pressure differences.

JSON pair 5's class slots fall **829,970 → 652,017**, and pair 7's fall **724,071 → 667,345**. Pair 8 starts its native arm with **495,139** slots, after the JSON arm ends with **671,177**. The counters therefore do not support assigning those entire timing gaps to encoding. Native pair 6 sees about **5.0% host I/O pressure**; JSON pair 7 about **6.9%**, and JSON pair 8 about **8.3%**. These observations remain in the aggregate. Go GC and snapshot collection continue normally throughout.

CLI CPU barely changes: it remains roughly 26 CPU-seconds per invocation. The substantial reduction in engine CPU does not remove all command work. A CLI profile and an independent-order confirmation are concrete next steps; another favorable component result would not settle the end-to-end question.

## Component cost includes indexing

Four alternating fresh-process pairs compare the actual controlled codecs, with their version/type header and current readers. Each uses `GOMAXPROCS=8` and 250 ms per benchmark case.

| Component | JSON | Native | Faster pairs |
| --- | ---: | ---: | ---: |
| Encode attributes and extract the call-index digest | 21.63 µs | 11.34 µs | 4/4 |
| Decode attributes | 36.00 µs | 6.02 µs | 4/4 |
| Encode resource metadata | 4.62 µs | 1.16 µs | 4/4 |

The first case includes an added cost: native digest lookup decodes the attribute list inside the existing call-index lock, whereas the JSON index scans the encoded bytes. Encoding plus indexing is about twice as fast in this fixture, rather than the sixfold encoder-only result. Allocations fall **171 → 64**, and allocated bytes **13,926 → 8,800**. The prototype adds no lock, but the longer index-reader work still needs consideration for workloads with heavy index contention.

## Correctness and retained cache

The complete client-database race suite passes with the final candidate and with both JSON and native fixtures. Focused server race checks pass in both modes for archive recovery, Cloud forwarding, bounded outage queues, ordered retries, delivery settlement, cancellation, malformed telemetry and client-store lifetimes. The archive API race suite passes too.

New checks compare complete exported spans, logs and metrics; test empty/nil values and returned-buffer ownership; reject malformed payloads, unknown versions and mismatched types; and reopen mixed JSON/native histories. Reopening must rebuild call, check and test indexes. That regression **fails with the original index code**, which loses the native span, and passes with the candidate. Existing archive and log fixtures also run through the native writer. Test readers use the dual-format API without weakening their delivery assertions.

The first server run exposes an unchanged legacy log-reader branch and a JSON-only Cloud marker prefilter. Both are corrected before installation. Failed attempts, fixture corrections and harness failures remain archived with the final passing logs.

All **35 selected Go-module checks pass** with native writing enabled. All six retained Rust histories reuse every compiler action before replacement, on their first native-enabled calls afterward, and after the cohort: **130/130, 1,026/1,026 and 6/6**, twice each. These verify cache reuse, not edited Rust-build performance. No new Rust timing gain is claimed.

The old engine exits gracefully in **205.10 seconds**, saving its existing cache. The same container and mounts are retained. Replacement is setup, separate from measured command cleanup; it is not a controlled shutdown-performance comparison. No forced shutdown, cache reset or forced GC is used.

## Separate profile and remaining work

The post-cohort native diagnostic completes successfully in **35.18 seconds**, with the correct rows. Its **1,134,726 recorder events** have none dropped or left open. The measured main query takes **33.46 seconds**. This is one profiled run, not another timing pair.

CPU samples positively identify the native codec: **5.28 cumulative CPU-seconds** under `marshalNativeProto` and **5.76** under `unmarshalNativeProto`. This verifies the mechanism. It is not a matched before/after CPU comparison with the earlier engine.

Configuration stats and reads still occupy **9.33 seconds on the main query's critical path**; session-lifecycle waits occupy **3.33 seconds**. These configuration reads remain fresh and independent. The rejected in-progress sharing from the previous study is not installed.

The final engine is idle, with profiling off and native writing disabled. Its dual-format readers and v2 store support remain installed. Before selecting or preparing this migration for upstream, confirm the full-command gain with independent ordering and review crash/upgrade and downgrade behavior. The existing upstream review queue is unchanged.

[Evidence](experiments/telemetry-native-storage/) retains exact source overlays, before/after sources, tests and expected control failure, all benchmark observations, maintenance/pressure counters, raw compressed profiles, retained native histories and final state. Binaries are identified by hash and excluded.
