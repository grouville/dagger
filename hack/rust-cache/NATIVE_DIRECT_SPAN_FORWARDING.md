# Forward stored span attributes without an SDK round trip

[Engine experiment `4d68998ba`](https://github.com/grouville/dagger/commit/4d68998ba) reduces allocations when forwarding stored telemetry. The shared-history confirmation reduces the edited 1,026-package listing from **3.84 to 3.43 seconds**, but the initial cohort disagrees and ordinary edited checks do not improve consistently. The experiment remains isolated, its diagnostic switch is off, and no PR is open.

## Change and correctness

The database stores protobuf-JSON attributes. Forwarding previously decoded them, converted them into SDK attributes, then constructed new protobuf attributes for export. The candidate reuses decoded protobuf attributes when that round trip preserves their value. Mixed or nested arrays and unsupported values use the existing conversion. Links and events retain their existing normalization. Resource/scope grouping and all span fields preserve the current SDK converter's behavior.

There is no new lock, global production cache, dependency, persistence format or change to telemetry producers. The direct converter must continue tracking SDK conversion behavior; differential tests compare complete exported messages, not just names or counts. Tests cover scalar and array types, unusual floating-point values, malformed input, IDs, status, timestamps, flags, dropped counts, links/events, grouping and output ownership.

The full client database suite passes with `-race` using both the default decoder and the previously selected array decoder. Focused server race tests pass for Cloud forwarding, call-frame delivery, stream framing, cursors and oversized batches. A clean engine stop exits 0 after 105 seconds and preserves its volume. After all measurements, all six histories reuse every native compiler action: 130/130, 1,026/1,026 and 6/6 in each arm. Compiler artifacts and incremental state remain native Dagger snapshots.

## Measurements

The component benchmark uses 512 rows, Go 1.26.6, `GOMAXPROCS=8`, three repetitions and the same selected array decoder in both arms. With 16 attributes and no links, median construction decreases from 26.82 to 23.09 ms; allocated bytes decrease from 7.86 to 4.54 MB and allocations from 194,140 to 142,922. With a wait link, construction decreases from 31.27 to 27.31 ms and bytes from 8.76 to 5.51 MB. A one-attribute row benefits less. These benchmarks measure conversion, not a complete export or command.

Complete commands use the same warm engine binary, telemetry enabled, Rust module `cd6d25e`, buffered CLI, selected array decoder and batch metadata reuse. Only the stored-span forwarding switch changes. Snapshot completions and source-import snapshot seeds remain off. The separate sparse-usage-map change is not installed. Every invocation edits a used Rust value, after admission and before the timer. Order rotates; Cargo uses Rust 1.77.2 and incremental compilation. Listings must contain exactly the expected 1,026 names.

Admission is unchanged: no engine sessions, a one-second quiet window, host/engine I/O stall below 5%/1%, host CPU stall below 10%, engine CPU below 0.05 CPU-seconds/second, maximum wait 60 seconds. Wcprof and diagnostic counters are off during timing. All admitted observations remain included.

Initial eight pairs, separate histories:

| Command | SDK median | Direct median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.696 s | 0.678 s | 0.126 s | 15 ms | 6/8 |
| List, 1,026 packages | 3.485 s | 3.800 s | 0.448 s | -340 ms | 2/8 |
| Grouped check, 1,026 crates | 2.034 s | 2.100 s | 0.772 s | 96 ms | 4/8 |
| Small workspace tests | 0.996 s | 1.007 s | 0.510 s | 0 ms | 4/8 |

Eight confirmation pairs, exchanged physical histories:

| Command | SDK median | Direct median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| List, 1,026 packages | 4.151 s | 3.414 s | 0.455 s | 719 ms | 6/8 |
| Grouped check, 1,026 crates | 1.951 s | 1.975 s | 0.788 s | 16 ms | 4/8 |

Eight additional pairs use **one physical source and native-cache history for both modes**. Both modes update that history through fresh edits. This removes the physical-history difference for the engine-only comparison:

| Command | SDK median | Direct median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| List, 1,026 packages | 3.843 s | 3.428 s | 0.450 s | 425 ms | 6/8 |
| Grouped check, 1,026 crates | 1.916 s | 1.946 s | 0.787 s | -33 ms | 2/8 |

The first cohort has a 9.81-second outlier and maximum host/engine I/O stalls of 36%/11%. These remain included. Confirmation maxima are 4.4%/1.1%; shared-history maxima are 2.0%/0.6%. The shared-history listing's engine-container CPU median decreases from 16.55 to 11.87 CPU-seconds; the grouped check rises from 1.81 to 1.93. These CPU counters cover the wall-time interval and exclude later background work. Neither the mixed cohorts nor the slightly slower shared-history check justify claiming an edited-compilation speedup or enabling the prototype by default.

## What the profiles change next

Four separate wcprof/CPU captures use the same physical history and fresh edits. They have zero dropped events and zero open operations. Listing captures convert about 83,000 span rows and 58,562 log rows; check captures convert about 3,700 span rows and 286 log rows. Counts include repeated forwarding/readers, not unique emitted spans. Conversion is a much larger opportunity for listing.

The ten-second listing CPU captures contain 19.93 and 12.12 CPU-seconds. A slower diagnostic check contains 3.18 CPU-seconds of Go GC work out of 6.28 sampled CPU-seconds; its elapsed time is 4.25 seconds. A faster check takes 2.18 seconds. This identifies GC as a concern, without proving it caused the elapsed-time difference. Sampled cumulative frames overlap and must not be added.

After timing and correctness checks, with no active session, a forced diagnostic collection leaves a sampled **5,327 MiB (about 5.2 GiB) and 29.3 million objects** live. Unforced and collected heap profiles are saved. This is the accumulated local benchmark engine, with no Docker memory limit; it does not establish a leak or normal-project memory use.

About 86% of retained sampled bytes originate in startup cache restoration. Persisted-list/scalar decoding accounts for about 2.24 GiB cumulatively, including detached result wrappers and cloned call descriptions. Ordered digest-index sets contribute about 268 MiB and 5.85 million tree nodes. These frames overlap. The next investigation should quantify list sizes and digest-posting cardinality, then test a compact representation while preserving ordering, identity, ownership and eviction behavior. These paths remain present on upstream main `a5c17bb7e`, fetched during this experiment. The local engine includes earlier experimental changes, so its heap size is not a measurement of that main revision. No memory fix or general speedup is claimed yet.

The [selected primitive-array codec](experiments/direct-span-forwarding/engine-overlay-source/dagql/cache_persistence_self.go) shortens encoding, while its list decoder still creates a full detached result and cloned call per scalar item. A concrete next experiment is restoring plain builtin scalar lists into their existing typed-array representation. It must preserve indexed-item identity, nullable/custom-scalar behavior, nested ownership and eviction before measuring restart memory and edited-command latency. This decoder experiment is not implemented yet.

[Samples, test logs, pressure/admission records, local harnesses, exact engine overlay sources, wcprof/CPU/heap captures and provenance](experiments/direct-span-forwarding/). The engine feature branch contains no diagnostic endpoints or switches.
