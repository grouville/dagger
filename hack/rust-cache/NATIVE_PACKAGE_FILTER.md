# Copy retained package sources

The selected root-package projection removes its nested packages in one
`withoutFiles` snapshot. Removing directories still traverses their files.
This experiment instead copies the retained tree with `Directory.filter`,
excluding the immediate child packages. Packages with zero or one child keep
their previous recipe. It adds no engine API.

The native projection regression passes under race detection. It compares
materialized directories and package hashes with sequential child removals,
including nested ownership, sibling paths, modes, special names and a symlink.
A bridge first verifies a control history, then recovers its 130/130 compiled
results through the filter variant. This also checks real imported source.

The experiment is not selected. Literal path escaping for filter patterns adds
complexity; newline and edge-whitespace cases remain unverified. The archived
patch is a performance experiment, not a completed literal-path interface.

## Complete edited commands

Both variants use one unchanged warm engine, separate source trees and native
histories, Rust 1.77.2 and eight compiler workers. Each command follows a fresh,
distinct edit. Invocation order rotates with native Cargo. Telemetry stays
enabled and wcprof is disabled. The timer uses blocking process exit without
timeout polling. Two preparation rounds precede eight pairs per scenario.

| First series | Batched removal | Filtered copy | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.752 s | 0.753 s | 0.099 s | −22 ms | 3/8 |
| 130 crates, shared edit | 1.650 s | 1.468 s | 0.625 s | 219 ms | 5/8 |
| Actual package test collection | 1.052 s | 1.096 s | 0.482 s | −24 ms | 3/8 |

Host I/O stalls reach 88.1% and engine I/O stalls reach 11.2%. Swapping the
implementations between those same histories, without restarting the engine,
does not reproduce a general benefit:

| Histories swapped | Batched removal | Filtered copy | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.715 s | 0.737 s | 0.098 s | −8 ms | 4/8 |
| 130 crates, shared edit | 1.414 s | 1.411 s | 0.604 s | 37 ms | 5/8 |
| Actual package test collection | 0.999 s | 0.987 s | 0.482 s | 9 ms | 4/8 |

Host I/O stalls reach 16.5% in this crossover; engine I/O stalls stay below
0.2%. No unrelated build, test or profiling capture runs during either series.
All samples remain. The small fixture is a virtual workspace and has no root
package requiring multiple child exclusions; its command comparison also
illustrates the background variation in these measurements.

## The profile supports only the local mechanism

Fresh leaf-edit wcprof captures have no dropped events or open operations.
The 130-package digest request falls from 81.84 ms to 41.09 ms. In the control,
`Directory.withoutFiles` takes 64.23 ms. In the candidate, the additional
`Directory.filter` takes 24.26 ms. Both captures retain 26 function-call
metadata requests and 110 total engine requests. These are phase measurements,
not additional complete-command savings.

The local reduction does not justify changing the source recipe globally.
A workspace with many files in excluded packages could benefit more; a large
retained root could make copying more expensive. Neither case has been timed
here, and no size heuristic is selected.

The [measurements](experiments/native-package-filter/measurements.json) retain
both series, pressure samples, profile summaries and correctness outcomes.
The isolated patch and local drivers are archived beside them. No module
default changes and no upstream PR is open.
