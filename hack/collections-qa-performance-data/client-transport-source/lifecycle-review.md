The corrected candidate has passed its focused normal and race gates. It remains isolated and has no measured CLI performance result.

API requests keep a cancellation link to `Client.closeCtx` until their response body is closed, including after `Do` has returned headers. RoundTrip errors release that link immediately. The three telemetry streams use their existing `telemetryContext`, which survives command cancellation and stays alive through the successful `/shutdown` drain. Closing or canceling one HTTP/2 API stream therefore does not close the shared connection.

The physical connection owner is per Client. Each wrapper still constructs its own metadata headers and BasicAuth and injects per-request trace propagation and suppression. The engine decodes ClientMetadata for each request (`Server.ServeHTTP`), validates session/client/token when resolving executable requests (`getOrInitClient`), and creates the request's context/lifecycle lease independently. There is no global connection pool, result cache, cross-session metadata reuse or authority shortcut.

Pending dial registration and the transition to closed share one mutex. Close cancels the owner's dial context, closes established connections, then joins pending dials; a connector returning after cancellation has its returned connection closed before decrementing the pending counter. Concurrent Close callers wait for that same completion. The gated synctest witness fails against the earlier owner and passes against the correction, including when physical connection closure is itself blocked. This prevents HTTP-owned Docker command connections from escaping cleanup merely because they finished starting late.

This guarantee is scoped to the shared HTTP owner. BuildKit, reverse attachables and unconsumed speculative connector tunnels keep their existing lifecycle; the candidate does not claim to join every child process in an arbitrary failed startup. A connector that never returns and ignores cancellation cannot be joined within a guaranteed deadline. Docker's current `commandConn.Close` waits for its child command to terminate; that cost must stay inside full CLI timing. The candidate chooses complete owned cleanup instead of hiding it after exit.

With the normal peer stream limit, three telemetry streams and API requests share one HTTP/2 connection. If a peer only allows three concurrent streams, the unchanged non-strict HTTP/2 transport opens another connection for API traffic rather than blocking behind the subscriptions. A real HTTP/2 peer test covers that fallback, and the connector retains ordinary on-demand dialing after its two warmed tunnels.

A physical connection failure necessarily correlates API and telemetry failures more than two separate transports did. The candidate preserves existing OTLP cursor/resume handling and ordinary API transport errors; it adds no application-level retry that might repeat a mutation. Tests cover telemetry stream error/reconnect without canceling an unrelated API stream, slow telemetry with a large API response, late final records and terminal cursor validation, failed shutdown and partial initialization. They do not establish a latency benefit or eliminate network-level failure coupling.

Validation command (requires existing Go build-cache write access, but no Docker/Cloud access):

```sh
python3 /tmp/collections-perf/shared-client-transport-v1/prototype-v1/validate.py --run
```

The preserved first run is `validation-v1`: unchanged-source witnesses fail only the expected API/telemetry dial count and normal warm topology; the pre-correction ownership witness fails only the join contract; corrected normal and race suites pass. No shared production source was changed. The next experiment must compare two freshly matched CLIs that both include the same parent-metadata v2 implementation, using identical dependency pins and the same engine. No queue-worker backport, early log flush or core TypeDef bulk candidate belongs in that comparison.
