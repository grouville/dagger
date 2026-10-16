# Reuse telemetry buffers when reading batches

The standalone engine change [18f246dd1](https://github.com/grouville/dagger/commit/18f246dd1842faed187bffd637a35394951e7891) removes repeated temporary allocations when reading stored telemetry. A 512-row read improves from **619 to 424 µs**, allocating **1.61 to 0.83 MB**. Complete edited 1,026-package listings allocate **108 MB less per pair**, with lower allocations in **15/16 pairs**. Complete listing and compilation latency do not improve consistently. The four-line production addition is prepared for review; no PR is open.

## Why this path

CPU and allocation profiles of the real Rust-module listing identify telemetry conversion and transport as substantial work. A flushed allocation capture attributes about **126 MB** to `frameScanner.nextInto`, reached through `spillFile.readSince`, `SelectSpansSince` and the CLI/Cloud telemetry readers. This is the engine's active telemetry path, and the same code remains on upstream main `717589c9cc`.

`readSince` called `scanner.next()` for every row. That creates a fresh frame buffer, after which the row decoder copies strings and byte fields into their own storage. The scanner's existing reader pool was also bypassed on return. The neighboring `readIDs` implementation already reuses a payload buffer and returns its reader.

The candidate follows that existing pattern in `readSince`: keep one payload buffer for the call, use `nextInto`, and defer `scanner.release`. The decoder still owns every returned field. There is no format migration, additional lock or shared cache. Scratch storage lasts for the read call; an unusually large early frame keeps that allocation until the call returns. It is not retained between batches.

## Component measurements and correctness

Six alternating before/after pairs use fresh test processes, Go 1.26.6 and `GOMAXPROCS=8`. Fixture creation and file writes are outside the timer. Both cases improve in every pair.

| Rows | Time before → candidate | Bytes allocated before → candidate | Allocations before → candidate |
| --- | ---: | ---: | ---: |
| 1 | 10.26 → 1.96 µs | 68,775 → 3,116 | 15 → 13 |
| 512 | 619 → 424 µs | 1,614,839 → 830,824 | 5,126 → 4,613 |

The complete `engine/clientdb` race suite passes. The new ownership test reads spans with growing and shrinking frames, nil and empty fields, then reads the file again and checks the original results. It passes on main and the candidate. A deliberately altered decoder returning views into the frame fails the test, showing that it guards the assumption behind reuse. Both diagnostic engine modes also pass this test with the race detector.

## Complete Rust commands

Both modes run in the same engine binary, `8e31c79773355d11bac9854a3a641534c7733171953c483993e5888a290b6734`. A diagnostic switch selects the old or new batch reader; no such switch is included in the standalone patch. Both use Rust module `3cd40e5`, the same physical source and native cache, and identical source-snapshot, scalar-restoration and telemetry settings. The separate Protobuf experiment is not installed.

Every arm edits a Rust value and starts a fresh command process. The engine and compiler caches are warm. Telemetry stays enabled with the local decoding/null receiver. Native Cargo is Rust 1.77.2 with eight workers and incremental state outside the imported source. Wcprof is off during timing. Ordinary engine and Go collection remain enabled; no scratch snapshots or forced collection are introduced. Listings require exactly all 1,026 expected names; Cargo leaf checks require two compiler actions.

The confirmation reverses arm order. All **192 admitted measured commands** remain included, plus preparation runs, allocation/CPU counters, Go-GC counts and pressure.

| Cohort and command | Before | Candidate | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial, 1,026-crate check | 1.543 s | 1.544 s | 0.772 s | -16 ms | 4/8 |
| Confirmation, same check | 1.520 s | 1.545 s | 0.770 s | 6 ms | 4/8 |
| Initial, 130-crate direct check | 0.624 s | 0.646 s | 0.129 s | 3 ms | 5/8 |
| Confirmation, same direct check | 0.613 s | 0.616 s | 0.130 s | -2 ms | 4/8 |
| Initial, small workspace tests | 0.982 s | 0.964 s | 0.495 s | 24 ms | 4/8 |
| Confirmation, same tests | 0.977 s | 0.972 s | 0.507 s | 4 ms | 4/8 |
| Initial, expanded listing | 3.674 s | 3.630 s | 0.451 s | 39 ms | 4/8 |
| Confirmation, same listing | 3.684 s | 3.731 s | 0.443 s | -5 ms | 4/8 |

The listing's median paired allocation reduction is **103 MB** initially and **108 MB pooled**, with 15/16 pairs allocating less. Column medians change from 3.047 to 2.948 GB initially, and 3.074 to 2.957 GB in confirmation. These are allocated bytes, not a measurement of lower peak or resident memory.

Pooled median paired latency savings are 1 ms for the large check, 3 ms for the direct check, 4 ms for tests and 15 ms for listing. Only 8/16 large checks, 9/16 direct checks, 8/16 tests and 8/16 listings are faster. Listing engine CPU does not improve consistently either. The component benefit therefore supports a small allocation improvement, not a general Rust build speedup.

One initial candidate listing overlaps ordinary snapshot collection and remains included. Maximum host I/O pressure is 21% in the initial direct control; listing CPU pressure reaches about 28%. Admission cannot guarantee a quiet complete command. GC and pressure observations are retained rather than used to discard samples.

All six retained native histories pass with the candidate enabled: **130/130, 1,026/1,026 and 6/6 twice**. The verifier first compiles the current input explicitly because a final Cargo or listing edit may not have been compiled by Dagger, then requires complete reuse. Unchanged calls establish correctness only. Rust artifacts and incremental state remain native immutable snapshots.

## Diagnostics and remaining work

Four separate captures cover both modes for a large edited check and listing. They include engine/CLI CPU, CLI runtime traces, wcprof and bounded goroutine snapshots. Every final wcprof capture has zero dropped events and open operations. Their durations do not enter the benchmark cohorts.

The candidate listing still publishes **13,677 results**. Wcprof assigns about **760 ms** of its reported 2.59-second critical path to result publication, and 601 ms to artifact items. Its five-second CPU window contains 16.85 CPU-seconds: stored protobuf-JSON decoding accounts for about 23% cumulatively and SDK span conversion for about 22%. Those frames overlap and include background work. The buffer change leaves those larger costs in place.

The large-check captures also contain source-import variation: 423 ms before versus 191 ms after, while compiler orchestration takes 702 versus 738 ms. This locates variation in those diagnostic captures; it does not attribute it to the telemetry buffer or explain each unprofiled sample.

A separate dependency screen compares [Protobuf's field ordering](https://raw.githubusercontent.com/protocolbuffers/protobuf-go/master/internal/order/range.go). A typed generic sort reduces small-message allocations but slows the 32- and 128-field controls by roughly 10%, so it is rejected in that form. Handling zero, one and two fields directly preserves the general sort and reduces the sample encoder from 20.45 to 19.07 µs and 170 to 125 allocations. Dependency JSON/text/binary codec and Dagger client-database race suites pass. This remains a component experiment with no complete-command measurement and is not a ready proposal.

The allocation investigation preserves an initial misleading capture: unforced heap profiles can lag collection cycles and showed mostly earlier cleanup. Separate diagnostic captures flush two GC cycles before and after the command and retain every profile. Their forced-GC timings are excluded from latency claims.

Installation preserves the existing engine volume. The old engine exits cleanly after 157.6 seconds; its final stacks wait in `unix.Syncfs`, before the new code is installed. The first measurement attempt records 90 seconds of failed quiet admission and runs no commands. A monitor later observes three quiet windows and starts the unchanged driver. All controls are restored and no clients remain active after validation.

[Raw measurements, sources, scripts, failures and profiles](experiments/telemetry-spill-batch-buffers/) · [Prepared PR description](upstream-prs/telemetry-spill-batch-buffers.md).
