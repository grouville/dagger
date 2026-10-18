# Follow Go collection requests into the engine

The new recording links **all 7,820 Dang API requests** to their exact backend admission and query operations. It identifies **3.46 seconds on the critical path waiting for the session lifecycle lock**, while query preparation and result processing remain larger costs. It establishes attribution, not a speedup.

## Exact request links

The SDK uses a private loopback HTTP connection to the engine. During profiling, its transport carries the current wcprof operation ID in a private header; its handler restores that parent. Each request keeps the existing transport, authentication, body, response, cancellation and error handling. The wrapper is installed only for a profiled invocation. It records no query arguments or credentials.

A concurrent real-HTTP regression fails before the change because both backend operations have no API parent. It passes afterward, assigning each overlapping request to its own API operation. Transport and handler tests preserve request ownership, response/error identity, cancellation and malformed-header handling. The shared SDK and Dang v2 suites pass under the race detector.

The complete diagnostic command uses the selected Go module `7568cd0`, source `ff0b029a`, CLI `e7ba08d0` and engine `695ad854`. It starts a fresh CLI with a fresh source edit on the warm retained engine. Telemetry and ordinary GC remain enabled. It returns the expected ordered 4,398 rows and exits successfully in **39.53 seconds**. Its 397,897 events have none dropped or open. CPU and mutex profiling are off for this capture.

All 7,820 API operations have exactly one admission child and one query child. No matching relies on timing or client-ID inference. An earlier temporal join matched 5,816 requests uniquely and left 1,043 ambiguous; those observations remain archived and are superseded by the causal links.

## Critical path

The main query lasts 36.82 seconds. These are exclusive classes along its critical path; concurrent requests are not added together.

| Recorded class | On the critical path |
| --- | ---: |
| Query work outside the recorded child operations | 12.75 s |
| Publishing cached results | 4.30 s |
| Waiting for the session lifecycle lock | 3.46 s |
| `Host.directory` | 2.97 s |
| `Artifact.items` | 2.49 s |
| Dang function evaluation outside recorded child operations | 1.86 s |

For example, one API call takes 3.23 seconds: 2.69 seconds in admission and 0.54 seconds serving its query. Another takes 7.05 seconds, almost entirely in the backend query; its admission takes 6.6 milliseconds. Request counts alone do not explain either case. The subsequent [schema and response markers](NATIVE_METRIC_FLUSH_DISPATCH.md) separate the query's remaining unassigned work.

## CPU and memory attribution

A separate deeper diagnostic uses the isolated workspace-search prototype. It completes correctly in 40.25 seconds and records 349,050 events without loss. It combines wcprof with engine CPU windows, allocation and lock-profile deltas, and CLI allocation windows. It is not a timing comparison.

The CPU sample contains 191.50 CPU-seconds, including 37.38 in background garbage collection. Focused stacks attribute 8.22 CPU-seconds to stored protobuf-JSON array encoding, 5.54 to GraphQL operation preparation and 2.53 to client admission. These cumulative stacks overlap other categories. They are not command-time savings. In particular, schema forking accounts for about 0.45 CPU-seconds inside admission, which does not justify a large schema-generation redesign by itself.

Engine allocation counters increase by about 30.78 GB in that diagnostic. Allocation profiles publish with a GC delay and do not cover that total completely. Cumulative function samples include their descendants. Lock profiles sum waiting goroutines and likewise cannot be read as elapsed seconds saved. CLI allocation windows total about 3.10 GB; a candidate-only profile does not establish the cause of the prototype's higher memory use.

All retained Rust compilations remain reusable on the first calls after the graceful engine replacement. The cache volume is preserved. No optimization is selected from this profile alone.

## Follow the long publication stalls

The finer capture rules out two attractive explanations. The [metric-dispatch filter](NATIVE_METRIC_FLUSH_DISPATCH.md) removes only 0.24% of real tasks. GraphQL schema access contributes 28 ms on that capture's critical path. Result publication instead includes individual stalls of 3.48 and 7.89 seconds.

One targeted follow-up captures eleven engine CPU windows, allocation and mutex deltas, and four goroutine snapshots scheduled at 30, 35, 40 and 45 seconds. Every unselected performance switch is off. It returns the correct ordered rows and exits successfully in **56.42 seconds**, with 409,562 events and none dropped or open. This diagnostic includes profiling overhead and ordinary maintenance; it is not a timing sample or a regression measurement against earlier runs.

The tail CPU windows contain **16.77 CPU-seconds in engine cache pruning**, including **13.39 in metadata pruning** and **9.17 in class compaction**. Those cumulative numbers overlap. The 40-second goroutine snapshot finds cache-usage collection running while publication waits; the 45-second snapshot places the maintenance goroutine in class compaction. Other samples show publication blocked on cache locks. These observations explain why exclusive API or publication time can grow without equivalent compiler work.

The main query's critical path in this follow-up attributes 13.97 seconds to response execution outside recorded children, 11.96 to `Artifact.items`, 9.16 to publication and 2.77 to the session lifecycle lock. The categories partition that capture's path; they must not be added to another capture's numbers. CPU windows can extend slightly beyond command completion. A net increase in class slots does not establish that compaction was absent during a command.

The next isolated implementation target is [copying live digest sets during compaction](NATIVE_CACHE_COMPACTION_DIGEST_SETS.md). Cache maintenance remains enabled. Its cost and lock duration need improvement; deferring it would leave that work outstanding.

[Request-link sources, regression and capture](experiments/dang-request-parent-links/), [deeper attribution](experiments/go-api-backend-attribution/), [publication-tail evidence](experiments/go-publication-tail/) and [the fixed allocation experiments](NATIVE_GO_ALLOCATION_BUNDLES.md) preserve the evidence and its limits. The [attribute-array encoding screen](experiments/attribute-array-encode/) also stays unselected: both race-test modes pass, but four component pairs show effectively unchanged time, 23.969 → 23.944 µs, with only two improvements.
