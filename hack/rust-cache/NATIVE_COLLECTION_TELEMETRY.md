# Rust collections: output correctness and remaining overhead

The investigation found a CLI output bug and reduced the cost of rendering and decoding telemetry. The listing benefits in both edited-command comparisons; build and test results remain mixed. All changes are pushed to Guillaume's forks. No PR is open.

## Complete collection output

`dagger check --list --all rust:packages/check` sometimes returned success with missing packages. One capture printed only 341 of 1,026 rows and lost the header. Earlier listing measurements that checked only the header are unsuitable for evaluating complete output.

The table writer emits cells and padding separately. Each write becomes a telemetry log record, so a 1,026-row table creates 6,163 records and can overflow the SDK's 2,048-record queue. The [CLI fix](https://github.com/grouville/dagger/tree/fix/buffer-artifact-list-output) buffers list output in 4 KiB chunks and returns flush errors. A separate commit reuses the cell formatter once per table.

| Renderer through a synchronous telemetry exporter | Time per 1,026-row table | Allocated bytes | Log records |
| --- | ---: | ---: | ---: |
| Original | 9.87 ms | 24,752,793 | 6,163 |
| Buffered | 6.94 ms | 21,994,120 | 8 |
| Buffered, formatter reused | 1.42 ms | 1,187,380 | 8 |

These are three-sample component medians, not complete-command timings. A deterministic regression blocks the real SDK exporter during a 4,096-row burst and checks every row in table, link and CLI formats. It fails before buffering and passes afterward. Output, delimiter escaping and write-failure tests also pass under the race detector. The real CLI prints all 1,026 expected packages exactly once.

Commits: [buffer output](https://github.com/grouville/dagger/commit/56fb4f1e4), [reuse the formatter](https://github.com/grouville/dagger/commit/c72dd20d0). Both start from main `249edbd646`.

## Rust package discovery

The [module branch](https://github.com/grouville/dagger-rust/tree/perf/metadata-toolchain) separates three changes:

- Prepare package metadata without the source-reconciliation probe or default build-tool downloads. Explicitly requested OS packages remain available.
- Select configured Rust toolchains with older rustup. The pinned Rust 1.77 image's rustup rejects the previous install command without a version; `show active-toolchain` selects its installed toolchain successfully.
- Read package names directly from `cargo metadata --no-deps`, which returns workspace members. This removes a quadratic membership filter.

Virtual and root-member workspaces with excluded path dependencies return the correct package names. Both toolchain-file formats reject invalid selections, and an installed `1.77.2` selection succeeds. The legacy check smoke test passes. Compiler worker inputs are byte-identical to `d565c70`.

The complete-output crossover gives median paired savings of 81 ms for listing, 25 ms for the 1,026-crate check, and −2 ms for small tests. Only five of eight listing/check pairs improve; the unrelated 130-crate control regresses by 27 ms. These results do not establish a general execution-speed benefit. The first listing cohort and its interrupted crossover are retained as invalid-output evidence.

## Decode stored attributes with fewer allocations

The engine CPU capture attributes 6.68 of 28.38 sampled CPU seconds to span conversion, including repeated JSON decoding. These cumulative call-tree totals overlap. The [decoder experiment](https://github.com/grouville/dagger/commit/54526d4fb) parses attribute arrays through Protobuf's `KeyValueList`, avoiding the intermediate `RawMessage` array and per-element decoder setup. Empty arrays take a shorter path.

The original JSON syntax and nesting limits are preserved. An adversarial deeply nested input exposed a difference in the first prototype; the final version keeps JSON validation. Comparison against the old decoder covers empty values, allowed whitespace, all attribute types, malformed data and unchanged output on error. The final fuzz run completes 471,926 executions. Client database and focused ingestion, streaming and Cloud-delivery tests pass under the race detector. The production change adds no shared state, locks, dependencies or persistence format.

| Attributes | Original decode | Final decode | Original/final bytes allocated |
| --- | ---: | ---: | ---: |
| 4 | 10.39 µs | 9.00 µs | 2,624 / 1,992 |
| 32 | 77.70 µs | 63.61 µs | 19,456 / 13,549 |
| 1,024 | 2.46 ms | 1.98 ms | 626,049 / 431,773 |

Five-sample medians use Go 1.26.6 and `GOMAXPROCS=8`, without concurrent builds, engine shutdown or profiling. Preliminary measurements that omitted validation or overlapped shutdown are not selected.

Both complete-command cohorts use module `30600fd`, the same warm engine and separate existing native histories. Every invocation edits a used Rust value. Order rotates; the crossover swaps physical histories. Telemetry stays enabled, wcprof stays disabled, immutable source-import seeds are off in both arms, and decoder selection happens outside the timer. Cargo uses Rust 1.77.2 and incremental compilation. All listing outputs must contain the exact 1,026-package set.

| Complete edited command | First cohort: paired saving, wins | Crossover: paired saving, wins |
| --- | ---: | ---: |
| Check, 130 crates | 7 ms, 5/8 | 19 ms, 5/8 |
| List, 1,026 packages | 192 ms, 6/8 | 305 ms, 7/8 |
| Grouped check, 1,026 crates | 21 ms, 4/8 | 65 ms, 6/8 |
| Small workspace tests | 17 ms, 7/8 | 8 ms, 4/8 |

All observations are retained. Maximum host I/O pressure is 16% in the first cohort and 53% in the crossover; the latter includes 18-second control and 33-second candidate stalls. The listing improvement repeats across histories. The benefit for ordinary builds and tests remains uncertain. The crossover's candidate check medians are 0.679 s for 130 crates and 2.337 s for 1,026 crates, versus Cargo's 0.129 s and 0.804 s. The overall target remains unmet.

After engine restart, both histories reuse every action: 130/130, 1,026/1,026 and 6/6. The subsequent profiling edit rebuilds exactly two of 1,026 actions, followed by full reuse again. Compiler results and incremental state remain native Dagger snapshots. The diagnostic decoder switch is restored off after verification.

## Next measured bottleneck

Wcprof places about 1.21 s of result publication on the large listing's critical path. A complete engine runtime trace confirms contention on the cache's global `egraphMu`: publication waits at the indexing lock and snapshot-completion notification lock. The notification's write lock dominates its admission-flag read. The trace's 49.43 and 40.70 seconds at those sites sum waits across concurrent goroutines; they are not command durations or additive savings.

The second diagnostic command takes 28 seconds and outlasts its ten-second engine capture. Its CLI trace is complete; the engine trace cannot establish the cause of the full stall or support a before/after lock comparison. Profile the work holding the write lock and reduce unnecessary notifications or repeated result construction before choosing a synchronization change.

The control engine also takes 95.57 seconds to shut down, with captures in SQLite mirror clearing and saving. A subsequent idle diagnostic engine takes 41.27 seconds. Both exit zero and preserve the volume; the latter exceeds the helper's 45-second startup-readiness window before later passing all six cache checks. These observations do not measure a decoder-induced shutdown regression.

Evidence and local harnesses: [collection-telemetry](experiments/collection-telemetry/). The standalone CLI regression and decoder benchmarks live in their fork commits. Raw runtime traces remain under `/tmp/rust-cache-sipsma-review/rust-collection-sync-profile`; archived profiles, samples and pressure records accompany this report. The local harnesses reuse the existing generated workspaces and experimental engine. Registry dependencies, general build scripts and procedural macros still need work before the native compiler backend is ready for general use.
