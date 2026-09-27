# Telemetry completion boundaries: next experiments

Source-only review at Dagger `85b60f7a0a`. No test, build, engine or Cloud command was run for this review. The three CLI close variants are being measured separately; this report does not predict their results.

The next small experiment can overlap an early flush with engine close, but cannot eliminate the final CLI export by itself. Two EOF log records and the completed CLI root span do not exist until engine close has returned. Combining all final telemetry behind one engine-owned acknowledgement requires a lifecycle protocol change, not an extra goroutine around the existing Close.

## Current sequence and records that must survive

`internal/cmd/dagger/engine.go:127–157` registers telemetry cleanup first and engine-session cleanup second. `util/cleanups/cleanup.go:49` runs them in reverse. Thus:

1. `engine/client/client.go:858` sends `/shutdown` and waits for the handler. The handler flushes workspace locks, concurrently drains the engine Cloud branches within their shared budget, ends OAuth credential-file access, begins closing the session, stops services, flushes local telemetry, and marks client streams terminating (`engine/server/session.go:2714–2832`).
2. The CLI drains those terminating telemetry streams before canceling internal connections. Session/attachable teardown and any errors or drain warnings complete. Those late events must remain observable.
3. `initEngineTelemetry` closes the command's stdout and stderr telemetry streams and ends the CLI root span (`internal/cmd/dagger/engine.go:489`). Pinned `otel-go/logging.go:119–137` emits one EOF record per stream; these are new records, not merely buffered bytes being flushed. The root's final snapshot contains its final duration and command status/error links.
4. The pinned `otel-go` closes trace, log and metric providers. Trace cleanup may emit more log/error records, so closing the logger concurrently with trace cleanup would lose data. The tested overlap instead starts ForceFlush early, joins it, then shuts the logger.

Engine session removal has an additional, later barrier: it drains outstanding queries, container/cache cleanup and client scopes, stamps `wcprof.session_complete`, then shuts down session providers (`engine/server/session.go:1070–1147`). Previous local-API readback confirmed a late request containing that completion carrier. Consequently `/shutdown` is not a claim that every eventual session-retirement record has already reached Cloud.

## What is established by previous timings

The metadata comparison selected ordinary candidate samples of 591.477 ms for core and 817.200 ms for module read. In those same rows the post-engine-handler intervals are 274.075 and 194.334 ms. They also contain transport/frontend/process work, so they are upper envelopes, not measured CLI export durations. Removing the entire latter interval would still leave the module sample at 622.866 ms. Those observations cannot support a promise that a CLI-only change reaches 500 ms for every flow.

A separate instrumented native-generation series established 306.870–431.730 ms of engine Cloud flush. Span/log branches already ran concurrently. Every invocation sent the same four log uploads: payloads 44, ordinary 5, payloads 14, ordinary 16, totaling 79 records and 26,377 declared request bytes. All warm requests reused connections, and waits lay mainly between request write and first response byte. The maximum remaining log tail beyond the simultaneous span branch was only 12.656–106.891 ms; summing serial queue waits would overstate removable critical path.

Separate-exporter concurrency was subsequently tested and held: it helped warm generation but made other flows slower, including expanded listings. Do not revive it as an assumed win. Neither these earlier generation samples nor their bounds transfer automatically to a new merged design or to current core/module commands.

## Ranked next proofs

### 1. Measure the already-tested provider-close change first

The three-way local API matrix isolates the worker correction from joined trace/log close. It is the smallest change with an existing correctness witness and no protocol/cache change. If request counts rise or complete CLI time does not improve, retain that result rather than attributing all post-handler time to removable exports.

### 2. Bounded early flush while Client.Close runs

A narrowly scoped experiment can start flushing the CLI's already queued logs (optionally its pending trace updates) immediately before invoking `sess.Close`, leave all providers open, then join the flush before normal finalization. This can drain old batches while the engine waits on its own exports. It must not call Shutdown or emit EOF/end the root early. Prefer one well-defined telemetry helper over manipulating global processor slices from the CLI; preserve each processor's existing serialization and the bounded cleanup budget.

