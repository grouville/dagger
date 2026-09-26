# Reusing the engine for durable telemetry handoff

The long-lived engine is a better architectural home to investigate than adding
another permanent daemon. This does **not** mean the current telemetry store
already implements a durable outbox.

## Existing reusable mechanisms

* `engine/server/session_cloud_telemetry.go` already negotiates engine-owned
  Cloud publication per session, constructs the signal exporters, and preserves
  CLI forwarding when the engine cannot reach the destination.
* `engine/server/telemetry.go` routes origin-stamped telemetry into per-client
  stores, including the main client's view of its descendants. Existing streams
  have increasing row IDs and bounded reads. Reuse the selected root stream and
  its cursor, rather than copy all nested-client fan-out records into JSON files.
* The local TUI and Cloud are separate consumers. A slower Cloud publication
  interval need not slow the TUI's local record path.

## Missing invariants

1. **Durable acceptance.** `engine/clientdb/store_stream.go` keeps a memory tail;
   spill append and close call `bufio.Flush`, without `fsync`.
   `store_spill.go` explicitly says the store has no crash-durability contract
   and recovers only its complete prefix. Add an explicit durable checkpoint
   through a row ID, waiting for spill and syncing the affected streams before
   acknowledging a detached producer. Group that work at a meaningful boundary;
   avoid fsync for every live snapshot.
2. **Ownership after session close.** Cloud processors currently shut down with
   the session. Client store handles close at the final telemetry barrier.
   `store_registry.go` allows inactive stores to be collected after one hour;
   the engine's GC loop runs every minute. A pending outbox needs a persisted
   ownership pin and cursor until remote acknowledgement, plus quota, retry,
   permanent-failure and restart rules. Merely keeping a goroutine alive is
   insufficient.
3. **CLI's own final records.** CLI telemetry initializes before engine connect
   and shuts down after session cleanup (`internal/cmd/dagger/engine.go`).
   Engine-origin records are no longer redundantly forwarded to Cloud when the
   engine owns them, but CLI-origin records still have their own Cloud pipeline.
   A common handoff needs explicit producer completion before transport teardown
   and a policy for records emitted by final CLI cleanup. Avoid closing the
   import endpoint while those records are still being produced.
4. **Credentials beyond the client lifetime.** Engine OAuth refresh currently
   reads and atomically replaces the credentials file on the CLI host through
   attachables. `stopCloudTokenRefresh` deliberately closes that gate before
   attachables disappear. Retaining the callback after CLI exit cannot work.
   A static engine token is easier to delegate, but expiry/revocation still
   matter; OIDC tokens may expire quickly. OAuth needs an explicit delegated
   credential or a reconnect/refresh protocol and account isolation, not an
   unnoticed copy of a rotating refresh token into the cache.

## Batch behavior to measure before selecting a design

The current Cloud payload processor uses a 512-record maximum with only a 5 ms
coalescing interval inherited from the local persistence path. A pass detaches
the present queue; records arriving during export receive another 5 ms window.
An 88 ms HTTP response implicitly allows more records to accumulate, whereas
a 2–4 ms local durable acknowledgement can produce many more small requests.
`ForceFlush` and `Shutdown` already bypass coalescing and drain immediately.

The first isolated async trial sent 89–96 requests per warm command, with
~8.09 seconds of summed request duration and ~88.3 ms per request. About 54–59
requests remained at CLI exit. The comparable sync/direct request counts were
not instrumented, so amplification is a hypothesis supported by code, not yet
a measured ratio. Four relay workers showed about 1.68 average overlap across
the whole command-plus-drain interval; that does not establish worker saturation.

If measurements confirm payload-log amplification, give Cloud's payload
processor its own coalescing option (for example the existing 100 ms Cloud live
interval), while preserving local 5 ms delivery and immediate explicit flush.
A durable row-stream consumer could group committed rows into bounded requests
at publication time. Existing writer/sequence identities and receiver semantics
must be preserved; concatenating arbitrary OTLP request bodies is not batching.

The next comparison should record requests, payload bytes, signal type,
successful responses, queue growth and final delivery time across ten commands
without waiting for Cloud between commands. Faster command completion with an
ever-growing queue is not a sustainable throughput improvement.
