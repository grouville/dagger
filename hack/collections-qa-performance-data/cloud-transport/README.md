# Engine Cloud transport and bootstrap diagnostic

Both matched diagnostic engines are built. All 15 focused tests pass
with race detection. The completed runtime has ten normal Cloud commands and two
local-only primers, all correct. See `runtime-evidence/report.md` and its numeric
verification. `validation.json`, `build-result.json` and
`baseline-build-result.json` record actual execution. It preserves the normal span-fanout common candidate at
`21939e4ff9`, including the metric shutdown fix and the same pinned common SDK,
syntax and lazy-withFile stack. It adds passive timing/counter hooks; it does not
change queues, batch sizes, delays, retries, tokens, transports or shutdown order.

`manifest.json` records every overlay/dependency input. The existing reviewed
CLI diagnostic's pinned byte-identical otel-go copy is a local module replacement
so a helper file can be added. No instrumented CLI source or otel init is included.
The original Dang replacement remains unchanged. `diagnostic.patch` is the exact
instrumentation diff. `build.py` prints its command unless passed `--run`.

## Numeric collection

The existing localhost `/debug/vars` endpoint contains one fixed object named
`cloud_transport_audit`. Keep only that object when collecting results; do not
archive the rest of expvar. It contains a process Unix/monotonic anchor, snapshot
time, 10,000-event bound, total/dropped event counts, started/finished/active HTTP
counts and completed events. Each event has a monotonically increasing local
event sequence, fixed source-defined kind, start/end offset and numeric values.
The event sequence is unrelated to export, client, trace or span identifiers.

No IDs, URLs, hostnames, header/authentication values, error strings, request or
response contents are recorded. Pipeline log classes are source-defined integers:
0 unknown, 1 ordinary records, 2 call payloads. Request classes are 0 other, 1
query, 2 init, 3 shutdown, 4 attachables, 5 telemetry subscription. Classification
does not inspect any log payload. There are no filesystem writes in hooks or
per-call persistence operations. Reading the object snapshots under a short
mutex and performs JSON encoding after releasing it.

The collector stops retaining rows at its bound and increments dropped_events;
never silently interpret a saturated buffer. HTTP start/finish counters continue.
Finished request publication and its completion counter update are atomic under
the collector mutex. Response bodies retain their original read/close behavior;
the observer counts only bytes read by the existing consumer. A body never closed
has no completed event and remains active. Declared request length is not a count
of transmitted bytes. There are no upload payload copies or pre-reads.

## Shutdown boundaries and interpretation

- `engine.cloud.session.force_flush`: existing session-wide span/log drain.
- `engine.cloud.spans.flush_bound` / `.force_flush`: outer deadline wrapper and
  actual span processor flush; an absent inner event can indicate a skipped flush.
- `engine.cloud.logs.flush_bound` / `.force_flush`: same for the complete log pipeline.
- `engine.cloud.logs.payload.force_flush` and `.records.force_flush`: the two
  existing log pipeline flush branches, already concurrent.
- `engine.cloud.logs.batch`: an export batch at its existing processor boundary,
  tagged by the fixed numeric class and record count.
- `engine.cloud.logs.serial_wait`: waiting for the shared exporter admission
  channel; `.serial_export` is the admitted call to the existing exporter.
- `cloud.export.traces` / `.logs`: existing sequenced exporter calls; numeric
  record counts and log class, with no sequence header or writer identifier.
- `cloud.traces` / `.logs` / `.metrics` / `.other`: request transport interval,
  connection acquisition/reuse, DNS/connect/TLS counts and durations, request
  write, first response byte, headers returned, status and body read/close counts.
- `engine.cloud.token_gate.stop` / `.wait`, `.token_refresh`, `.token_file.read`,
  `.token_exchange`, `.token_file.write`: the existing token/lifetime boundaries.
  Static-token sessions should not enter refresh/file phases; that is a measured
  absence, not a reason to remove the OAuth lifetime constraint.

Parent and child phases overlap and must not be summed. Exporter time outside
HTTP can include encoding, retry/backoff, token work and scheduling; it is not a
pure queue measurement. A processor's ForceFlush includes waiting on previously
queued/in-flight work. These hooks do not measure per-record enqueue residence.
HTTP write-to-first-byte includes network and remote processing; it does not
separate them. Connection acquisition includes DNS/connect/TLS and queueing.

## Cold query admission boundaries

The same helper brackets main HTTP entry, client HTTP dispatch, getOrInitClient,
session initialization, local telemetry initialization, Cloud initialization and
reachability check, gateway/runtime initialization, and serveQuery. Static schema
subphases split base lookup/lock/build, view lookup/lock/build, buildTypeDefs, final
server fork and CoreMod wrapper construction. Store retention and per-client
metrics initialization are separate. No client, view, type or schema names appear.

This covers work before `session.serveQuery` wcprof starts. Match request time
brackets and distinguish the first view construction from later cached lookups;
do not transfer timings from a profiled cold sample to a separate ordinary sample.

## What already overlaps, and what cannot simply detach

`session_cloud_telemetry.go:flushSessionCloudTelemetry` uses a WaitGroup and starts
all cloudFlushers concurrently. Its log pipeline calls `bothWithin` for payloads
and ordinary records. More goroutines at either outer boundary cannot remove a
serial stage that is already overlapping. The shared serialLogExporter enforces
the existing sdklog.Exporter non-concurrent-use contract; removing its gate is
not a safe optimization.

The main shutdown request first flushes workspace locks, then flushes session
Cloud telemetry, then stops and waits on token file operations, then calls
beginClosing and stops services. Workspace lock writes and OAuth credential
reads/writes rely on client attachables. The token gate prevents a refresh from
waiting through an already-closed client transport. Moving flush to an unowned
goroutine after CLI exit would change that lifetime and the current delivery
boundary. The diagnostic changes none of these requirements.

Metrics use their existing background queue. The session-wide span/log flush
does not include metrics; request observations can still show a metric upload
overlapping the interval. Later exporter shutdown is separate from this flush.

## Prepared correctness checks

Three local otel helper tests cover passive body/close semantics and privacy,
immutable/bounded event publication, and concurrent snapshots (suitable for
`-race`). Two server wrapper tests cover unchanged exporter callbacks/context/
record slices and fixed endpoint classes. Existing Cloud pipeline/routing tests
can run with the test overlay. The helper/wrapper tests and selected existing Cloud pipeline/transport tests
have passed under race detection; see `validation.json`.

The diagnostic adds clocks, locks, maps, context values, body wrappers and JSON
snapshot work. It is for attribution, not a normal-engine wall-time comparison.
Use ordinary matched binaries for performance conclusions.


## Paired diagnostic control

`baseline-manifest.json` and `baseline-build-result.json` record the completed
second build. Both builds use HEAD `21939e4ff9`, the same diagnostic hooks and
fixed runtime inputs, replacing only the local span serializer with its frozen
baseline. Runtime input hashes are preserved in both manifests. Build preflight
allowed precisely two changed tracked documentation/archive files; runtime
source hashes remained unchanged. Both versions are diagnostic-only binaries.
