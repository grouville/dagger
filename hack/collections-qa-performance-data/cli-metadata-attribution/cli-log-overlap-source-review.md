Reactivating the prepared CLI log-overlap experiment is justified as an attribution experiment, not yet as a production fix.

Measured reason: JSON metadata reaches engine shutdown 93–138 ms sooner for all three Cloud core pairs, while its remaining CLI interval grows 84–127 ms. In the module pairs the engine Cloud drain itself grows 50–97 ms. These boundaries do not isolate HTTP or prove the same cause in both flows. Optimizing only the CLI cannot remove the engine's module drain; preserve that separate result.

Relevant source paths:

- internal/cmd/dagger/engine.go registers close telemetry first, then close dagger session. util/cleanups/cleanup.go:49 executes cleanups in reverse.
- initEngineTelemetry's cleanup at engine.go:489 closes span stdio, ends the root span, then calls telemetry.Close.
- The pinned otel-go logging.go:119 emits a distinct EOF log on closing each stream. Ordinary writes emit log records immediately; final EOF records are new work after the engine session closes.
- Pinned otel-go init.go:484 performs tracerProvider.Shutdown, LoggerProvider.Shutdown, MeterProvider.Shutdown sequentially, using one 30 s close context. Its live log interval is 100 ms; live trace processing also uses that interval. Shutdown drains rather than deliberately sleeping for the interval.
- The effective old log SDK is v0.16.0 despite the nominal v0.19 requirement, because the temporary CLI modfile contains explicit replacements. Its BatchProcessor.ForceFlush retries enqueue in a loop while the export buffer is full, and its poller re-triggers whenever a full batch remains even if the exporter was not ready. These are source-level busy-loop possibilities. No CPU profile from this metadata series demonstrates that either occurred, so the observed tail must not be attributed to busy spin as fact.
- The prepared v0.21 source instead owns dequeuing/export calls in one worker and processes ForceFlush/Shutdown requests through channels. It serializes each exporter, prioritizes queued lifecycle requests, and makes no equivalent enqueue retry loop. This supports upgrading before adding an explicit early ForceFlush, but is not measured latency evidence.

The narrow overlap patch starts logs.ForceFlush on a goroutine, drains traces, joins that ForceFlush, then closes logs and metrics in their original order. It does not detach work past CLI exit or shut logs before late trace-cleanup/error records can arrive. Per-exporter concurrency remains owned by the SDK. No public cache, data-dropping change or new daemon is required. The potential gain is overlapping independent log/trace drain; there is no promised fixed RTT saving or elimination of final EOF/root records.

Use three ordinary CLI variants with the same JSON metadata path and the same frozen engine: current dependencies; dependency upgrade only; upgrade plus early joined log flush. The retained preparation was based on HEAD21939 and maps only otel-go/init.go, so explicitly compose the current JSON CLI overlay and freeze the merged inputs. A future source update must not silently replace the measured JSON metadata loader with an older copy. Keep engine exporters/dependencies unchanged during this CLI comparison.

The seven prepared local tests need their expectations updated to the v0.21 contract before execution, rather than weakened to hide changed behavior:

1. Retain the gated real BatchProcessor witness: queued logs export while trace Shutdown is blocked, and the helper does not return before both are joined.
2. Verify final stdout/EOF-like records, a late trace-cleanup record, and trace failure reporting arrive once and in per-channel order. Cover more than 512 final records so splitting is not mistaken for loss.
3. Verify failure reporting through the actual path. v0.21 ForceFlush returns a synchronous export error; the old test expecting only the global asynchronous error handler will be wrong for that case. A separately timer-triggered export still exercises the global handler.
4. v0.21 BatchProcessor.Shutdown invokes the exporter's ForceFlush itself. The old no-trace test must distinguish no extra helper ForceFlush from the legitimate shutdown flush, and must still prove no empty network upload or duplicate payload.
5. Cancellation must bound the helper and still request logger shutdown; separately verify a context-aware blocked exporter worker eventually exits. Joining the helper's ForceFlush goroutine alone does not prove every SDK internal worker has ended after cancellation.
6. Keep errors from trace, early log flush, final log shutdown and metrics observable. Check that errors emitted before logger shutdown remain exportable, without requiring all cleanup diagnostics to be delivered after their own provider closes.
7. Repeated close, nil providers and race checks should retain no double shutdown/duplicate data. Real final-queue and cancellation tests are more meaningful than only asserting method names.

For a local transport experiment, use a fresh loopback fake OTLP receiver with exact record/request counting and bounded configurable latency, explicitly not the actual Cloud. Gate one trace response to demonstrate overlap independently of scheduler timing, then exercise normal short commands and high-volume logs. Timing hooks should distinguish client.Close, root/stdio finalization, trace drain, early log flush, logger shutdown and metrics; HTTP hooks can count requests and write-to-first-byte separately without payload logging. Any claimed real-Cloud gain needs a later authorized measurement; this round's 220-command budget is exhausted.

No sources in cli-log-overlap-v3 were changed, and no tests, builds or runtime calls were performed for this review.
