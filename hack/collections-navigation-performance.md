# Collections: navigation, generation and command completion

The current warm, Cloud-connected medians are **615 ms for `dagger ws ls`**, **2.332 s for `dagger list -a`**, and **2.033 s for `dagger generate -l`** on greetings-api. A small independent generator writes its file in **296 ms warm / 379 ms after a new input edit**, but the CLI exits at **726 / 925 ms**. The target remains 500 ms for the whole command, not just file availability.

These measurements use the retained experimental SDK stack described in the [lazy-source report](collections-lazy-source-performance.md). They are not measurements of an ordinary upstream build or Kyle's machine. All commands use the normal production Cloud endpoint and login. No relay or local receiver is involved.

## Warm user commands

Three ordinary repetitions per flow, fresh CLI processes. Five local correctness/warmup commands and five separate instrumented wcprof commands are excluded from the medians.

| Command and fixture | Samples, ms | Median CLI exit, ms | Median file ready, ms |
| --- | --- | ---: | ---: |
| `dagger ws ls`, greetings-api | 633 / 547 / 615 | 615 | — |
| `dagger list -a`, greetings-api | 2332 / 2346 / 2320 | 2332 | — |
| `dagger generate -l`, greetings-api | 2119 / 2033 / 1733 | 2033 | — |
| `dagger -y generate`, native fixture | 730 / 726 / 722 | 726 | 296 |
| New input edit → `dagger -y generate`, native fixture | 925 / 904 / 1035 | 925 | 379 |

On this branch `ws ls` lists workspace files; `list -a` lists artifacts. There is no `ws list` subcommand. The generator fixture uses an ordinary Dang `@generate` function returning a Changeset. It copies current input bytes into a generated file. This validates the generation/apply/write path, not the performance of the Go or TypeScript SDK's code generator.

Every generation starts with the destination removed. Every edit uses previously unseen input bytes. File bytes are checked against the current input, with readiness observed by five-millisecond polling. CLI completion uses blocking waitpid. All 25 commands passed their output checks; both fixtures were restored. The local warmups are not a paired estimate of the production-versus-local difference.

## First use on a new Dagger volume

Each command gets its own new engine and empty Dagger volume, with no preliminary CLI warmup. The engine image and SDK blobs are already available; provisioning and engine readiness are timed separately. This is not a cold host page cache, first image download, or a measurement including automatic Docker engine startup.

| Flow | First command, s | Next two commands, s | Engine readiness excluded, s |
| --- | ---: | --- | ---: |
| `ws ls` | 2.685 | 0.599 / 0.606 | 0.867 |
| `list -a` | 26.747 | 2.431 / 2.639 | 0.923 |

There is one ordinary cold sample per flow, not a distribution. The first workspace listing writes about 0.32 MB in its engine cgroup; the first artifact listing writes 1.21 GB. Host I/O pressure increments are about 1.5 / 244 ms. These counters include background work and do not by themselves explain the cold latency.

Two further fresh volumes supply separate cold diagnostics. The profiled artifact command takes 25.552 s, with 24.038 s of engine-query union and about 18.236 s covered by runtime processes. Image-layer application occupies about 4.193 s; these intervals overlap. The corresponding profiled workspace command takes 1.123 s: its command callback is 473 ms, but recorded `session.serveQuery` is only 39 ms. Roughly 434 ms precedes that instrumentation boundary. The profile therefore points to an initialization gap to instrument, not 434 ms of directory scanning. These independent profiled samples are excluded from the ordinary table.

## Where the command time goes

The diagnostic CLI records fixed phase names and numeric HTTP timing/count data, without request bodies, credentials, URLs or trace IDs. It preserves the same transports, root-span lifetime, cleanup order and joins. Each row below is one separately instrumented/profiled command, not an additional ordinary sample.

| Flow | CLI exit, ms | Engine query union, ms | Engine shutdown HTTP, ms | CLI telemetry close, ms |
| --- | ---: | ---: | ---: | ---: |
| Workspace files | 591 | 28 | 160 | 242 |
| Artifacts | 2337 | 1391 | 609 | 134 |
| Generator listing | 1632 | 632 | 668 | 149 |
| Generate, warm | 836 | 138 | 370 | 153 |
| Generate, new input | 833 | 223 | 240 | 156 |

Workspace navigation performs little actual query work in its profile. Artifact discovery still performs substantial module and collection work. Both then pay for session closure and final CLI telemetry. The query union excludes some startup work, and nested phases must not be summed as independent savings.

