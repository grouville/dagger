# Direct package hashes after batching exclusions

The [direct-path experiment](NATIVE_PACKAGE_DIGESTS.md) removed one directory
selection per crate but slowed the small collection. This follow-up repeats
that comparison on the selected module with batched child-package exclusions,
`a8ede44`. Its [isolated variant](https://github.com/grouville/dagger-rust/commit/d098517)
enables `SourceDigestPaths` and extends the native projection regression.
The experimental engine API remains required; the default module is unchanged.

The regression compares both hashing paths and materialized package directories
against an independent reference built with sequential child removals. It checks
nested ownership, file modes, sibling names, bracket and exclamation characters,
and a dangling symlink. It passes with race detection against the running engine.
A bridge first verifies the control's existing history, then recovers 130/130
results with direct hashing. Post-timing probes recover all 130 workspace and
six collection results with both variants. Their preceding edits have exactly
two and four execution markers, respectively.

## Complete edited commands

Both variants use one unchanged warm engine, separate source trees and native
histories, Rust 1.77.2 and eight compiler workers. Each command follows a fresh,
distinct source edit. Invocation order rotates with native Cargo. Telemetry
remains enabled, wcprof is off, and timing uses blocking process exit without
timeout polling. Two preparation rounds precede each eight-pair series.

| First series | Control | Direct paths | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.759 s | 0.708 s | 0.097 s | 49 ms | 6/8 |
| 130 crates, shared edit | 1.415 s | 1.390 s | 0.603 s | 49 ms | 8/8 |
| Actual package test collection | 1.010 s | 1.013 s | 0.479 s | −5 ms | 2/8 |

The implementations were swapped between the same histories without restarting
the engine. A broad file search may have overlapped that crossover, so its
samples are retained but are not used as a clean confirmation. A further series
ran without unrelated work:

| Clean confirmation with histories swapped | Control | Direct paths | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.767 s | 0.749 s | 0.097 s | 22 ms | 5/8 |
| 130 crates, shared edit | 1.427 s | 1.414 s | 0.629 s | 54 ms | 4/8 |
| Actual package test collection | 1.009 s | 1.004 s | 0.482 s | 2 ms | 4/8 |

Host I/O stalls reach 5.5% in the first series, 71.6% in the potentially
contaminated crossover and 14.6% in the clean confirmation. Engine I/O stalls
remain below 0.5%. All samples remain, including slow pairs. The leaf benefit
is modest; shared edits are inconsistent and the collection is effectively
neutral. These results do not justify a global default or a size threshold.
They also do not establish the Cargo +0.5 s target. Savings from earlier
comparisons must not be added to these medians.

## Locate the reduction

Two fresh leaf-edit wcprof captures have no dropped events or open operations.
Directory selections fall from 132 to three. The request containing 130 package
digest calls falls from 111.60 ms to 60.61 ms. This is identified by its call
count: a separate request containing two digest calls takes 64.02 ms in the
candidate capture. Selecting the longest digest request would misattribute it.

Both captures retain 26 function-call metadata requests and 110 total engine
requests. This experiment does not include the separate Go entrypoint batching
change. The profile locates less package-hash work; its intervals are not
additional complete-command savings.

The [data](experiments/native-batched-package-digests/measurements.json) retain
all three timing series, pressure samples, profile summaries, per-request
digest counts and correctness outcomes. Measurement, confirmation and profile
drivers are archived beside it. The module branch is pushed to Guillaume's
fork; no upstream PR is open.
