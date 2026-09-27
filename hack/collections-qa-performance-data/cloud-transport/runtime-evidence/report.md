# Bootstrap and Cloud drain attribution

All 12 commands passed: ten with their normal Cloud destination and two explicit local-only primers. Both owned engines stopped afterward; the fixture was restored and both volumes were retained. Every numeric buffer had zero dropped events and every final observed-quiet snapshot had zero active HTTP requests. These are instrumented attribution measurements, not ordinary-binary speed comparisons or an end-to-end Cloud storage guarantee.

Two matched engines use runtime HEAD `21939e4ff9`, the same pinned SDK/Dang/lazy-withFile stack and identical diagnostic hooks. Only the local span serializer differs: baseline versus serialize-once common. The first command on each new engine volume was `ws ls`; no hidden workload warmed the engine. Generation uses the native Dang fixture, removes `generated.txt` before each invocation and verifies the actual expected file bytes. It does not compile an SDK module. The six measured warm generation calls alternate engine order across three pairs.

## Cold startup: the missing work is now located

| Engine | Full CLI | TypeDef graph construction | Base schema construction | Final server fork | Query execution |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, first view | 2,464.791 ms | 481.500 ms | 10.710 ms | 0.221 ms | 44.389 ms |
| Common, first view | 1,123.962 ms | 401.056 ms | 9.480 ms | 0.346 ms | 42.714 ms |

The eager core TypeDef graph runs before `serveQuery`, accounting for the previously missing roughly 400–480 ms. It is outside the earlier wcprof query interval. Later warm workspace calls have only 0.382–0.420 ms of runtime initialization and 27.600–28.042 ms of query execution. Their full CLI times are 579.577 ms baseline and 577.911 ms common.

Do not interpret the two cold CLI totals as a serializer improvement: the first baseline CLI spends 1,139.345 ms in pre-run, with only 2.303 ms in label loading. The diagnostic does not split the remainder. The two engines also separately perform their first Cloud reachability check, 232.809 and 252.276 ms. The TypeDef timer directly identifies avoidable eager work regardless of these other differences.

## Warm generation: four serialized log uploads dominate the engine drain

| Pair/order | Baseline CLI | Common CLI | Baseline engine Cloud flush | Common engine Cloud flush | Baseline file visible | Common file visible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0: baseline, common | 828.497 ms | 932.711 ms | 375.850 ms | 431.730 ms | 328.612 ms | 299.288 ms |
| 1: common, baseline | 826.052 ms | 831.917 ms | 380.858 ms | 348.725 ms | 289.217 ms | 326.658 ms |
| 2: baseline, common | 734.939 ms | 823.343 ms | 306.870 ms | 342.201 ms | 305.196 ms | 330.869 ms |

The common serializer is slower in all three CLI pairs, but the middle pair has a shorter engine Cloud flush. Consequently neither a blanket wall-time improvement nor a causal serializer regression follows from these six diagnostic samples. File visibility is polled every 5 ms and is separate from complete CLI exit.

Every generation command exports the same four log batches, in this order:

| Channel | Records | Declared request bytes |
| --- | ---: | ---: |
| Call payloads | 44 | 15,661 |
| Ordinary records | 5 | 1,235 |
| Call payloads | 14 | 6,044 |
| Ordinary records | 16 | 3,437 |

That is 79 records and 26,377 declared request bytes per command, with no log-request amplification in the common variant. HTTP framing/retries could change transmitted bytes; these counters measure declared request lengths. Trace requests vary independently: baseline has 4/4/3, common 4/3/3. Every observed engine response is HTTP 201 and transport error counters are zero.

Payload and ordinary ForceFlush already run concurrently, as do the span and log branches. Their shared log exporter admits one batch at a time. Three queued batches per command wait approximately 81–145 ms each at that gate. The ordinary-record flush ends last in all six commands and determines the 306.870–431.730 ms session flush. The payload flush waits on earlier ordinary exports too. These overlapping phase durations must not be added.

All 45 engine requests during the six generation commands reuse established connections, with zero TCP connect or TLS handshake attempts. Across all requests in any one command, connection-acquisition time totals at most 0.059 ms. Almost all HTTP time lies between writing the request and receiving the first response byte. This includes network latency and remote processing; the measurement cannot separate them. The first payload request takes roughly 153–176 ms and later requests usually take 81–98 ms, with three slower ordinary-log tails of approximately 149–170 ms. More outer flush goroutines cannot remove the shared serialization.

No engine token refresh, token file read/write or token exchange occurred. Token-gate waits are 0.003–0.013 ms. This identifies the cost in these samples; it does not eliminate the OAuth lifetime constraint for other sessions.

## Foreground versus later work

All generation HTTP requests complete before CLI exit. The workspace cold common sample has one metric upload still active at the post-exit sample; it starts before CLI exit and finishes afterward. Metrics run through their existing background queue and are not part of the foreground span/log flush. The other eleven post-exit snapshots have no active requests.

The post-exit snapshot occurs 0.54–2.02 ms after the recorded exit timestamp. An additional observed-quiet wait requires zero active requests and no new event for 500 ms, bounded at eight seconds. It is intentionally outside CLI wall time and is not a durable-ingestion or record-completeness assertion. Both local-only primers emit zero observed engine and CLI HTTP exports.

## Disk and CPU controls

Each warm generation sample records zero cgroup disk bytes written over its counter bracket. Host I/O PSI increases by only 0.026–1.146 ms (`some`) and memory PSI remains zero. The engine uses 322–386 ms of CPU per command. Counter brackets extend slightly beyond CLI exit for sampling, so CPU is not an exact subprocess-only quantity. These observations do not support disk stalls as the source of this particular 300–430 ms foreground drain.

## Next change to evaluate

A subsequent bounded read of the two stopped engines' persisted local log streams found zero exact `dagger.io/engine` scope records: each volume had 365 rows, all in other scopes. The helper sought past bodies, attributes, identifiers and resources and read only scope fields; it had no network and mounted both volumes read-only. These are whole-trial local row counts, not a one-to-one account of Cloud batches, but this particular discarded-scope shortcut cannot remove the observed ordinary batches. See `scope-counts.json`.

If the ordinary records must be delivered, separate ordinary and payload SDK exporter instances can remove this cross-channel gate while preserving one exporter call at a time per instance. They must share the credential's token source and the HTTP pool, own independent writer sequencers, retain joined flush and bounded shutdown, and shut down the payload exporter only after its worker stops. This remains a source-review candidate; it has not been built or timed. Independent HTTP requests can overlap but may increase concurrent destination load. The existing span flush can become the next critical path, so summing removed log waits would overstate the possible CLI gain.

`numeric-evidence.json` contains every phase, anonymous request timeline, class/count/length summary and resource counter used here. `verification.json` and the matched build manifests preserve provenance. Raw wcprof, stdout/stderr and authentication data remain outside the archive.

With all other measured phases held fixed, the last log response ends only 12.656–106.891 ms after the concurrent span flush across the six generation samples (62.154 / 81.078 / 106.891 / 66.584 / 85.882 / 12.656 ms in execution order). Eliminating the remaining log delay therefore exposes the span branch; this is a bound from the existing timeline, not a measured speedup or a prediction that network/server timing stays constant under more concurrency.
