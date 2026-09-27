Prepared, not executed. Wait for the parent's exclusive heavy-slot grant before any compilation.

1. Run the negative overlay against `TestSessionTraceLogBarrierAllOriginsAndFinalMetrics`; require a failure at zero reader collections, not a compile failure.
2. Run the candidate normal and race gates in `./engine/server` with the anchored set:
   `TestSessionTraceLogBarrier.*|TestClientShutdownMetrics.*|TestClientRuntimeReclamationDrainsMetricsBeforeUnpublish|TestTelemetryRoutesClientsAndAncestorsExactlyOnce|TestCallPayloadReachesCloudOnce`.
3. Compile the narrow core/schema and Dang v2 packages with their existing focused source/log tests, including both changed core.Server mock implementations. Do not silently use the historical helpers overlay that omits current directive retention.
4. If those pass, compose identical fixed profiling instrumentation into an approved matched baseline/candidate engine. First inspect aggregate phases and actual per-client collection count on one explicitly primed local listing. No timing forecast from the whole 49 ms parent span.
5. Before production adoption, use the existing LLM log-capture tests for Dang stdout/error output, workspace path-safety and partial service-startup regression coverage, plus a repeated real check. Inspect call-payload presence and final metric export with a local receiver. These are future gates, not work already authorized/run by this prototype.

Cancellation keeps ordinary SDK semantics; a canceled ForceFlush may fail without making all queued telemetry visible. The new barrier must not claim stronger durability than full FlushTelemetry. No asynchronous fire-and-forget work is introduced.

The frozen `validate.py` now defines exactly four subprocess steps: one expected-negative server test, 15 explicit server test roots normally, the same 15 with race, then six existing core/schema/Dang tests across three packages to compile both changed mock implementations and retain source-error behavior. `-p=1` keeps package compilation/testing sequential. All regexes are anchored, skipped tests are rejected, and the successful roots must exactly match the reviewed names. The negative witness requires the specific zero-versus-two actual-reader assertion for root, rather than accepting arbitrary failure or failed compilation.

Inputs include exact overlay files, original production/mock files, existing regression tests, go.mod/go.sum plus SDK module pins, and the Go1.26.6 toolchain SHA. Network module fetching is disabled. The only HTTP expected in the tests is the existing in-process httptest receiver with synthetic credentials. The driver strips inherited Dagger/OTel configuration from child environments and invokes no CLI or Docker process. Test logs stay private; the numeric outcome JSON contains test names and status only.

`validation-v1` must not exist before execution. Any unexpected error/timeout is recorded and stops the script; no automatic retry or fallback is allowed. The driver currently has only been parsed and dry-run; none of these gates has executed.
