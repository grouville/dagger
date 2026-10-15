# Remove constant scripts from Rust project state

[Module experiment `83d81cc`](https://github.com/grouville/dagger-rust/commit/83d81cc) makes three private shell constants computed properties. It follows the [local package-fingerprint binding](NATIVE_PACKAGE_FINGERPRINTS.md). The runtime-encoded project object shrinks from **1,392 to 342 bytes**, while the three executable strings remain identical. Complete-command measurements remain mixed, so this branch is isolated and no PR is open.

The change affects only `main.dang`. Compiler helper, model, worker and dependency files are identical to the comparison module, `cd6d25e`. It does not change the compiler cache algorithm or the native backend's opt-in status.

## Verified behavior

Temporary module copies expose the executable strings and `JSON.encode(packages(source: source))`. The three strings are byte-for-byte equal before and after. The nested project loses exactly `cargoLayoutProbe`, `layoutSelect` and `publishLegacyArtifacts`; every other field is equal. Computed properties are excluded from object state by Dang's existing function serialization rule.

The normalized compact JSON sizes are 1,342 and 342 bytes. Preserving the runtime's actual JSON escaping gives 1,392 and 342 bytes. The earlier report used normalized JSON sizes; the distinction matters when discussing literal transport bytes. The SDK's `runtime.eval` also uses `json.Marshal(result)`, so this is the same object serialization mechanism, rather than a custom representation added by the probe. Neither measured module contains probe methods.

Fourteen independent Cargo comparisons pass for discovery and invalidation, including edited Rust, added targets, package renames, lock changes, symlinked manifests and retargeting, `.cargo` fallback and invalid manifests. Ordinary native checks compile a fresh edit, reject invalid Rust with a compiler diagnostic and succeed after repair. The existing Cargo check path also passes, exercising the layout probe and layout selection. The string comparison checks artifact-publication script preservation too.

After benchmarks and profiles, a preparation pass compiles current inputs, including edits made only for listing. A separate strict pass then reuses all 130/130, 1,026/1,026 and 6/6 compiler actions in both histories. Unchanged inputs are correctness checks only.

## Complete edited commands

The comparison uses the same warm owned engine, buffered CLI and full telemetry pipeline in both arms. Both use the existing local fingerprint, metadata-name cache, selected attribute decoder and per-batch telemetry metadata reuse. Source-import snapshot seeds and snapshot-notification changes are off. The new cache-usage-map engine change is **not installed** in this engine.

Wcprof and diagnostic counters are off during timing. Every invocation edits a used Rust value after admission and before starting the command timer. Orders rotate. Cargo uses Rust 1.77.2 and incremental compilation. Every listing must contain exactly the expected 1,026 package names.

Admission criteria are fixed before collecting the new cohorts: one second with no engine sessions, host/engine I/O stall below 5%/1%, host CPU stall below 10% and engine CPU usage below 0.05 CPU-seconds per second. The existing 60-second admission limit remains. These criteria reduce carryover from background engine work; admitted samples are never removed afterward. They differ from earlier reports, so absolute timings should not be compared across reports as another speedup.

Eight initial pairs:

| Command | Before median | After median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.689 s | 0.674 s | 0.130 s | 0 ms | 4/8 |
| List, 1,026 packages | 3.651 s | 3.769 s | 0.450 s | −122 ms | 4/8 |
| Grouped check, 1,026 crates | 2.044 s | 1.959 s | 0.794 s | 46 ms | 4/8 |
| Small workspace tests | 1.030 s | 1.024 s | 0.511 s | 36 ms | 5/8 |

Eight confirmation pairs exchange physical histories:

| Command | Before median | After median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.705 s | 0.690 s | 0.128 s | 14 ms | 6/8 |
| List, 1,026 packages | 4.012 s | 3.472 s | 0.442 s | 549 ms | 6/8 |
| Grouped check, 1,026 crates | 2.020 s | 1.984 s | 0.788 s | −12 ms | 3/8 |
| Small workspace tests | 0.999 s | 0.985 s | 0.500 s | 6 ms | 4/8 |

Neither listing nor large edited checks establish a repeatable latency benefit across the two cohorts. Engine CPU is mixed too: listing medians rise from 12.156 to 14.314 seconds initially, then fall from 17.728 to 11.917 seconds in confirmation. Large-check CPU falls initially and rises in confirmation. State reduction is proved; a complete-command CPU reduction is not.

Maximum host/engine I/O pressure during admitted samples is 35%/9% initially and 4%/1% in confirmation. The slowest commands take 4.37 and 4.77 seconds. All remain included. The large-check target of native Cargo plus 0.5 seconds is still unmet.

## Where the remaining listing time goes

Two diagnostic listing captures, separate from latency measurements, pass the exact 1,026-name assertion and have no dropped or open wcprof operations. The captures contain **one** Dang parsing pass and **one** inference pass each. In the reference capture they take about 2.7 ms each. A hypothesis that Dang reruns the program once per crate is contradicted by this profile.

The reference capture publishes 13,677 graph results. It resolves metadata fields for 1,026 artifacts and their dimension keys. Wcprof attributes about 839 ms of that capture's critical path to result publication. Its summed concurrent durations are not wall time, and the publication span includes waiting; this does not identify one specific lock as the cause.

A ten-second engine CPU capture includes the command and subsequent engine work. Attribute protobuf-JSON decoding (`UnmarshalProtoJSONs`) accounts for 3.62 seconds of cumulative sampled CPU, SDK span conversion (`SpansToPB`) for 3.15 seconds, and Go GC for 3.21 seconds. Cumulative frames can overlap and must not be added. These remain substantial costs after the earlier telemetry improvements; support for telemetry stays enabled.

The next useful investigation is repeated metadata-result publication and telemetry conversion. The [separate empty-map change](CACHE_USAGE_ALLOCATIONS.md) already removes a measured allocation cost during cache accounting, but its complete-command effect still needs measurement.

[Raw samples, pressure, probes, compressed wcprof captures, CPU profiles and local harnesses](experiments/constant-scripts-and-usage-maps/).

Follow-up: [direct stored-span forwarding and retained engine memory](NATIVE_DIRECT_SPAN_FORWARDING.md) records the next measured engine experiment.
