The metadata improvement remains visible before shutdown, while later work absorbs much of it with Cloud enabled.

The completed run uses one identical engine binary (7226c5d1a5a0…) and alternates two ordinary CLIs: baseline f10947c2788e… and JSON metadata 2d8cce9bcc42…. Both use the old log SDK replacement v0.16.0. There are three warm pairs per flow/configuration. All 32 core/module calls passed their exact-output checks. The subsequent baseline collection-get probe failed, so that run does not establish collection API correctness. The engine binary and fixtures were restored, the task engine stopped, and the volume retained. This audit made zero CLI or Cloud calls.

| Complete CLI median | Original metadata | JSON metadata |
| --- | ---: | ---: |
| Local-only core version | 377 ms | 227 ms |
| Local-only module read | 443 ms | 304 ms |
| Cloud core version | 628 ms | 591 ms |
| Cloud module read | 823 ms | 817 ms |

Local paired improvements are 143 ms for core and 140 ms for module. Cloud differences of medians are 37 ms and 6 ms; median paired improvements are 37 ms and 16 ms. These are different statistics and should not be interchanged. Three pairs and separate local/Cloud blocks do not establish stable distributions or a precise universal Cloud overhead.

Read-only extraction of the stopped engine's retained logs finds all 33 main-client shutdown records, including the failed collection probe. Only fixed labels and numeric durations are exported. For each command, the log's main-shutdown completion timestamp and duration divide the CLI interval into an approximate pre-handler interval, the recorded engine shutdown handler, and the interval between that log and CLI exit. Docker log timestamps are completion observations; these are not separately instrumented CLI phase boundaries.

| Cloud pair | CLI delta | Before main shutdown delta | Main shutdown delta | After shutdown log to exit delta |
| --- | ---: | ---: | ---: | ---: |
| Core 0 | -132 ms | -93 ms | -122 ms | +84 ms |
| Core 1 | +0 ms | -127 ms | +0 ms | +127 ms |
| Core 2 | -37 ms | -138 ms | -6 ms | +107 ms |
| Module 0 | -97 ms | -154 ms | +80 ms | -23 ms |
| Module 1 | +2 ms | -117 ms | +97 ms | +22 ms |
| Module 2 | -16 ms | -113 ms | +50 ms | +47 ms |

Negative values favor JSON. Each row's components reconcile to its total delta, apart from rounding. Do not add medians of different components: their median may select different rows.

The core candidate reaches shutdown earlier in every pair, but has a longer remaining CLI interval in every pair. The module candidate also reaches shutdown earlier in every pair; its longer engine shutdown is almost entirely the recorded Cloud-flush phase: +80/+97/+50 ms. That phase includes export drains and the token-refresh gate. It does not establish HTTP RTT, queue time, server time, batch amplification, or retry behavior. The post-handler interval also includes response/transport cleanup, frontend work, CLI telemetry and process shutdown; it cannot all be called an HTTP export without phase hooks.

Resource observations support a reduction in local work, without isolating metadata CPU: engine CPU medians for local core/module are 1.106→0.392 CPU-seconds and 0.821→0.262 CPU-seconds; Cloud core/module are 0.728→0.127 and 0.826→0.340 CPU-seconds. These pre/post cgroup counter brackets are wider than CLI timing and include background work. The 12 Cloud-warm rows record zero engine write bytes. This is not evidence that disk caused their different tails. Coarse ordinary TUI output also reports type loading at 0.2 s baseline versus 0.1 s candidate for Cloud core, but that rounded display is not the attribution source.

The source makes joined CLI telemetry a credible next experiment. withEngine registers telemetry cleanup before session cleanup; reverse cleanup order closes the engine session first. initEngineTelemetry's cleanup then emits both stdio EOF records, ends the root span, and calls telemetry.Close. In the pinned otel-go implementation, Close drains traces, then logs, then metrics. These final records are produced after the session-close boundary. Faster metadata changes when they arrive relative to the existing 100 ms live exporter intervals and any outstanding requests. This is a mechanism consistent with the observations, not proof of which queue/request caused these samples. There is no evidence of an intentional fixed 100 ms sleep here.

The prepared cli-log-overlap-v3 experiment is now relevant to the measured critical path: promptly ForceFlush queued logs concurrently with trace Shutdown, then join before logger Shutdown, retaining late trace cleanup logs and the existing trace/log/metric terminal order. Test dependency upgrade separately from overlap. The prepared dependency update is broader than one function: it moves the four explicitly replaced log modules from v0.16 to v0.21 plus associated OTel/transitive requirements. Do not call an old-vs-upgrade+overlap comparison an isolated overlap result. See cli-log-overlap-source-review.md for the correctness gates.

Fresh input caveat: the existing local-fresh-input pair writes one new input value, executes baseline, then candidate against the same bytes and the same engine. Both outputs prove invalidation and correct content, but the second invocation can reuse downstream results. It is not an independent first-use edit-cost comparison. A prepared, unexecuted ten-command local-only driver uses two primers and four alternating pairs with different equal-length first-seen input values per variant. It preserves warm engine/SDK state and explicitly does not claim cold caches. That is useful to check whether the speedup survives fresh input admission without sharing the exact preceding content result; it does not replace a broader real compilation/edit workload.

No raw engine logs, CLI stderr/stdout, telemetry payloads, credentials or identifiers belong in the public evidence archive. The allowlist contains only aggregate/numeric evidence, review prose and the extraction/prepared driver source.
