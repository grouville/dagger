# Native Rust compiler preparation

The Rust module is written in Dang. Its experimental native-cache path calls a
Go submodule, `compiler`, which selects reusable results and builds Dagger
operations. A separate Go program runs inside the Rust container and launches
the selected `rustc` processes. The timings below distinguish those components.

## Measure the Go submodule's preparation

Temporary instrumentation splits the Go function into phases and times its
nested engine requests. Two detailed captures of fresh leaf edits in the
102-crate workspace show:

| Phase | First capture | Second capture |
| --- | ---: | ---: |
| Read the retained plan through the API | 43.9 ms | 45.0 ms |
| Decode the plan JSON | 17.0 ms | 12.2 ms |
| Check Cargo configuration | 25.8 ms | 22.3 ms |
| Read source paths | 34.9 ms | 28.0 ms |
| Hash package directories | 49.1 ms | 40.6 ms |
| Synchronize compilation outputs | 516.9 ms | 460.0 ms |

The last interval includes actual compilation and engine filesystem work.
These are diagnostic wall times, not CPU measurements or unprofiled benchmark
medians. The graph-construction timer contains package hashing; do not add it
again. Preparation runs include several seconds of module/tool building and
are retained separately from the warm edit captures.

The retained plan is 774,947 bytes, including 203 compiler actions and 203 test
commands. A subsequent probe reuses all 203 compiler results. The many-crate
Dang preparation takes about 7 ms in one capture, with schema opening below
0.1 ms. The earlier large schema-opening interval came from the separate
128-check fixture and does not establish the same cost for Rust.

The earlier estimate of 153 ms between server requests remains unattributed:
it includes transport and client response handling as well as local Go work.
The finer timers above identify particular operations without treating that
whole interval as Go computation.

The [diagnostic patch](experiments/native-compile-phases/diagnostic.patch) applies
to Rust module `3ee3187`. It records phase names, durations and query lengths,
without query contents or environment values. It is temporary instrumentation;
the measured production candidates do not include it. Raw phase records and
benchmark samples are in
[measurements.json](experiments/native-compile-phases/measurements.json).

## Smaller dependency descriptions: no command gain

For a leaf edit, three actions run. The execution program reads only IDs,
outputs and graph edges from the other dependency descriptions, while the
submodule sends their full compiler commands and environments. The actual Go
encoding is 429,695 bytes; the reduced description is 90,862 bytes. A small
experiment sends only the fields those descriptions need. Commands for actions
that execute remain complete; the execution program and its binary do not
change.

Six rotated pairs use the same engine, independent project caches, fresh edits
on every command, telemetry enabled and wcprof disabled. All commands pass.
The control median is 3.003 s, candidate 3.021 s and native Cargo 2.065 s.
Only two of six candidate runs are faster; median paired saving is -75 ms.
Maximum CPU/I/O pressure is 3.9%/2.1% during measured commands.

The smaller transfer has not demonstrated an edited-command benefit. It stays
isolated. Removing bytes or requests is useful evidence about work removed;
it is insufficient evidence that the user's command became faster.
Implementation: [a6e77f8](https://github.com/grouville/dagger-rust/commit/a6e77f8).

## Reuse the evaluated batch snapshot

Another isolated variant synchronizes the batch's output root once, then uses
that resolved snapshot for artifacts and cache publication. Previously, the
submodule synchronized the artifact subdirectory and subsequently sent the
large recipe again to identify the retained output root. The variant keeps
source inputs, compiler commands, cache keys and test commands unchanged.

Eight rotated test-command pairs initially look promising in the many-crate
workspace: 3.239 s to 3.048 s, 205 ms median paired saving, eight of eight pairs
faster. The small workspace shows no gain: 0.935 s versus 0.945 s, three of
eight faster and -28 ms median paired saving. Maximum CPU/I/O pressure is
36.0%/12.1%.

Swapping the implementations between the existing cache histories does not
confirm the result. The many-crate candidate wins four of eight pairs, with
-31 ms median paired saving. Cargo's median rises from 2.082 s in the first
series to 2.579 s in this series, and reaches 4.677 s in one run. Host I/O
pressure reaches 87.8%. Keep the entire series, including the 12.343 s
candidate outlier; it does not establish a repeatable code benefit.

A further comparison uses compilation checks, separating compilation from the
203 test-process launches. Eight leaf and shared-library pairs each have four
candidate wins, with -11 ms and -17 ms median paired savings. This time host
I/O stalls stay below 2.1%, while host CPU stalls reach 70.8%. The owned engine's
CPU/I/O stalls reach 19.1%/0.54%; pressure on the host cannot all be attributed
to this engine. No unrelated build, test or benchmark runs alongside ours.

Four complete wcprof captures preserve three executions per test command.
Resolving the root adds one engine request; `Container.directory` calls fall
from four to two. These counts verify the implementation, not a latency gain.
Focused race checks pass, and a real leaf edit recompiles three actions while
retaining 200 of 203 results and running the normal tests. The variant remains
isolated rather than becoming the selected module.
Implementation: [77923cf](https://github.com/grouville/dagger-rust/commit/77923cf).
