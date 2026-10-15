# Snapshot completion notifications: no command speedup established

The [isolated engine experiment](https://github.com/grouville/dagger/commit/154acf737) avoids snapshot-completion notifications before a cache has registered its first imported result. It removes a measured source of graph-lock contention, but the complete edited Rust commands do not get consistently faster. Keep it as an experiment, outside the selected implementation. No PR is open.

## Why the notification can be skipped

Early snapshot sharing lets an imported result receive a completed local equivalent. Without an imported result, there is no receiver. Previously, completing a result still took the global graph lock, enumerated its output classes and checked their members before discovering that there was no sharing work.

The patch records the first import with an atomic flag. Before that flag is set, completion returns without the graph lock. Registration and in-place replacement both set the flag; restoring an imported result does too. The flag never resets, so collection, replacement and failed imports can only cause unnecessary notifications, not suppress a required one. After the first import, notification behavior is unchanged. This deliberately does not optimize a cache that has already received remote results.

The first-import merge already queues its imported rows and changed classes while holding the graph lock. It therefore covers a completion that returned just before that import became visible. No snapshot ownership, result identity, persistence format or compiler state changes.

## Correctness and actual use

The new regression holds the graph lock and verifies that completing a result without imports does not wait for it. It fails on unpatched main and passes with the patch. Existing sharing tests cover actual import, replacement, restored imported rows, close and cancellation. The complete `./dagql` package passes under the race detector in 64.79 seconds.

A real edited `dagger check --list --all rust:packages/check` prints the exact 1,026-package set. All 13,845 completion notifications take the no-import path. Thus the absence of a command speedup is not explained by an unused fast path.

After a clean restart of the same owned engine, with its volume preserved, both histories retain their compiled results: 130/130 actions in the medium workspace and 6/6 in the test workspace. The unchanged large history reuses 1,026/1,026. The history edited for the notification probe reuses 1,024/1,026, rebuilding exactly the two affected actions. These checks verify cache behavior, not unchanged-command performance.

## Complete edited commands

Eight pairs use the same warm engine and binary, toggling only the notification path outside the timer. Both arms use Rust module `30600fd`, the buffered CLI and the selected attribute-array decoder. Telemetry remains enabled; wcprof and diagnostic counters are disabled. Immutable source-import seeds are off. Each invocation edits a used Rust value. Order rotates and all observations are retained, including slow samples. Admission requires an idle engine and a one-second low-I/O window before each invocation. Cargo uses Rust 1.77.2 with incremental compilation.

| Command | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Check, 130 crates | 0.690 s | 0.711 s | 0.128 s | −11 ms | 3/8 |
| List, 1,026 packages | 5.400 s | 5.399 s | 0.429 s | −43 ms | 3/8 |
| Grouped check, 1,026 crates | 2.350 s | 2.335 s | 0.796 s | 13 ms | 5/8 |
| Small workspace tests | 1.032 s | 1.019 s | 0.501 s | −10 ms | 3/8 |

The difference between arm medians is not the median of paired differences. Neither the small apparent check improvement nor the listing's unchanged median establishes a useful gain. A crossover is not selected from these results.

## What the complete profiles change

Two separate diagnostic listings capture the whole command with wcprof, an engine CPU profile and a 30-second runtime trace. Both print the exact package set; neither wcprof capture drops events or leaves operations open. The commands take 5.71 and 5.78 seconds under profiling. These are diagnostic observations, not additional benchmark pairs.

The fast path removes notification waits, but other graph-lock waits remain. Publication itself accounts for only 0.58 of 24.29 sampled CPU seconds in the candidate capture. Protobuf JSON decoding accounts for 7.27 CPU seconds; span conversion includes 5.94 and log conversion 3.05 seconds. These cumulative figures overlap and sum concurrent work, not command latency. Runtime traces also show contention in the profiler's string table, so the instrumented lock totals cannot be treated as normal-command savings.

Wcprof still observes 3,078 calls each for dimension-key reads and 1,026 each for artifact items, descriptions and URIs. Reducing repeated metadata decoding or the number of necessary result publications is a better next experiment than treating a waiting lock as its own cause. The earlier per-batch resource/scope decoder had no measurable benefit on the small module; this larger workload provides a new reason to measure it, rather than assuming that old microbenchmark transfers.

Evidence and local harnesses: [snapshot-notifications](experiments/snapshot-notifications/). Raw runtime traces remain in `/tmp/rust-cache-sipsma-review/snapshot-publication-profile`. The standalone commit starts from main `6de2877bc`, fetched again after the measurements. The native Rust backend remains experimental, with registry dependencies, general build scripts, procedural macros and remote automatic state discovery still unfinished.
