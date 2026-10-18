# Check metadata and logging changes against the full Go listing

Neither change establishes a consistent speedup for listing every Go test on dagger/dagger. Both remain off in the experimental engine. The review queue is unchanged: 19 Dagger proposals and one Go module proposal. No PR is opened.

| Independent comparison | Full-command median, before → after | Faster pairs | Decision |
| --- | ---: | ---: | --- |
| Clone sealed client metadata after unlocking | 37.33 → 37.43 s | 2/4 | Keep off; no new proposal |
| Import Sipsma's ordered log writer | 37.24 → 36.02 s | 2/4 | Mixed; keep off here |

The median paired saving is **−0.59 s** for metadata and **+1.22 s** for logging. These are separate comparisons, not additive improvements. The latter measures only the queue portion of upstream PR 14653: both arms keep the original logrus formatting lock. It does not assess the entire upstream change.

Each cohort has four fixed alternating pairs after one excluded initialization pair. Every invocation starts a fresh CLI and receives a fresh source comment on the same warm engine and retained volume. Initialization adds a real test, then measured commands remove it. All 20 commands return the correct ordered rows: 4,399 during initialization and 4,398 during measurement. All exit successfully. Source files, module configuration, diagnostic flags and profilers are restored.

Timing includes the whole CLI process and session cleanup. Both arms also wait for an explicit final engine-log flush inside the timer. The largest flush is 2.21 ms across both cohorts. Logs and telemetry remain enabled; warnings are synchronous; the queue is bounded. Neither GC nor maintenance is deferred. No cache reset, forced GC, changed concurrency limit, resampling or discarded failure is used.

The metadata change is one method: retain the sealed-state check and pointer read under the existing mutex, then perform the unchanged deep clone after unlocking. Full clean-main server race suites pass before and after. Parallel component throughput improves, but the larger serial component is about 3% slower. The full listing is the selection criterion, and it does not improve. The standalone experiment is uncommitted and unpushed; its exact sources and component observations are archived for inspection.

The logging experiment imports the upstream writer and its tests exactly, with a separate diagnostic switch that drains the old mode before switching. Writer, switch and client-metadata race checks pass. Neither comparison reduces listing allocations: the median is 29.16 → 29.55 GB for metadata and 29.34 → 29.92 GB for logging. Small changes in these overlapping paths do not account for the remaining command latency.

The engine binary is `760397ce75b91e5006bbc43bb46621b288a9cafe64ca9ed5a37ae09c1a872da9`, built from base `19eda924` with the archived overlay. CLI `e7ba08d0` and selected Go module `7568cd0e` are unchanged. The comparison uses the local telemetry receiver in both arms. This controls receiver latency while retaining telemetry work; it is not a measurement of Dagger Cloud latency.

All six retained Rust histories hit every action before replacement, on the first calls after a graceful restart with both candidates enabled, and after both cohorts: 130/130, 1,026/1,026 and 6/6, twice each. The same cache volume survives the restart.

The [field preparation profile](NATIVE_GO_FIELD_PREPARATION.md) instead points to repeated dependency-root construction. The next isolated Go module experiment stores one ordinary `Gomod` root per `Go` object and passes it into its module wrappers. Correctness, client rebinding and actual work reduction must pass before a complete-command comparison. A smaller call graph alone is not a speedup claim.

[Full comparisons, modes, source hashes and retained-cache checks](experiments/go-session-log-controls/). [Clean-main metadata sources, race checks and component benchmarks](experiments/clone-sealed-metadata-outside-lock/).