The hard limit is temporal: final EOF/root records and cleanup errors are still created afterward and still require final delivery. The 100 ms live export interval already flushes older records in many commands, so an explicit earlier flush could save nothing, or produce additional small/live-only batches. There is no measured backlog in the old metadata series proving this option's gain. Its minimum useful proof is a gated local receiver: an old queued record exports while `/shutdown` is held, both final EOFs and root completion appear only after engine close, late errors appear once, and no export goroutine outlives cleanup. Count requests and bytes in no-backlog, fast-engine and slow-engine cases. Only then compare ordinary commands; do not implement a general engine protocol to test this narrow idea.

### 3. A single joined engine-owned completion barrier

A generic engine-native design could route CLI-owned records to the existing session sender and use a two-stage finish protocol:

- **Prepare completion:** stop accepting new executable work, finish workspace writes/services and drain local streams, while retaining the telemetry record graph, transport and credential attachables. Do not yet seal the engine Cloud sender.
- **Finalize completion:** the CLI submits its final EOF/root records with a bounded, authenticated completion request. The engine joins those with its pending session records, drains the relevant Cloud writers, reports completion/error, then closes the credential gate and allows transport/session teardown.

Existing POST telemetry routes already use stable client records and session-owned Cloud forwarding (`engine/server/telemetry.go:445–526`), but that is not sufficient: records can disappear when the session is removed, `/shutdown` stops credential-file refresh, and `Client.Close` closes the HTTP transport. A real protocol needs an explicit lifetime reservation, idempotent per-client barrier, admission cutoff, and protection against replay/duplicate forwarding. It must preserve nested/scale-out origin markers and avoid feeding returned engine telemetry back into Cloud.

There is also a trace semantics choice. Today's CLI root duration includes engine Cloud waiting, but excludes its own subsequent provider shutdown. Ending the root before a new combined delivery barrier would remove the former wait from that span. That may be a better definition of command work, but it is a visible timing change and must be deliberate. If exact existing span timing is required, a record whose timestamp includes a wait cannot be produced before that wait finishes; another final update/acknowledgement remains necessary. No batching trick removes this causality.

A useful protocol proof should retain blocking remote acknowledgement initially. Early local acceptance is a separate delivery-contract change: the current in-memory/spill telemetry store is not automatically a durable exporter outbox. Persisted pending delivery cursors, durable acknowledgement, crash recovery, bounded retention/backpressure and OAuth ownership after CLI exit would all need explicit design. This is where an engine-owned sender could eventually replace the earlier experimental external relay, but not by silently detaching today's flush goroutine.

### 4. Coalesce payload and ordinary log records before HTTP serialization

Both record classes share `/v1/logs`, and their incidental cross-channel arrival order is already scheduler-dependent. A single Cloud-specific worker could retain separate queues and delivery policies, then build bounded mixed batches from records already ready. This could reduce request count rather than merely adding competing HTTP requests.

The important boundary is before the two processors' current blocking Export calls. Merely replacing the shared serial gate with a request combiner is not enough evidence: when one processor is blocked exporting, it cannot submit its next batch, so two pending calls are not necessarily ready at the same time. The four observed batches do not imply two merged requests are achievable without delay. A fixed extra coalescing sleep would also trade cold/interactive latency for batching; the earlier 100 ms experiment did not justify a global default.

The mixed worker must keep ordinary queue capacity/drop semantics separate from payloads. A failed mixed export should report the ordinary error normally and retain/retry only its payload subset at the queue head, with current attempt limits/backoff/order. Payload deduplication claims must not be released early or sent through the ordinary dropping queue. Preserve per-writer retry-stable headers, one exporter call at a time, clone/ownership lifetime, context cancellation and bounded batch sizes. SDK-internal HTTP retries and payload-level retries are distinct layers; merging must not accidentally duplicate ordinary records on payload retry.

The smallest useful preparation is a deterministic replay of numeric arrival/ack events, supplemented by source-level queue semantics, to estimate how many records could actually coalesce without waiting. A real proof then needs payload failure plus ordinary success/error, queue saturation, cancellation, >512 records, retry exhaustion and shutdown. This is a larger processor change than early flush, and should be pursued only if reduced requests appear on the critical path of multiple ordinary flows.

## Disposition

Keep the final root, EOF and late cleanup records. Preserve joined, bounded delivery before claiming equivalent UX. First use the current matrix to decide whether joined provider close is worthwhile; next test a bounded early flush only if pending-record evidence supports it. Treat a two-stage engine completion barrier and a mixed log worker as distinct architectural experiments, with explicit lifecycle and delivery contracts. None is a Dagger result-cache optimization, and none should introduce a cross-session TTL or reuse dynamic call results.
