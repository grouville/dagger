# Smaller log-flush buffers: allocation saved, no listing speedup

Sizing the log SDK's flush buffer to its queued records saves about **800 MB per complete Go listing**, with lower allocation in all eight pairs. It does **not** establish faster listing: the median is **34.38 → 35.36 seconds**, faster in only three pairs. The experiment is off and no PR is proposed.

## Cause and compatibility

Dagger pins the log SDK to v0.16.0. Its `BatchProcessor.ForceFlush` allocates a record slice for the queue's full capacity on every call. At the default capacity of 2,048, even an empty queue allocates about 885 kB per flush. The saved real-listing profile attributes about 0.79 GiB directly to this function.

The prototype reads the queue length under its existing mutex and sizes that buffer accordingly. It keeps the export barrier, batching, capacity, cancellation and shutdown paths. A successful concurrent poll enqueues exports while holding the queue lock, before the preserved exporter barrier. Records emitted later need not be included in this flush. That matches the [SDK's flush contract](https://opentelemetry.io/docs/specs/otel/logs/sdk/#forceflush).

An empty queue still calls the exporter flush: exports can already be in progress. The change adds one acquisition of the existing queue mutex; it does not introduce another lock or change lock order. It changes neither record contents nor telemetry storage formats.

SDK v0.21.0 has reworked flushing, but upgrading the four pinned log modules fails to compile because it removes `log.Value`, `log.KeyValue` and their constructors, used by Dagger and `dagger/otel-go`. The intermediate v0.20.0 retains that API but still allocates the full-capacity buffer. A dependency-only upgrade does not solve this on the current source. Maintaining a legacy backport would need justification beyond the component result.

## Component result

Four alternating fresh-process pairs compare exact copies of SDK v0.16.0 with Go 1.26.6 and eight workers. Setup and shutdown are outside timing; enqueue plus synchronous flush is timed, with ordinary collection.

| Queue capacity / records per cycle | Original | Smaller buffer | Allocated bytes before → after |
| --- | ---: | ---: | ---: |
| 128 / 0 | 8.29 µs | 0.81 µs | 57,472 → 128 |
| 128 / 16 | 11.52 µs | 4.86 µs | 57,760 → 8,608 |
| 2,048 / 0 | 166.72 µs | 0.80 µs | 884,864 → 128 |
| 2,048 / 1 | 166.03 µs | 1.99 µs | 885,154 → 864 |
| 2,048 / 16 | 159.67 µs | 6.05 µs | 885,158 → 8,608 |

All six measured shapes improve in all four pairs. Both complete SDK race suites pass. Added checks cover delegated flushing of an empty queue, cancellation with an in-flight export, and exact concurrent delivery of 256 distinct records. A deliberately broken empty-queue return fails both barrier tests. Review tests also pass using the SDK's Go 1.24-compatible concurrency style. Test exporters clone retained records, and cleanup uses a fresh bounded context.

## Complete edited listing

The comparison runs `dagger check --module go --check test --list --all` on the real repository at `ff0b029a`, using the selected Go module and CLI. Each invocation starts a fresh CLI and edits a source comment on the same warm engine. Both arms use the same diagnostic binary and native telemetry codec; only flush-buffer sizing changes. Counters are off during timing. No collection, budget, cache-retention or cleanup policy changes.

| Paired result | Observation |
| --- | ---: |
| Complete command, column medians | 34.38 → 35.36 s |
| Median paired latency change | 1.02 s slower |
| Faster candidate pairs | 3/8 |
| Median paired allocation reduction | 800.06 MB; lower in 8/8 |
| Median paired engine CPU change | 1.64 CPU-seconds higher; lower in 3/8 |

Separate CPU column medians decrease, but the paired CPU differences do not establish an improvement. All sixteen measured commands return the same ordered **4,398 rows** and exit successfully through cleanup. The excluded initialization pair adds one real test and returns 4,399 rows in both arms. Its counters confirm the changed path: 966 original flushes allocate 1,978,368 record slots, versus 967 smaller-buffer flushes allocating 22,814 slots. The favorable initialization time is not a measured speedup.

All attempts remain included. Class-slot counts decrease during several commands, so automatic cache maintenance overlaps part of the cohort. Compaction recording is disabled during timing; these samples cannot assign a duration to that work. There is no filtering or repeated cohort seeking a favorable result.

## State and next work

The owned engine restarts gracefully in 261.17 seconds on its existing volume. A shutdown snapshot locates the later wait in pooled network-namespace cleanup; that is separate from listing time. All six native Rust histories hit every compiler action before restart, after restart and after the comparison: 130/130, 1,026/1,026 and 6/6 for both histories.

The running diagnostic engine is `4b03eb195a40e785efe89113572fafa8192329b8853ae3621f28aca0e57b01d7`, inheriting the previous overlays and v2/dual-format telemetry readers. Original buffer sizing, flags, source, configuration and inactive profilers are restored. Neither the earlier iterator experiment nor either rejected compaction change is installed.

[Verified evidence](experiments/log-flush-buffer/) retains the patch, SDK sources, upgrade failure, all checks, negative control, every component and command sample, restart/cache verification and restoration state. The next lead is interpreter callback setup: `callFunc` constructs a temporary type and scope for every callback, while an interpreted function derives execution state from its captured closure. That remains a source audit, with no patch or performance claim.
