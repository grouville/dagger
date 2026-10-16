# Parallel fingerprint scan: leave it disabled

The bounded parallel scan improves the local 1,026-crate fingerprint benchmark from **55.5 to 37.0 ms** in all six pairs, but does not establish a consistent complete-command gain. A listing-only confirmation reverses the initial listing result. Keep the serial implementation selected; the added concurrency is not justified by these measurements.

## Experiment

The selected native-discovery module remains `da1ae47b6c96a3117de303b7584d028e35166530`, with the same compiler sources and cache keys. CPU profiling places about 50 of 70 ms of fingerprint CPU in filesystem calls, principally metadata reads. The candidate processes up to 128 entries at a time with at most eight workers, then hashes their results in the original lexical order. Matcher evaluation remains on the traversal goroutine; each worker owns its contents buffer. No persistent memo or new input exclusion is introduced.

The candidate retains the v1 digest format, permissions, ownership, xattrs and non-ignored contents. Compatibility tests compare exact digest bytes with a frozen copy of the selected implementation across multiple batches, ignore/reinclude patterns, non-ASCII and control characters in paths, metadata, rejected directories and symlinks. Repeated canceled calls return without hanging. The full contenthash race suite and the diagnostic serial/parallel switch tests pass.

Six fresh-process component pairs alternate order. Go 1.26.6, `GOMAXPROCS=8`, 150 ms per case; fixture creation is outside the timer.

| Crates | Serial | Parallel | Allocated bytes, serial → parallel | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 128 | 7.02 ms | 4.99 ms | 1.31 → 1.67 MB | 6/6 |
| 1,026 | 55.49 ms | 36.98 ms | 10.19 → 11.27 MB | 6/6 |

The large case adds about 1.08 MB of allocations. The temporary entry batch is bounded; eight content buffers can coexist. The candidate adds a worker pool, batch synchronization and ordered error handling to a previously serial scan.

## Complete edited commands

Both arms use the same diagnostic engine binary and the same native Rust module. Only fingerprint concurrency varies. Engine and compiler caches are warm; every command starts a fresh CLI process after an edit to a used Rust value. Telemetry remains enabled. Workload-specific randomized orders balance which Dagger arm runs first. Wcprof is off during timing. Ordinary collection remains enabled, and no GC is forced. All admitted observations, including background work and pressure, are retained.

| Command, eight pairs | Serial median | Parallel median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Collection check, 1,026 crates | 1.356 s | 1.402 s | 0.771 s | −45 ms | 3/8 |
| Direct check, 130 crates | 0.612 s | 0.634 s | 0.118 s | −38 ms | 1/8 |
| Small workspace tests | 0.955 s | 0.958 s | 0.502 s | 20 ms | 5/8 |
| Expanded listing, 1,026 packages | 2.898 s | 2.777 s | 0.440 s | 99 ms | 7/8 |
| Listing-only confirmation | 2.794 s | 2.785 s | 0.445 s | −61 ms | 3/8 |

Column medians and median paired differences differ. The first listing series suggested a gain; the confirmation does not support selecting it. Listing engine CPU is about 13.11 → 12.49 CPU-seconds initially and 12.84 → 12.81 in confirmation. Confirmation allocations increase from 2.254 to 2.298 GB median. These whole-process measurements include more than the fingerprint function, so they do not attribute each difference to it.

The direct check never invokes the fingerprint. Its timing shift is a control demonstrating variation outside the changed path, not a measured fingerprint regression. The initial mixed cohort has host I/O pressure up to 63% in the large-check controls and 34% in direct controls. Listing CPU pressure reaches about 30%; confirmation reaches 33% CPU and 2.4% I/O. No measured command overlaps recorded snapshot collection, although a Cargo control includes background engine CPU. Admission does not guarantee quiet conditions throughout a command.

## Profiles and cache preservation

Six separate diagnostic captures have zero dropped events and open operations. The large-check fingerprint takes **51.7 → 46.1 ms**, while its package-discovery scope is **122.6 → 123.7 ms**. In the listing, the fingerprint takes **75.8 → 47.5 ms** and discovery **152.3 → 130.1 ms**. Both direct captures have zero fingerprint calls. The execution and publication counts remain unchanged. Compiler and GC variation is much larger than the small large-check fingerprint difference; instrumented durations are not added to the timing cohorts.

The owned engine exits cleanly in 54.28 seconds before the new binary is installed, preserving its volume. Shutdown timings are outside the command comparison. All six native histories remain fully reusable after preparing their current inputs: **130/130**, **1,026/1,026** and **6/6**, twice each. These unchanged inspections verify retention only.

The diagnostic engine is now `f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721`; its serial path is the previous fingerprint implementation. Parallel scanning remains disabled. Selected direct dimension-key reads remain enabled; profiling and temporary modes are off, ordinary snapshot collection is enabled, and no clients remain active. [SELECTED_BASELINE.json](SELECTED_BASELINE.json) records the current diagnostic binary and source manifest.

The next change should remove more repeated work, rather than depend on this scan's small local gain. Source import still takes roughly 200 ms in the large fixture. Reusing metadata would need a proof that every fingerprint input is covered; dropping metadata or treating a content digest as equivalent without that proof would change correctness. Registry dependencies, build scripts, procedural macros and remote automatic discovery remain unfinished parts of the broader native Rust-cache goal.

[Sources, raw timings, controls, profiles and validation](experiments/parallel-fingerprint/). No upstream proposal is added and no PR is opened.
