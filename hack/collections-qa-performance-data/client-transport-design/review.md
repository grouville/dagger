# Share the client's API and telemetry HTTP/2 connection

Source-only candidate review against Dagger `85b60f7a0a`. No implementation, build, test or workload has run. This follows the CLI CPU profiles; it does not replace the higher-priority parent-directory enumeration work.

## Work that exists now

The normal non-nested CLI has four connection consumers:

1. BuildKit control gRPC (`engine/client/buildkit.go:24`): wait/Info/version validation.
2. Reverse attachables (`engine/client/client.go:654`): an HTTP upgrade followed by reversed gRPC direction. This cannot simply be multiplexed into the ordinary client HTTP transport.
3. Telemetry HTTP/2 (`client.go:587,1821`): one transport multiplexes traces/logs/metrics streams.
4. API HTTP/2 (`client.go:675,1806`): one transport serves GraphQL and `/shutdown`.

`containerConnector.Connect` starts three speculative Docker exec tunnels only after a read from the initial tunnel returned bytes, and gives them to the later consumers. A successful process launch or EOF alone does not trigger them. Existing tests cover a dead initial tunnel, a failed dial, reuse when a waiter cancels, and later on-demand dials. This is therefore genuine concurrency for the normal CLI path, not three demonstrably unused tunnels.

A purely on-demand pool cannot keep that startup overlap if the caller still creates the consumers sequentially. A generic demand hint could avoid excess warm connections for nonstandard users, but these benchmark flows use all three. The concrete work-removal opportunity is one shared per-Client HTTP/2 transport for API plus telemetry; then normal startup needs two later physical connections instead of three.

## Smallest safe candidate shape

- Add a lazily initialized, **per-Client** `*http2.Transport` with explicit ownership. A `sync.Once` or initialization under the existing connection lifecycle prevents duplicate transports if wrappers are created concurrently. It dials with the existing transport-safe lifetime, not the lifetime of whichever request happens to open the first connection.
- Keep separate `httpClient` wrappers for API and telemetry. Preserve their independently constructed headers, BasicAuth, propagation, and Cloud-publishing response handling. The connection is shared only within the same Client/session/authority; no global transport or cross-session pool.
- Give API requests an explicit cancellation link to `closeCtx`, lasting until the response body closes. Use `context.AfterFunc` rather than a permanent waiter goroutine per request if practical. Release the link on RoundTrip error and on body Close. Canceling or closing one API response must not close the shared connection or telemetry streams.
- Keep telemetry requests on their existing `telemetryContext`, which survives command cancellation and the accepted shutdown drain but is canceled by `internalCancel` on final/error cleanup. Do not change cursor/terminal-frame logic or forwarding destinations.
- On successful Close: `/shutdown` completes, telemetry terminal streams drain, request/internal cancellation occurs, then the owned shared transport closes its idle connection after all consumers have completed. On errors/timeouts: cancel both request domains, join the existing consumers, and close the shared transport even if initialization was partial. Check every Connect error path too.
- Reduce proactive warm demand from three to two **only in the same candidate** once all normal connection consumers use the shared transport. Reducing it first only makes the API dial later; sharing first while retaining three speculative dials still launches the work supposedly removed. Preserve the initial answered-byte condition and on-demand fallback.

This is more than replacing `newTelemetryHTTPClient()` with `c.httpClient`: today's API dialer (`Client.DialContext`) schedules a physical connection close on `closeCtx`, while the telemetry dialer deliberately bypasses that mechanism. Shared transport needs request-level cancellation so one API close cannot truncate final telemetry. Conversely, using the telemetry dialer for everything without linking API requests would lose today's guarantee that Client.Close terminates in-flight API requests.

The current telemetry HTTP transport is local to `subscribeTelemetry`; it is not the `c.httpClient` explicitly closed in Client.Close. The source does not show an explicit CloseIdleConnections for that separate telemetry transport. A shared ownership proof should count final closed physical connections, rather than assuming response-body EOF already closed the pooled connection. This is a lifecycle observation, not measured leakage or a promised speedup.

## Focused proof before ordinary benchmarking

Use a counting connector and a real local h2c peer, without Docker or Cloud:

1. Open API plus three telemetry streams with real response bodies; prove one physical HTTP/2 connection serves all four. Reverse attachables/control remain separate. Both wrappers send the same intended session/auth scope and can carry independent request headers.
2. Hold an API response open, cancel its request, and prove telemetry still receives a late record and terminal frame. Do the converse: a failed/reconnected telemetry stream does not abort an unrelated API call.
3. Hold `/shutdown`, emit late spans/logs, and require complete terminal-cursor validation before shared transport closure. Client.Close must cancel a concurrent API request, join consumers, and close physical transport once.
4. Exercise canceled command with live attachables, rejected shutdown, deadline expiry, partial telemetry initialization, missing/legacy stream capabilities, and repeated/concurrent Close. Reuse existing session-attachable lifetime and telemetry-retry tests rather than weakening them.
5. Generic connector tests: one initial successful answer plus two warm dials; no warming on failed/dead initial connection; cancellation returns an unconsumed warm tunnel to the pool; extra demand still dials; all unused owned tunnels close on teardown where ownership is added.

Then build matched ordinary CLIs and compare core/module/listing/check/generate with the same engine. Capture actual dial/consume counts separately from timing; record process self/child CPU where possible. The earlier profiles show only 30–40 ms sampled core Dagger CPU versus 193–197 ms waited process-tree CPU, but that gap also contains unprofiled Dagger startup and sampling error. It does not measure the CPU of one removable Docker exec. Likewise the approximately 15–17 ms `docker version` wait is a separate availability preflight and is not removed by sharing a tunnel.

## Compatibility and disposition

The public API still uses ordinary HTTP/2 requests, the same headers, telemetry records, cache scopes and local filesync freshness. No server change should be needed if per-request authorization remains as today. However, connection-level failure coupling and HTTP/2 flow-control must be tested with a slow telemetry consumer and a large API response; a physical connection reduction is not automatically a wall-time improvement.

Expected patch scope: `engine/client/client.go`, focused client transport/lifecycle tests, and `engine/client/drivers/container.go` plus its connector tests. Prefer an explicit warm-demand mechanism if the connector serves materially different consumers; otherwise document that the count tracks the main client's transport topology. Keep BuildKit and attachables untouched. No code should be applied until the cancellation/ownership proof passes.
