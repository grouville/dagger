# Collections performance: allocation matrix and novel-edit diagnosis

The matched engine matrix completed **279 commands with all expected outcomes**: 276 successful exits and three deliberate failing checks, followed by successful recovery. Interface-signature reuse and the Dang clone fast path reduced allocations in the main listing/check flows, but this run does **not** establish a broad end-to-end wall-time improvement. Separate profiles of previously unseen source edits expose a larger, concrete cost: an approximately eight-second Go build during listing. The separate [source-aware `withFile` comparison](collections-lazy-source-performance.md) confirms and fixes that cause. Its timings are kept separate from this allocation matrix.

## What was compared

Three engines were built from the same source HEAD `74d8b41823f06602ccfbf8fa7f58f1a1c8b7ada5`, image, SDK blobs and fixture pins. The variants are the common control, control plus lazy per-pass interface signatures, and that candidate plus the Dang scalar/nil clone fast path. The common stack already includes earlier experimental SDK/syntax work; this is not a comparison with upstream main or Kyle's laptop.

The workload uses Kyle's greetings fixture for core API, expanded/filtered check listing and actual selected Go-test execution. A small native fixture additionally exercises ordinary module calls, checks, generation, service readiness/shutdown and real host-file export. Each timed interval starts before a fresh CLI process and ends at blocking waitpid. Setup, counters, pauses and profiler collection are outside ordinary timing intervals. The local matrix has Cloud/OTLP export disabled; it cannot be substituted for normal Cloud-connected timing.

There are 93 commands per engine: first listing, nine warmups, six repetitions of nine warm flows, three repetitions of source/test/input edits, deliberate failure/recovery, and three separate profiles. Nine profile rows are excluded from ordinary performance summaries. No GC was forced. All original fixture files were restored, with no new fixture files left behind.

## Warm CLI completion

Medians in seconds, six repetitions per engine/flow. Samples and paired deltas are retained separately.

| Flow | Control | Interface | Interface + Dang |
| --- | ---: | ---: | ---: |
| Core `api call version` | 0.367 | 0.365 | 0.369 |
| Expanded `check -l --all` | 1.535 | 1.504 | 1.532 |
| Filtered test listing | 1.987 | 1.947 | 1.968 |
| Selected Go test execution | 1.523 | 1.518 | 1.531 |
| Native module call | 0.476 | 0.468 | 0.459 |
| Native check | 0.290 | 0.283 | 0.295 |
| Native generate | 0.344 | 0.368 | 0.347 |
| Native up, through cancellation/exit | 0.540 | 0.571 | 0.583 |
| Real file export | 0.378 | 0.407 | 0.391 |

The expanded-listing combined median moves by only about −3 ms; selected execution is about +8 ms. Paired samples have positive and negative differences. These results support keeping the allocation work as an independently useful optimization, not advertising a general command-speed improvement.

For `up`, the visible readiness boundary is different from CLI completion: median HTTP readiness is 0.432 / 0.467 / 0.467 seconds. The driver then sends its own SIGINT, waits for CLI completion, and verifies the tunnel closes. File visibility is a five-millisecond-poll observation of expected bytes, not the exact write timestamp; destinations are removed before every measured export/generate so these are real writes.

## Allocation evidence

Median process-wide engine TotalAlloc deltas in decimal MB, measured around each command. They include concurrent/background engine work and are not exclusive allocations of one resolver.

| Warm flow | Control MB | Interface MB | Interface + Dang MB |
| --- | ---: | ---: | ---: |
| Expanded listing | 701.21 | 670.91 | 665.77 |
| Filtered listing | 621.66 | 599.19 | 589.84 |
| Selected Go test | 347.39 | 319.16 | 317.64 |

The combined reductions are about 5.1%, 5.1% and 8.6% for these three flows. Allocation does not decline in every synthetic flow, and the wall-time table does not justify converting these percentages into latency promises.

The separate library microbenchmarks explain the intended mechanism:

- Lazy interface signatures reduce dirty reconciliation time by about 31–37% and bytes by 67–76% at the tested sizes. The all-permanent case is effectively unchanged; the mostly-permanent case adds two allocations/400 bytes.
- The Dang scalar/nil clone fast path reduces real cached-parse cases by about 14–19% and bytes by 8–9%; allocation counts drop about 40%. Mutable tree isolation and rewritten source locations remain covered by tests. This is scoped to the existing experimental reflection-based syntax cache, not proof that a production syntax-cache design is complete.