A separate 16-command Cloud investigation compares the existing engine control and the source-aware lazy-copy engine. Four ordinary warm listing pairs give **2.024 / 2.033 s** medians: no meaningful warm improvement from the copy change in this series. Its earlier fresh-edit benefit remains separate.

The diagnostic pair has essentially identical command callbacks, **1340.7 / 1339.6 ms**, followed by **325.6 / 1098.8 ms** in the engine shutdown HTTP request. Existing engine logs identify **308.4 / 1082.5 ms** specifically in `flush session Cloud telemetry`. Workspace-lock flush and service shutdown are below 0.01 ms; local telemetry flushing is about 4 ms. The extra time is therefore in that Cloud drain phase, not in the artifact-discovery work or a second local stream drain.

This is not a stable 774 ms regression: the four ordinary calls' Cloud-drain medians are **396 / 365 ms**. The phase includes concurrent Cloud trace/log drains and closing the token-refresh gate; it does not distinguish the responsible engine HTTP request or server processing from network latency. CLI-only HTTP hooks cannot supply that missing attribution. Later final session teardown occurs after CLI exit in all 14 recorded expanded-listing sessions.

## Generic change committed in this iteration

Commit `21939e4ff9` removes `MeterProvider.ForceFlush` immediately before `MeterProvider.Shutdown` during client runtime reclamation. The configured OTel PeriodicReader already performs its final collection/export during Shutdown. The old sequence collected the same final observable value twice, for both local and Cloud readers.

The unchanged baseline fails the real-reader assertions with `[42, 42]` instead of `[42]`, and `[41, 42, 42]` instead of `[41, 42]` after a genuine earlier explicit flush. The fix preserves that earlier flush, the final updated value, cancellation, both readers' cleanup, error propagation and the metrics-before-traces shutdown order. Six new tests plus eight existing lifecycle/Cloud-metric tests pass, including race detection.

This is a demonstrated reduction in callbacks, local exports and queued Cloud collections. **The timing tables above precede this engine change and do not measure its latency benefit.** Metric HTTP export is asynchronous; removing duplicate collections must not be described as removing a foreground network round trip.

Ending the root trace early was rejected: the UI treats root completion as trace completion and marks still-running children canceled. Returning while a CLI goroutine keeps exporting would also lose delivery when the process exits. Faster completion must preserve these contracts or introduce a separately validated durable handoff.

## Measurement boundary and next work

The CLI control/diagnostic pair is built from `341595f376`; the only diagnostic dependency adjustment is a byte-identical copy of the pinned otel-go module so Go accepts the source overlay. Both binaries use that same copy. The engine hashes and experimental SDK inputs match the preceding source-aware-copy experiment. Counters and profile dumps are outside ordinary timing intervals, and builds/tests do not overlap command measurements.

The navigation/exit investigation and cold follow-up contain 55 validated commands: nine local setup/correctness calls and 46 production Cloud calls. Eleven wcprof captures have no open or dropped operations. A first minimal-core diagnostic also shows a separate approximately one-second pre-run outlier; it is retained rather than folded into a supposed fixed discovery cost.

The warm `list -a` profile executes static discovery once (662 ms) and expansion once (694 ms). Four Go metadata-registration processes occupy 301 ms of union time; two backend function invocations are separate. Existing Go SDK static-metadata work can help warm registration as well as cold compilation, but those process intervals overlap Git and cannot be subtracted as a guaranteed saving. Just 16 ms remains between the last module load and catalog completion, so its final tree walk is not the main bottleneck.

The subsequent [44-command span-serialization comparison](collections-qa-performance-data/span-runtime/report.md) is complete. Listing medians improve from 2.280 to 2.129 s, but warm native generation slows from 729 to 824 ms and loses all three pairs. The candidate remains isolated. The [bootstrap and completion follow-up](collections-bootstrap-performance.md) now identifies eager core metadata before the query boundary, measures lazy materialization on ordinary commands, and isolates same-binary completion variability. It also records the actual Cloud requests behind the engine drain. The 500 ms target remains unmet for complete Cloud-connected commands. A cached workload still needs correct source invalidation, authority checks and final telemetry delivery.

The [evidence archive](collections-qa-performance-data/navigation/README.md) contains the exact samples, numeric phase/HTTP counters, source and input hashes, drivers, diagnostic overlays and validation results. Raw Cloud output, engine logs, profiles, credentials and private receiver code are excluded.
