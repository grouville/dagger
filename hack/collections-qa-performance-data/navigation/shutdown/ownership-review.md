# Exit-tail ownership audit at 341595f376

Source review plus isolated local unit/race validation; no new engine workload or Cloud command. Existing profiler evidence is one separate diagnostic pair: about 1.39 s of recorded engine work on either engine, followed by 701/1079 ms until CLI exit. This review identifies actual dependency barriers and a small redundant-work candidate; it does not assign that measured tail to an uninstrumented phase.

## Current shutdown dependencies

1. `internal/cmd/dagger/engine.go:123–155` initializes telemetry, registers its cleanup, then registers `sess.Close`. `util/cleanups/cleanup.go:57` executes cleanups in reverse order. The engine client therefore closes before CLI root-span completion/provider shutdown.
2. `engine/client/client.go:858` first sends `/shutdown`. On success it drains the engine's terminal telemetry frames while connections and attachables are alive. It then cancels internal transports, closes clients/attachables and joins cleanup. The second telemetry `Wait()` is a join of the same consumer group, not a second remote flush; once already completed, it returns immediately. Removing it does not remove a second Cloud RTT.
3. `engine/server/session.go:2710` closes new-work admission, writes workspace locks while host attachables remain available, explicitly flushes session Cloud spans/logs, closes the token-refresh file-operation gate, begins closing, stops services, flushes local session telemetry, and signals terminating streams. Cloud span/log drains already run concurrently in `flushSessionCloudTelemetry` (`session_cloud_telemetry.go:631`). Generic `FlushTelemetry` does not synchronously reflush Cloud spans/logs: bounded Cloud processors deliberately implement its `ForceFlush` as a no-op.
4. Final session teardown (`session.go:1139`) waits for accepted requests, services, containers, analytics and detached-cache cleanup to stop. It stamps the final wcprof carrier, shuts down client metric providers before session traces/logs, then drains the owned Cloud metric queue and closes client stores. Producers and local-store consumers must remain valid through these barriers.
5. Only after `sess.Close` completes does CLI cleanup restore stdout/stderr, close span stdio, end the command root and call `otel-go.Close` (`engine.go:489–494`). The pinned otel-go implementation shuts down trace, log and metric providers sequentially, under one 30 s context. Analytics is a later Cobra finalizer; the current driver sets `DO_NOT_TRACK=1`.

Engine-owned and CLI-owned Cloud publication are already separate. A confirming engine response excludes engine-origin telemetry from the CLI's Cloud exporters, while still forwarding it to the frontend. CLI-origin root/final records still need their own publication. A shared connection pool does not turn those into one producer or remove the final-root dependency.

## Why ending the root at callback completion is not a neutral optimization

The callback's `rerr` is indeed captured before `sess.Close` runs. The `cleanupTelemetry(rerr)` argument therefore excludes errors later returned by cleanup. Report-only/plain-style frontend paths join cleanup errors into their own final error; the interactive pretty frontend logs cleanup errors separately. This is an existing error-argument distinction, not justification for changing root completion time.

More importantly, `dagql/dagui/db.go:1143–1162` treats the root's end as a trace-completion signal: it marks still-running spans canceled/LeftRunning and clamps their end time, including live updates arriving after the root ended. Ending it when the callback returns would mark active service/lock/cleanup work canceled prematurely and change the command's displayed duration. Merely keeping providers alive until both cleanup branches finish does not preserve that UX. A separate operation child span could end at callback completion, but the authoritative command root must retain its completion barrier unless the trace/UI protocol itself changes.

Consequently, no early-root-end experiment is prepared here. That would require explicit product semantics and tests of late success/failure updates, services, signal cancellation, host-lock errors, nested invocations, and Cloud/local completion behavior.

## Smallest concrete candidate: collect metrics once at final runtime shutdown

`clientRuntime.shutdownMetrics` (`engine/server/session.go:670`) calls `MeterProvider.ForceFlush(ctx)` immediately before `MeterProvider.Shutdown(ctx)`. All production readers created by `initializeClientMetrics` are OTel `PeriodicReader`s. In the pinned OTel metric SDK v1.43.0, `PeriodicReader.Shutdown` itself stops/joins its worker, performs a final collection/export and shuts down the exporter (`periodic_reader.go:348–384`). Thus the preceding flush performs another reader collection and export at an already-quiescent boundary.

Removing only that preceding call preserves the real final collection, the caller context, reader/exporter shutdown, metric locking, pointer clearing, idempotent runtime reclamation and session-owned Cloud exporter lifetime. It also avoids running observable callbacks an extra time. The explicit `flushMetrics` API and main-client pre-termination flush remain unchanged; a metric recorded between a genuine earlier flush and final shutdown must still be delivered.

For a client with local and Cloud readers this removes one collection/export from each reader at final shutdown. The Cloud queue currently stores and serially sends each nonempty resource collection separately. Request savings depend on which collections are nonempty and on earlier periodic/explicit flushes; this review does not infer an exact production request count or a millisecond gain from the old 14-metrics-request examples. A transport count measurement is required.

Prepared under `metrics-final-collection/`:

- `source.patch` changes only the immediate flush in `session.go`; original and candidate source are retained.
- `overlay.json` is the minimal engine overlay. Merge its single replacement into the frozen active engine overlay rather than discarding SDK/other replacements.
- `test-overlay.json` adds six tests with real SDK periodic readers, not a mock provider mirroring the implementation.
- `baseline-test-overlay.json` runs those tests against unchanged source; the one-collection assertions should fail before the patch.

