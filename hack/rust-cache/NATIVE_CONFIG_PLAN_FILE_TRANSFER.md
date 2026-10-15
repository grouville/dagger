# Transfer compiler-plan metadata after adding the configuration guard

The [earlier file-transfer experiment](NATIVE_PLAN_FILE_TRANSFER.md) had mixed complete-command results. This follow-up repeats it on the current engine and module, including the primitive-array codec fix and native configuration guard. It changes only how the Go compiler module reads the retained plan: export the file into a private temporary directory, read its bytes, then remove the directory. The plan format, decoder, compiler keys and worker inputs stay unchanged.

The [candidate module](https://github.com/grouville/dagger-rust/commit/d565c70) starts from `3e8209e`. Both modules run on the same engine at port 16276; no engine change or restart is part of this comparison. Compiler results and rustc incremental state remain native Dagger snapshots. Only metadata already read by the module takes the file-transfer path.

## Complete edited commands

Every command changes a used Rust value and starts a fresh CLI. Each implementation has its own existing source and native cache history. The first series uses eight rotating pairs per scenario, two preparation rounds, enabled telemetry and disabled wcprof. Cargo uses the same pinned Rust 1.77.2 toolchain, incremental compilation and eight jobs. Timing waits for process exit without timeout polling.

| First series | Plan text | Plan file | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130-crate leaf | 0.705 s | 0.682 s | 0.131 s | 24 ms | 6/8 |
| 130-crate shared dependency | 1.365 s | 1.354 s | 0.646 s | 10 ms | 4/8 |
| 1,026-crate leaf | 1.796 s | 1.724 s | 0.799 s | 60 ms | 6/8 |
| Actual small collection tests | 1.121 s | 1.100 s | 0.513 s | 21 ms | 4/8 |

The implementations are then swapped between the same histories, without restarting the engine. The large-leaf medians become 2.379 s versus 1.777 s, with a 341 ms median paired saving and six faster pairs. However, host I/O stalls reach 60%; 11 of 96 measured commands exceed 10%. The first series reaches 18.7% host stalls. These samples are retained, but the larger crossover difference is not a clean estimate of the implementation's benefit. The small collection and shared edit remain mixed.

A separate eight-pair large-leaf confirmation requires two quiet seconds before every launch, with no engine sessions or active requests, host I/O stalls below 5% and engine stalls below 1%. It retains every measured sample, including stalls after admission. Preparation is excluded; admission waits are recorded separately.

| Quiet-start confirmation | Plan text | Plan file | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full edited command | 1.841 s | 1.778 s | 0.832 s | 44 ms | 6/8 |

Admission takes 78.05 seconds over 39 windows for 30 launches. Measured host stalls stay below 9.74% and engine stalls below 0.32%. The 63 ms difference between column medians differs from the 44 ms median of paired differences. This measures isolated warm edited commands; neither cold starts nor sustained throughput are established. The Cargo-plus-0.5-second target remains unmet.

## What the profiles establish

Separate wcprof captures alternate fresh edits on both implementations. Large-plan requests take 73.4, 68.7 and 68.8 ms through `File.contents`, versus 18.1, 19.4 and 23.5 ms through `File.export`. The old file resolver itself takes only 1.2–1.5 ms. The file path avoids roughly 50 ms of request handling on these captures. The small-plan requests take roughly 1–2 ms through either path, consistent with no established small-collection gain. All ten captures have zero dropped events and open operations.

The integration test passes under race detection on this engine for exact Unicode and escaped JSON, a multi-chunk 1.3 MB plan, read-only input, missing-file errors and temporary cleanup. An existing-history smoke test preserves all 1,026 results. Final checks on both histories retain 130/130, 1,026/1,026 and 6/6 results, with the expected preceding batches of 130, two and four actions. No plan recapture or compiler-key migration is required.

The variant is retained on an experimental fork branch. No official-module default or PR changes. [Measurements and drivers](experiments/native-config-plan-file-transfer/measurements.json) preserve all three cohorts, pressure, admission, compatibility checks and complete profile summaries. A [separate source-import profile](NATIVE_SOURCE_IMPORT_PROFILE.md) identifies the next larger preparation cost.
