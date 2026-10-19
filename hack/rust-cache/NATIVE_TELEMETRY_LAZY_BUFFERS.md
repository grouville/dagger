# Allocate telemetry spill buffers when needed

A small engine candidate reduces allocation after a test edit, while complete-command latency remains modest and mixed:

| Complete listing, fixed eight-pair follow-up | Before | Lazy buffers | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 7.15 s | 7.00 s | 6/8 |
| Ordinary-source edit | 4.15 s | 4.19 s | 3/8 |

| Engine work, same cohorts | Test edit, before → after | Ordinary edit, before → after |
| --- | ---: | ---: |
| Allocated bytes, decimal GB | 6.361 → 5.614 | 1.927 → 1.922 |
| CPU-seconds | 30.31 → 29.40 | 11.01 → 11.14 |

Both modes use Go module `720a525`, the same development engine binary and the same selected settings. A fresh CLI receives a real edit on a warm engine. Timings include normal telemetry, ordinary GC, output, final flushing and successful cleanup. Each cohort completes test addition and removal before its measured pairs. All 64 real-repository timing commands across the initial screen and follow-ups return the correct ordered rows. The stable listing has 4,398 rows. These are separate cohorts, without pooling or additive savings; current cold, released-engine and Rust latency effects are unmeasured.

The initial four-pair screen measured test edits **6.91 → 6.72 s**, faster in 3/4 pairs, and ordinary edits **4.08 → 4.17 s**, faster in 1/4. The fixed follow-ups test that source slowdown and variable test latency. The median paired saving is 116 ms for test edits and −18 ms for ordinary-source edits. All samples, including slower runs and the large baseline outlier, remain in the evidence. This is primarily an allocation proposal, not a three-second breakthrough. Its experimental mode is restored to off.

The earlier serialization hypothesis did not justify an implementation: recursive `Object.Bindings` accounts for only 2.50 MB in the preceding 5,076.57 MB allocation sample. New combined CPU, allocation, mutex and wcprof captures instead identify telemetry-store buffers among the major allocation callers. Allocation profiles can lag by up to two natural GC cycles, as documented by Go 1.26.6 `runtime.MemProfile`; use the paired `TotalAlloc` counter for command-level savings rather than treating sampled deltas as exact per-command attribution. No GC was forced. Mutex waiting is aggregate across concurrent callers, not elapsed time saved; the already-rejected parallel-admission mode stays off.

Opening a spill file currently reserves a 64 KiB reader for recovery and a 64 KiB writer, including for empty files. The candidate recognizes a validated header-only file without allocating a scanner and creates its writer on the first valid nonempty append. Files are still opened, headers validated, populated stores recovered and writes flushed before committed offsets are published. Closing an unused store still closes its descriptor and reports errors. The existing single spiller owns the writer; no new lock, shared pool, asynchronous flushing, storage format or public API is added. Private module state and all collection logic remain.

Standalone component comparisons on current main `ff0b029`, four alternating fresh-process pairs with Go 1.26.6 and eight available processors:

| Operation | Before | Lazy buffers | Allocated bytes, before → after |
| --- | ---: | ---: | ---: |
| Open/close empty | 25.10 µs | 7.54 µs | 131,920 → 536 |
| Open/close one stored row | 24.34 µs | 16.34 µs | 131,968 → 66,316 |
| Open/close 256 stored rows | 48.70 µs | 38.22 µs | 136,046 → 70,394 |
| Open, first append, close | 32.00 µs | 24.23 µs | 132,050 → 66,305 |

The first-write control includes resetting the same file to its header in both modes, then opening it, appending a real row, flushing and closing. It checks the cost where the delayed writer is actually needed, rather than timing open alone. The new lifecycle test verifies empty close, reopen, first append and recovery through observable rows. Existing corruption, cancellation, rollback, stream, concurrency and registry tests pass under race detection with both standalone implementations. The exact diagnostic engine's clientdb race suite also passes.

All 27 Go check invocations and 28 corrected Rust/native-cache cases have their expected outcomes. They exercise selected execution, required failures, edited/restored sources and native compilation-action hits. Lossless before/after captures retain all 800 authored getters and 799 unchanged discoveries after a test edit; ordinary-source captures retain all getter and discovery hits. SDK request counts stay at 1,415 and 493. Telemetry and final cleanup stay in the pipeline.

The first Rust gate failed in its harness: replacing a port number also altered a substring in the image digest. The source digest was restored and address replacements were narrowed to include their colon. That failed attempt and correction are retained. The completed engine build and Go checks were not rerun; only the failed gate and subsequent phases resumed. No production-code failure is inferred from that attempt.

[Standalone source](https://github.com/grouville/dagger/commit/38b2608e824446b8abd895582a4b3d12fdecb850) is based directly on verified upstream main `ff0b029a4d270a651b9a8c7286babc79089066e4`. The [PR description](PR_TELEMETRY_LAZY_BUFFERS.md) is prepared for review; no PR is open. [Evidence](experiments/telemetry-lazy-buffers/) includes all attempts, benchmarks, timings, race checks, six lossless captures and exact engine-input deltas. All twelve engines and cache volumes remain intact, workspaces are restored, and capture switches are off; the lazy buffer experiment is restored to off. The broader three-second collection and native Rust-cache performance goals remain unfinished.
