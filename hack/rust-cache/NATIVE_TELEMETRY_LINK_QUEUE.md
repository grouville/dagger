# A circular telemetry queue does not improve full Go listing

Full Go test listing takes **45.98 → 46.76 seconds median**, with only one of four paired runs faster. Every command succeeds and returns the expected rows. The circular-queue experiment is disabled. The latest selected full-command result remains **53.58 → 46.72 seconds** from the separate span-index comparison.

## A real copying cost, preserved behavior

An existing full-command CPU capture leads from list-element materialization through `Cache.wait` and `EmitOTelWait` into OpenTelemetry's `recordingSpan.AddLink`. In two late-command ten-second windows, this branch accounts for 1.94 sampled CPU-seconds. Those windows overlap normal GC and briefly extend beyond the command; this is CPU attribution, not a wall-time estimate.

The pinned OpenTelemetry SDK shifts every retained element when its bounded link/event queue overflows. Dagger raises the link limit to 16,384, making each subsequent insertion copy about 1.5 MiB. The [current upstream implementation](https://github.com/open-telemetry/opentelemetry-go/blob/main/sdk/trace/evictedqueue.go) matches the pinned implementation apart from its package import comment; the standalone patch applies to the downloaded upstream file.

The candidate replaces that shift with one queue index and overwrites the oldest element. Insertion becomes constant-time; snapshots still copy the retained values in FIFO order. Limits, retained values, drop counts, one-time warnings and snapshot independence stay the same. It adds one integer per queue, with no new lock, public API, dependency, cache policy or persistence format. The existing span lock still protects queue access.

This is an OpenTelemetry SDK experiment. It does not change Dagger's object identities, list materialization or ownership checks, and it retains all existing telemetry behavior.

## Complete-command comparison

Both arms run `dagger check --module go --check test --list --all` against the same persistent engine, Go module and CLI. Every invocation starts a fresh CLI and edits a Go source comment. The engine and tool caches are warm. Telemetry, ordinary GC and the selected span index remain enabled. Resource reuse, lazy Type maps and profiling remain off.

| Pair | Original queue | Circular queue |
| --- | ---: | ---: |
| 1, candidate first | 42.38 s | 46.44 s |
| 2, control first | 47.75 s | 45.00 s |
| 3, candidate first | 44.21 s | 47.07 s |
| 4, control first | 47.76 s | 50.20 s |

All eight measured commands return identical 4,398 rows and exit zero. The candidate is 2.66 seconds slower at the median paired difference. The separate initialization pair adds a real test, returns identical 4,399 rows in 47.51 → 45.84 seconds and is excluded from these statistics. Removing that test restores the expected listing.

Median engine CPU falls **235.59 → 230.86 CPU-seconds**, while cumulative allocation rises **36.79 → 37.35 GB**. Sampled peak heap falls **13.64 → 12.64 GB**. These observations do not establish a memory improvement or a useful full-command latency gain. Host I/O stalls stay below 0.24%, engine I/O below 0.10%; host CPU stalls range from 21.6% to 24.3%. All attempts are retained.

## Component results and tradeoffs

Four sequential processes alternate original/candidate/candidate/original, with two samples per case. Medians from the pure patch:

| Operation | Before | After |
| --- | ---: | ---: |
| Public `AddLink`, full 128-link span | 141.30 ns | 31.23 ns |
| Public `AddLink`, full 16,384-link span | 120.91 µs | 31.45 ns |
| Eight-link short span, including queue allocation and snapshot | 701.95 ns | 675.35 ns |
| Snapshot, 16,384 retained links after 127 drops | 397.67 µs | 427.68 µs |

Insertion adds no allocation in either arm. Short spans retain the same allocation count and bytes. Snapshot allocation remains one copy of the retained queue; a wrapped queue needs two copy segments, and the last row shows a roughly 7.5% slowdown in that case. The large insertion gain must not be presented as the complete command's speedup.

The SDK trace package passes on the original and candidate. The candidate also passes with the race detector. Added checks cover zero, unlimited and bounded capacities; repeated wraps; retained order and drop counts; independent snapshots; span accessors and final snapshots; and concurrent updates/readback. The A/B control is tested separately: each queue captures its mode at creation, so switching between commands preserves existing spans' storage. This control and its HTTP endpoint are excluded from the standalone patch.

The owned engine exits gracefully before replacement, preserving its cache volume. All six retained Rust histories reuse every compiler action before and after restart: 130/130, 1,026/1,026 and 6/6 on each side. These checks validate cache preservation with queue mode off; they are not Rust performance measurements and are outside listing timings. The engine now runs binary `2e2df880…`, with the queue candidate off, selected span indexing on, normal GC and no active session. No PR is opened.

[The evidence archive](experiments/otel-evicted-queue/) contains the standalone patch, source identities, SDK checks, all component and complete-command attempts, exact engine overlays, restart checks and restored state. The SDK's source tree is verified against the unmodified pinned module; this experiment adds no production dependency override.
