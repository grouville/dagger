# Parse workspace TOML once: less work, no reliable listing gain

Full Go test listing takes **48.24 → 47.45 seconds median**, but only two of four matched pairs improve. The median paired difference is **0.40 seconds slower**. Every command returns the expected rows and exits successfully. The experiment remains disabled; the latest selected complete-command result is still **53.58 → 46.72 seconds** from the separate span-index comparison.

## Change and compatibility

The [API profile](NATIVE_DANG_API_REQUEST_PROFILE.md) found repeated configuration parsing before module-function cache lookup. `ParseConfigAt` parses the same bytes once through `toml.Unmarshal` to decode a `Config`, then again through `toml.LoadBytes` to check unknown fields.

The patch shares one TOML document between the existing typed decoder and field checker. `ParseConfig` and `CheckConfigFields` retain their public entry points through small private helpers. The same SDK validation, scope reconciliation and warning loops still run in the same order. The library's `Unmarshal` already delegates decoding to `Tree.Unmarshal`; its `LoadReader` only copies the bytes before calling `LoadBytes`.

No memoization, host-read policy, dependency, lock, cache key or ownership rule changes. Each configuration load still reads and parses its current input. In particular, Git-client declarations can change on the live host, and unreadable declarations must continue preventing result reuse.

The original and candidate pass the workspace unit package. The candidate also passes race checks. The added compatibility check verifies that decoding does not consume an otherwise unknown case-variant key or change its reported position, while arbitrary nested settings remain accepted. Existing coverage checks legacy warnings, SDK scope reconciliation, invalid configurations, configuration writes and nearest-config Git-client selection. The A/B wrapper is checked separately in both modes, including race checks for the candidate.

## Complete-command comparison

Both arms use one engine binary, module and CLI. Every invocation starts a fresh CLI and edits a Go source comment on a warm engine. Telemetry, normal GC and selected span indexing remain enabled; profiling and unrelated experiments remain off. The complete command is `dagger check --module go --check test --list --all`.

| Pair | Two parses | One parse |
| --- | ---: | ---: |
| 1, candidate first | 47.95 s | 47.46 s |
| 2, control first | 42.29 s | 43.58 s |
| 3, candidate first | 58.47 s | 47.45 s |
| 4, control first | 48.54 s | 50.88 s |

All eight measured commands return identical 4,398 rows and exit zero. The separate initialization pair adds one real test, returns identical 4,399 rows in 48.21 → 42.37 seconds and is excluded. Removing that test restores the expected listing. No result-based exclusions are made.

Median engine CPU falls **236.07 → 232.68 CPU-seconds** and cumulative allocation **37.38 → 36.76 GB**. Sampled peak heap is **14.19 → 14.00 GB**, which does not establish a retained-memory improvement. Host I/O stalls peak at 10.34%, engine I/O at 2.35%; both peaks occur in candidate runs. The slowest control has low measured I/O pressure. All observations remain included, and the smaller column median is not evidence of a consistent latency gain.

## Parser benchmarks

Four sequential processes alternate original/candidate/candidate/original, with two samples per case. Every iteration performs a fresh parse and validation; there is no warm parse cache.

| Fixture | Before | After | Bytes allocated before → after |
| --- | ---: | ---: | ---: |
| Small workspace config | 44.00 µs | 34.73 µs | 36,937 → 22,401 |
| 32 SDK scopes | 648.50 µs | 452.96 µs | 324,892 → 210,186 |
| 256 SDK scopes | 5.16 ms | 3.57 ms | 2,629,677 → 1,666,739 |

The component improvement is clear, but does not justify a full-listing speedup claim. The standalone patch contains only parser reuse; experimental switches and handlers are excluded.

The owned engine restarts gracefully on the same volume. All six retained Rust histories reuse every compiler action before and after: 130/130, 1,026/1,026 and 6/6 on each side. These are cache-preservation checks with the parser mode off, outside command timing. The engine now runs `cf88d6dc…`, with the parser candidate off, normal GC and no active session.

[The evidence archive](experiments/workspace-single-toml-parse/) retains the patch, source identities, tests, every component/full-command attempt, exact engine overlays, restart checks and restored state. It is pushed for review; no PR is opened. The listing goal remains incomplete.