These percentages describe those algorithms. Their numeric summaries are archived, and the full CLI matrix above is the subsequent end-to-end check.

## Edits and first-seen source states

Three repetitions per engine; seconds through full CLI exit:

| Greetings edit and next command | Control | Interface | Interface + Dang |
| --- | ---: | ---: | ---: |
| Rename selected test → expanded listing | 9.860 | 10.124 | 10.028 |
| Main-file comment → expanded listing | 9.860 | 9.841 | 9.926 |
| Different main-file comment → execute selected test directly | 10.903 | 10.825 | 10.919 |

The direct-check edit has different bytes from the preceding listing edit, so the exact changed input is not warmed by a preliminary listing. All variants see identical bytes per case. The matrix starts each engine on a fresh Dagger volume and uses deterministic edit strings within that run.

Historical results from recurring edits and the new nonce-based experiments answer different questions. Reapplying an earlier source state can legitimately reuse Dagger's content-addressed results; a first-seen state measures invalidation work for new content. Some older drivers reused a finite set of edit strings across trials, but **this review has not established that any specific older sample was contaminated by an unintended cache hit**. Keep the original figures with their recorded cache/source boundaries rather than retroactively relabeling them.

To make the new diagnosis unambiguous, the two subsequent profiles use unique time-based nonces, different bytes for listing and execution, no preliminary command on either edited input, and recorded source hashes. They run on the warmed combined engine. These are separate profiled diagnostics, not extra ordinary timing repetitions.

## What the fresh-edit profiles prove

| Diagnostic | Profiled CLI time | Actual Go-build interval | Operations | Open / dropped |
| --- | ---: | ---: | ---: | ---: |
| New comment → expanded listing | 9.733 s | 8.140 s | 20,923 | 0 / 0 |
| New comment → selected test execution | 10.757 s | 8.095 s | 8,640 | 0 / 0 |

All recorded operations fall inside the corresponding CLI wall interval. The ancestry is explicit:

```
Container.withFile
  → Directory.file
    → Directory.withFile
      → Container.file
        → Container.withExec
          → go build
```

In the listing case, materializing the backend binary occurs while constructing the base container; discovering the checks does not inherently require running that backend. The source-aware `withFile` prototype aims to defer the source's materialization until an actual consumer needs it. Correctness still requires the binary and bound API to materialize when execution needs them.

The wcprof simulator's predicted baseline drifts by +85.9% and +77.8% in these two captures. Its what-if savings are therefore unsuitable as quantitative predictions here. The report uses measured operation duration, actual parent relationships and complete capture bounds. Nested runtime/build durations overlap and must not be added together.

## First-call and disk variability

Each engine's first expanded listing used a fresh task-owned Dagger volume. Host page/image caches were not cleared. There is one sample per variant in fixed setup order, so these are diagnostics rather than a cold-performance distribution.

| Variant | Engine start/readiness/hash check | First listing CLI | Engine writes | Host I/O PSI `some` delta |
| --- | ---: | ---: | ---: | ---: |
| Control | 1.020 s | 24.985 s | 756 MB | 0.217 s |
| Interface | 10.013 s | 34.179 s | 643 MB | 7.104 s |
| Interface + Dang | 1.213 s | 24.532 s | 1,408 MB | 0.203 s |

The slow interface first call coincides with much larger host I/O stall time; its engine CPU counter is similar to the others (90.2 versus 87.5 CPU-seconds). That supports further disk investigation, but host-wide PSI does not assign every stalled millisecond to this command. These data do not prove the interface patch caused the cold difference or that distributed caching would remove it. The minimum observed free space was about 817.9 GB, and maximum measured writes for one command were 1.41 GB; no per-command storage guard fired.

## Evidence

The [numeric archive](collections-qa-performance-data/lazy-source/matrix/) contains the samples, paired deltas, input/build hashes, restoration proof and profile aggregates. The source-aware copy fix and Cloud-connected measurements are reported [separately](collections-lazy-source-performance.md).
