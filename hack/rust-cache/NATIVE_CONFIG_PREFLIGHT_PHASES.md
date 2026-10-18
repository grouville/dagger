# Configuration reads and the next encoding experiment

The profile attributes **8.71 seconds of the main query's critical path** to configuration stats and reads. Sharing overlapping reads fails a freshness regression and is rejected before installation. A separate offline screen finds native Protobuf attribute encoding and decoding about six times faster than the selected JSON path. Neither finding establishes a new complete-command speedup.

The last eight-pair listing comparison remains **37.47 seconds for the selected implementation**. The [lazy-schema candidate](NATIVE_LAZY_SCHEMA_CANDIDATES.md) did not improve it consistently and remains disabled. This study adds diagnostics and an encoding component screen, without selecting another optimization or opening a PR.

## Full listing capture

The command is `dagger check --module go --check test --list --all` on dagger/dagger `ff0b029a`, with Go module `7568cd0`, CLI `e7ba08d0` and diagnostic engine `7d2d7e25`. The engine and caches are warm; the CLI is fresh and the source receives a fresh comment edit. Telemetry, ordinary garbage collection and cleanup remain enabled. All unselected candidates stay off.

The complete diagnostic command exits successfully in **44.59 seconds**, returning the exact **4,398 ordered rows**. Its main query takes **40.86 seconds**. Recording produces **1,146,600 events**, with none dropped or left open. CPU profiling, lock sampling, stack captures and added phase markers make this a diagnostic observation, not a comparison with unprofiled timings.

The added markers follow the real module dynamic-input path, including errors before the deliberate unreadable-declaration nonce fallback. They leave current-file reads, source ownership, cache inputs and error handling unchanged. No configuration contents or credentials are added to the recorder; file paths and host client IDs identify the repeated work.

| Phase | Calls | Main-query critical-path time |
| --- | ---: | ---: |
| Configuration stat | 26,804 | 5.86 s |
| Configuration read | 15,003 | 2.85 s |
| Host-owner metadata | 15,003 | 288 ms |
| Local-client guard | 15,003 | 81 ms |

Every one of the **15,003** Git-client declaration guards succeeds and reads the same module-owner `dagger.toml`. The nested `gomod` source also probes a missing nearer `gomod/dagger.toml` **11,801** times. Those expected NotFound responses do not trigger the unreadable nonce fallback. The configuration is read even when the eventual module result is cached.

Many calls overlap. Grouping each file's operations only until the first caller completes leaves 4,652 groups for 15,003 reads. This is a fixed-schedule overlap screen, not a safe cache key or an elapsed-time prediction. Summed concurrent operation durations are much larger than command time and are not used as savings.

## Why in-progress sharing is rejected

The prototype retains the original stat-then-read sequence, isolates engine sessions, host owners and exact paths, copies returned buffers, and removes completed flights before returning results. It uses the first caller's I/O context; canceled owners make remaining callers retry under their own contexts. Initial concurrency, cancellation, error, isolation and sequential-freshness checks pass under the race detector.

An adversarial regression exposes a remaining problem:

1. The host reads the old configuration, but its RPC response is delayed.
2. An edit completes on the host.
3. A second module call starts while the first response is still in transit.
4. Sharing that response gives the second call the old declaration.

The test requires the second call to see the new declaration. **It fails with sharing and passes with independent reads**, both under the race detector. Removing results promptly at completion does not solve this earlier-read gap. The prototype is rejected without engine installation, module-check execution or a timing cohort; its prepared installer has an explicit failed freshness gate.

A caller workspace's read epoch is also insufficient for this path: module configuration follows the module's own host and source tree, which may differ from the caller's workspace. No epoch cache, watcher assumption, weakened error handling or skipped read is introduced.

## Native telemetry encoding screen

The same CPU capture samples **20.68 cumulative CPU-seconds under Protobuf JSON marshaling** and **14.73 under unmarshaling**, out of **210.84 CPU-seconds**. Allocation and garbage collection also occupy substantial CPU time. These are concurrent sampled CPU totals; they are not seconds removable from the command and must not be added to the critical-path table.

The offline experiment compares the current JSON attribute-array writer and selected optimized reader with the existing generated OTLP `KeyValueList` native Protobuf codec. It introduces no codec dependency, hand-written parser or production format change. Four alternating fresh-process pairs use Go 1.26.6, linux/amd64, `GOMAXPROCS=8` and 250 ms per benchmark case.

| Component | JSON median | Native median | Faster pairs |
| --- | ---: | ---: | ---: |
| Small attribute encoding | 2.73 µs | 0.66 µs | 4/4 |
| Small attribute decoding | 4.72 µs | 1.01 µs | 4/4 |
| Representative attribute encoding | 21.14 µs | 3.57 µs | 4/4 |
| Representative attribute decoding | 36.78 µs | 6.03 µs | 4/4 |
| 64 KiB call attribute encoding | 77.96 µs | 12.34 µs | 4/4 |

Representative encoding allocations decrease **170 → 2**, with **13,901 → 3,136 bytes allocated**. Decoding decreases **166 → 62 allocations**, with **10,781 → 5,536 bytes allocated**. The fixture's encoded payload decreases **3,448 → 3,071 bytes**. The fixture is a deterministic attribute sample with a call frame, not a capture of all attribute sizes in the repository listing.

Race-tested decoded-value comparisons cover nested arrays and key/value lists, Unicode, bytes, empty lists, nil entries and unusual floating-point values. Both codecs reject invalid UTF-8. This checks the component's values; it does not prove storage compatibility or complete telemetry behavior.

A production experiment still needs versioned storage, existing JSON-row decoding, call and archive index compatibility, malformed-input handling and validation of every telemetry consumer. It then needs a complete-command comparison with telemetry and cleanup enabled. The binary codec is not installed, selected or ready as an upstream proposal.

## Cache and final state

The diagnostic engine replacement preserves the same volume and exits gracefully; the old engine spends **244.17 seconds** saving cache state to SQLite. That maintenance/setup duration is separate from listing time and has no before/after comparison in this study. It is not evidence of an added optimization cost.

All six retained native Rust histories hit every compilation action before replacement, on their first calls afterward and before the uninstalled prototype build: **130/130, 1,026/1,026 and 6/6**, twice each. These are correctness checks, not unchanged-build performance claims. Focused core race checks pass for the diagnostic overlay. The final engine remains diagnostic-only, idle, with profiling disabled and every unselected candidate off. No cache reset, forced collection or forced shutdown is used.

Evidence: [configuration profile](experiments/config-preflight-phases/), [rejected sharing prototype and regression](experiments/config-inflight-reads/), and [native encoding screen](experiments/telemetry-native-encoding-screen/). Exact overlays, copied sources, drivers, all test outcomes, raw compressed recorder chunks and component observations are retained. No PR is opened, and the upstream review queue is unchanged.
