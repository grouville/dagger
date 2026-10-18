# Attribute collection latency before and after field execution

A lossless capture places **9.35 seconds of the main query's critical path in field preparation**, and **4.97 seconds around field invocation**. This narrows the earlier response-execution category. The profiled full command takes **41.39 seconds**, returns all 4,398 ordered rows and exits successfully through cleanup. It establishes no additional complete-command speedup.

The selected Go module, CLI and clean repository are unchanged. Engine `7f821dcf` adds diagnostic markers in two DagQL files. Every unselected optimization stays off; telemetry, normal GC and native caching remain enabled. No compaction runs during the capture. The recorder contains **1,007,800 events, zero dropped and none open**.

## What the markers resolve

Field preparation precedes the existing call span. Telemetry setup and teardown surround it, and operation-lease cleanup follows it. New request-owned markers cover those boundaries, AST selection parsing, output conversion, operation validation and JSON response encoding. They preserve the original argument, result, error, cancellation and cleanup paths.

The main query takes 37.43 seconds. These are mutually exclusive portions of its reconstructed path, not cumulative CPU or predicted savings:

| Work on the main query's path | Time |
| --- | ---: |
| Prepare field calls | 9.35 s |
| Invocation outside recorded children | 4.97 s |
| Session lifecycle lock waits | 3.51 s |
| Host directory imports | 2.98 s |
| Cache publication | 2.85 s |
| Artifact dimension-key reads | 2.53 s |
| Searching existing search results | 2.11 s |

Selection parsing, output conversion and lease cleanup each sum to less than 0.24 seconds across their recorded invocations. Those sums overlap concurrent work and are not critical-path measurements. They do not justify a cleanup or result-conversion redesign here.

For 87,465 GraphQL preparations, the analyzer associates the unique sibling invocation with its direct call child. It leaves 48,541 internal preparations unclassified instead of guessing from timestamps. The largest aggregate preparation intervals belong to `gomod:Query.gomod`, `Gomod.at`, `GomodGoMod.subpath`, `Gomod.moduleLayoutDigest` and `GomodGoMod.selected`. Their aggregate elapsed times overlap heavily; they are not interpreter CPU or removable command seconds.

## Concrete follow-ups

Focused CPU samples attribute 5.02 CPU-seconds to preparation, including 3.31 beneath Git-client declaration lookup and 0.87 beneath sealed client-metadata snapshots. Result-reference construction accounts for only 0.06 CPU-seconds, so the capture does not support redesigning native result IDs.

The configuration guard still reads current files before result-cache lookup. The earlier [combined host request](NATIVE_CONFIG_HOST_REQUESTS.md) already removes redundant requests without a useful complete-command gain; reading first changes error handling. Neither rejected variant is repeated. A smaller candidate keeps the sealed-metadata check under its existing lock and clones the immutable snapshot after unlocking. Clean-main server race suites pass before and after. Shared-session component throughput improves in all four pairs; the larger serial case is about 3% slower. The completed full-command comparison gives **37.33 → 37.43 seconds**, faster in only two of four pairs. The candidate remains off and adds no upstream proposal.

Invocation profiling attributes 6.13 cumulative CPU-seconds to `AroundFunc`, including 2.33 beneath info logging. The local engine base predates Sipsma's merged [ordered log queue, PR 14653](https://github.com/dagger/dagger/pull/14653), commit `998141e8`. A separate controlled comparison imports its exact writer and tests from main `ff0b029a`, while keeping the original logrus formatting lock in both arms. It measures the queue subset of that PR, rather than claiming a measurement of the entire change. Every line is retained, warnings stay synchronous, and each timed command includes an explicit final log flush in both arms. Its medians are **37.24 → 36.02 seconds**, but it also wins only two of four pairs. This does not establish a consistent benefit; it remains off in this experiment.

Metadata cloning and the upstream writer queue are measured separately, one enabled at a time. Each cohort fixes four alternating pairs after an excluded initialization pair. Fresh CLI and source edits run on the same warm retained volume, with telemetry and ordinary GC enabled. All twenty commands return the expected ordered rows and exit successfully through cleanup. All observations remain in the record. [The completed comparisons and selection decisions](NATIVE_GO_SESSION_LOG_CONTROLS.md) claim no new gain or upstream PR.

## Correctness and analysis boundaries

The full DagQL race suite passes. Its initial run encounters an existing profiler assertion expecting an unscoped lease-lock name; the unchanged engine overlay reproduces that failure. The maintained assertion includes the exact result ID, with production locking unchanged. Initial failure, baseline reproduction and passing corrected suite are retained.

All six retained Rust histories hit every action before replacement and on the first calls after the graceful restart: 130/130, 1,026/1,026 and 6/6, twice each. No cache volume is reset or engine forcibly terminated.

All 7,820 API requests retain exactly one admission and one query child through the private HTTP parent header. One `Workspace.glob` request reaches the client 1.33 ms before the server's deferred query instrumentation ends. The original postprocessor wrongly requires temporal nesting at that boundary; the corrected analysis records the inversion and keeps exact parent linkage. It does not rerun the listing or infer a different parent from timestamps.

[Exact sources, markers, full capture, race checks, retained-cache checks and both postprocessing outcomes](experiments/go-query-phase-detail/).