The tests cover two readers receiving final value 42 exactly once, explicit flush of 41 followed by final value 42, waiting for/canceling a blocked final export, collection-error propagation, failure/cancellation across both readers, exporter cleanup and repeated shutdown. **Validated: all 14 selected top-level unit tests and the same 14 tests under the race detector pass.** The two final-collection assertions fail on unchanged source with duplicate values `[42,42]` and `[41,42,42]`, respectively. The source patch does remove an accidental extra export attempt: normal exporter retry behavior and the final Shutdown error remain, but a transient first failed export followed by a second opportunistic collection is no longer supplied by two SDK method calls. Do not describe the old sequence as a deliberate retry protocol.

Remaining before a wall-latency claim: count actual local/Cloud metric requests and verify final gauge/counter values. The focused tests, race tests, baseline failure, relevant lifecycle/client-reclamation tests and Cloud metric tests have passed their expected outcomes. A matched actual listing/check pair must still measure the entire CLI and separate exit phases; a request reduction alone is not a wall-latency result.

## Parallelization that is already present, unsafe, or unlikely to help

| Change | Assessment |
| --- | --- |
| Run engine Cloud trace/log flushes together | Already done with a joined WaitGroup and shared shutdown budget. |
| Parallelize the second client telemetry Wait with the first | They wait for the same group; there are not two independent drains. The final join ensures canceled consumers terminate. |
| Remove the first engine Cloud flush and rely only on final teardown | Not equivalent. The first runs while OAuth refresh can still read/write host credentials. The refresh gate closes before attachables disappear. Final cleanup can emit more records, but cannot assume host refresh remains available. |
| Overlap Cloud flush with workspace-lock flush | Their work may overlap mechanically, but lock writes still require attachables and can emit final telemetry. Likely small benefit; cannot remove their joins or claim final-delivery equivalence without tests. Not prepared without phase evidence. |
| Start Cloud metric-queue Shutdown earlier | Its worker already exports while trace/log barriers wait. Moving only the wait earlier generally does not shorten the export schedule; final provider collections must be queued first. Do not mistake concurrent background export for serialized network work. |
| Shut CLI trace/log/metric providers down concurrently | Potentially overlaps final export triggering, but is not generically semantics-free: exporter/metric callback cleanup can emit logs or other signals, and trace-shutdown errors are logged while the current log provider is still open. A narrow pipeline-specific change requires instrumentation and cross-signal cleanup tests. |
| Remove every ForceFlush before provider Shutdown | Shutdown often drains, but verify each configured processor and cross-signal cleanup ordering first. The metric-reader duplicate above is directly proven from the configured production readers; do not generalize blindly to arbitrary providers. |
| Increase Cloud payload coalescing to 100 ms | Prior controlled trial reduced async-relay requests/backlog but did not improve normal synchronous CLI latency. Existing background HTTP latency already coalesces arrivals; delaying a last small burst can move work onto shutdown. |
| Return while Cloud export goroutines continue | A CLI process exit destroys its goroutines. An engine outbox needs durable acknowledgement, retained ownership/quota/retry state and delegated refresh rights; current client-store spill/flush is not an fsync-backed outbox contract. |

## Instrumentation needed next

Use the prepared diagnostic CLI to separate `/shutdown` HTTP time, terminal-stream drain, transport cleanup, root-span End, each CLI signal-provider shutdown and analytics. Correlate those with engine shutdown phases and signal-specific HTTP start/response/body timing. Preserve the same root lifetime and all joins during diagnosis. A first-byte interval cannot distinguish server processing from network latency without receiver/server evidence; a later heap snapshot cannot attribute the tail to GC.

If a large CLI trace shutdown is confirmed, the next source question is whether the final root export is queued behind an earlier in-flight batch, or itself waits mainly on one HTTP response. If engine flush dominates, distinguish pending payload batches, ordinary log contention on the intentionally serial log exporter, and final trace drain. Those are different fixes; arbitrary shorter waits or fire-and-forget would only move or lose required delivery work.

### Reader error semantics checked against the pinned SDK

`metric/config.go:49` unifies all reader shutdown functions without short-circuiting, joining each reader's error. `PeriodicReader.Shutdown` always calls its exporter shutdown after collection/export; within one reader, an earlier collection/export error takes precedence over an exporter-shutdown error. Cancellation of the first reader therefore does not skip cleanup of the second reader, although its final collection can also return the same canceled context. The isolated tests explicitly exercise these two-reader cases.

Both production reader exporters expose no-op `ForceFlush`: `clientMetricExporter` and the session-owned `cloudMetricQueue`. The old immediate `MeterProvider.ForceFlush` consequently has no separate durable acknowledgement contract. Its additional possible error is from an additional metric collection/export attempt; the actual final collection/export and reader errors are retained by SDK Shutdown. Normal periodic and explicitly requested flushes remain intact.

## Completed validation

The unchanged source fails only the two intended duplicate-value assertions (0.031 s test execution). The isolated candidate passes 14 selected tests in 0.601 s, and the same 14 pass under the race detector in 2.88 s. Times exclude compilation and are correctness timings, not performance benchmarks. Existing tests include final metrics producing a cleanup span, reclamation waiting for metric delivery before unpublishing runtime state, Cloud queue copy/timeout behavior and actual fake-receiver publication. Shared `session.go` still matches the frozen baseline SHA. See `metrics-final-collection/validation.json` for commands, outcomes and hashes.

## Observed awaited-path attribution

The separate engine-log audit now identifies the profiled foreground difference as the explicit Cloud-flush phase (308/1083 ms), while all 14 observed final session-shutdown summaries finish after CLI exit. See `shutdown-log-evidence/report.md`. The tested metric change removes redundant collection/queue work, but is not evidence for eliminating the whole foreground Cloud wait.
