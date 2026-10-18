# Configuration lookup: request setup and batching screen

The confirmed native telemetry change leaves the complete listing at **32.78 seconds median** in reversed-order confirmation. This follow-up analyzes existing captures; it installs no candidate and establishes no new latency gain.

The engine profile still places **6.01 seconds of configuration stats and 3.32 seconds of reads** on its main query's critical path. Those are intervals around host requests. They do not show that filesystem calls themselves take nine seconds.

## Where setup CPU goes

The unchanged CLI profile contains **1.08 cumulative sampled CPU-seconds** under local-import option decoding and **0.83 seconds** under trace-context extraction. These include nested work:

| Nested work | Sampled CPU |
| --- | ---: |
| JSON decoding of local-import options | 0.66 s |
| Parsing propagated telemetry baggage | 0.58 s |
| Joining and decoding metadata maps | 0.23 s |

These CPU durations overlap their parents and are not elapsed-time savings. Metadata copying alone cannot explain the much larger critical-path cost. The previously recorded stat and file-read frames account for 0.28 and 0.40 CPU-seconds respectively. A joint request trace is needed to distinguish queueing, transport, scheduling and handler work. No library replacement is justified by this screen.

## Batch only before observing the file

Sharing an already-running read remains rejected: a later caller can start after an edit but receive bytes that were read before it. A narrower hypothesis would close a batch before its first filesystem observation. Every admitted caller would therefore begin before that observation, and later callers would require a separate read. Cancellation, error delivery and source-owner isolation would still need a real implementation and adversarial tests.

The existing engine capture contains 15,003 declaration guards and their first stat, owner-metadata and backend-client phases. A fixed-schedule screen groups requests only until the leading request's first stat begins. It tests three possible admission points:

| Admission point, no added wait | Hypothetical batches | Grouped followers |
| --- | ---: | ---: |
| Guard entry | 9,552 | 5,451 |
| Source owner resolved | 11,674 | 3,329 |
| Backend client ready | 14,940 | 63 |

The earliest number includes work before the caller has resolved the correct host owner. The middle number also includes backend setup. Once that setup finishes, only **0.42%** of requests join another batch in this schedule. This does not support a major benefit from merely combining requests at that late point.

Adding hypothetical 100 µs and 1 ms windows after backend setup produces 11,848 and 6,298 batches respectively. Those windows introduce waiting; the screen cannot predict their total command cost. It changes neither the real schedule nor any filesystem behavior. The trace records engine phase boundaries, not the physical CLI read instant, and a real batching implementation could change the schedule substantially. These are hypothesis checks, not safe cache keys or benchmark results.

## Next measurement

The recorded median request intervals are **19.75 ms for stat** and **20.59 ms for read**, across concurrent calls in one diagnostic listing. Their summed durations are not command time. The missing measurement is a causal breakdown from engine request creation through CLI receipt, decoding, filesystem access and response delivery.

That breakdown should guide a reduction in the work of each fresh lookup. The earlier combined stat/read experiment removed requests without demonstrating a command speedup, so a new proposal needs stronger evidence than request counts. Configuration edits, nearest-file selection, host ownership, metadata errors, cancellation and older-client compatibility remain required.

[Evidence](experiments/local-import-metadata/) retains the focused CPU reports, screen driver and all three admission-point results. The source captures remain in the [engine](experiments/telemetry-native-storage/) and [CLI](experiments/go-listing-cli-cpu/) archives. Native writing remains disabled in the controlled engine, with v2 and dual-format readers retained. No PR is opened.
