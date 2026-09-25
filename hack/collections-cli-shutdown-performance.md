# Collections discovery: CLI shutdown and Cloud ingestion

September 25, 2026. Starting the first analytics upload during command execution
reduces the minimal core-query diagnostic from **754 to 512 ms median**. It does
**not improve the real greetings-api listing**, which remains around 2.29 s.
The 500 ms discovery target remains unmet. Trace delivery still takes hundreds
of milliseconds at shutdown; this investigation separates that cost from a
second, previously serialized analytics upload.

## What is committed

[`b57f1deaf2`](https://github.com/grouville/dagger/commit/b57f1deaf2) wakes the
existing analytics sender when the first event is captured. The network request
then overlaps the command and trace export. Later events keep the existing
batch interval. Shutdown still drains queued events and waits with the existing
one-second analytics timeout. Opt-out and error handling are unchanged. This
does not create a new durable-delivery guarantee; analytics remains best effort.

The change is ordinary CLI/engine source, independently upstreamable. It adds
one notification per tracker lifetime and can split the initial events into an
earlier first batch. It does not increase the ongoing flush frequency. No
changes to Dagger result caching, discovery semantics, or Cloud deployment are
needed. Tests with a blocked HTTP transport verify early upload, shutdown
waiting, delivery of events captured during an upload, empty shutdown, and
opt-out. The focused analytics tests pass with the race detector.

## Measurements on Kyle's repository

Each sample starts a new CLI process and includes its exit. The app is
`kpenfound/greetings-api@14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`, with
`dagger/go@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. Both CLIs target the
same warm engine and unchanged app settings. Cloud telemetry and analytics
remain enabled; the broken SSH agent variable is omitted symmetrically.
Compilation, tests, instrumentation and profiling are outside these series.

The engine is the previous [artifact-schema candidate](collections-artifact-schema-performance.md),
including the experimental Dang and TypeScript SDK stack described there.
These absolute discovery timings are not timings for an ordinary branch build
or a verified reproduction of Kyle's installed binary.

Eight measured runs per variant, with reversed order on alternating rounds:

| Full process | Control | Early analytics | Difference |
| --- | ---: | ---: | ---: |
| Core query `{ __typename }`, median | 754 ms | 512 ms | −242 ms / 32% |
| Core query, range | 703–795 ms | 449–537 ms | |
| `dagger check -l --all`, median | 2.286 s | 2.290 s | No demonstrated gain |
| Listing, range | 2.216–2.358 s | 2.209–2.362 s | |

All listings match the 14 expected checks byte for byte. The core query is a
diagnostic, not artifact discovery. The listing already lasts long enough for
the original one-second analytics timer to upload during execution. No new cold
or source-invalidation speedup is claimed from this CLI scheduling change.

Separate wcprof captures report 21,438 operations, zero dropped events and
zero open operations on each side. Their full commands take 2.394 and 2.268 s;
engine trace spans take 1.88 and 1.76 s. These individual captures do not
establish a listing speedup: the repeated series above is the comparison.
wcprof does not account for the entire CLI's Cloud/analytics shutdown.

## Where the shutdown time goes

A diagnostic build records phase durations, HTTP connection/TLS timings, body
sizes and span counts. It does not record credentials, headers, payloads, span
names or IDs. Diagnostic timings are excluded from the medians above.

One warm core invocation breaks down as follows:

| Boundary | Time |
| --- | ---: |
| Git/default labels | 2 ms |
| Engine connection | 118 ms |
| Core query | 20 ms |
| Dagger client close | 5 ms |
| Trace/logger/metric shutdown | 268 ms |
| Analytics close, afterwards | 236 ms |

Its first Cloud trace request starts around 106 ms, spends 143 ms acquiring a
connection, then about 83 ms between request write and first response byte. A
second request on the reused connection takes about 87 ms. Shutdown waits for
both outstanding work and final data. The previously observed 312 ms is not a
fixed sleep and is not evidence that Dagger client teardown is slow.

The real listing also sends a large final batch. In one instrumented run,
296,197 bytes take 72 ms from connection acquisition to completed write, then
165 ms to the first response byte: roughly 237 ms for that request. These
boundaries include network behavior and overlapping server work. They do not
isolate server CPU or database latency. An initial diagnostic also encountered
a one-second OAuth token check/refresh; that first run is not part of the warm
comparison.

## What the Cloud receiver actually waits for

The local `~/dagger.io` checkout was inspected at
`383e5d38d` (full commit recorded in the evidence). No Cloud server was deployed,
no production server profile was collected, and the currently served code was
not verified against that checkout.

`api/server/handlers.go` routes `POST /v1/traces` through authentication,
subscription and membership checks to `api/otlp/traces.go:TracesHandler`.
Before returning HTTP 201, the handler:

1. Reads and decodes the protobuf, then coalesces duplicate span updates.
2. Converts spans and performs applicable module-use, module-call and priority
   index writes inside the per-span loop.
3. Sends the main span batch to ClickHouse. If a replica is configured, it
   sends to both in parallel and waits for both.
4. Updates the PostgreSQL projection of root-span names.

`InsertSpansAsync` and the per-span `*Async` methods still make synchronous
database calls. Here, async means ClickHouse asynchronous insertion with
`wait_for_async_insert=0`: the API waits for acceptance, not for the later
flush to persistent storage. This is not a durable queue acknowledgment.
GitHub/repository follow-up work already runs in a goroutine after ingestion.

The per-span side writes are a concrete algorithmic opportunity. With M module
records, C module-call records and P priority records, the handler performs
M+C+P serial side-write database calls, in addition to the main batch. Bulk
inserts per destination table reduce those round trips to a bounded number of
batches while preserving O(N) row conversion. This avoids needing one goroutine
per span and avoids losing error/backpressure semantics. The PostgreSQL name
projection is also derived data with a documented ClickHouse read fallback.

Existing `dagger_cloud_api_otlp_request_stage_duration_seconds` histograms cover
decode, main batch preparation and send. They do not separately identify all
per-span side writes, membership checks or the PostgreSQL projection. The next
server measurement should add those boundaries and compare bulk insertion
before changing acknowledgment behavior. The code inspection establishes the
work structure, not how many milliseconds each stage costs in production.

## Async and transport experiments

CLI export already runs asynchronously. Simply returning before its goroutines
finish loses the final trace when the process exits. Removing that wait safely
requires another owner, such as a persistent relay/engine, with an acknowledged
handoff, bounded storage, retries and explicit shutdown behavior. A server-side
early response needs the same ownership decision for essential ingestion.
Derived projections may be deferred under their existing fallback semantics.

Two isolated experiments were measured and are **not enabled**:

* A bounded OTel queue-drain prototype avoids exporting a nearly empty batch
  when the timer expires during an HTTP request. OTel's focused batch,
  shutdown, flush, cancellation, concurrency and metrics tests pass under the
  race detector. It measures 511 ms core and 2.303 s listing versus 512 ms and
  2.290 s for early analytics alone. There is no demonstrated benefit; the
  patch is archived, not added to the dependency.
* HTTP/1.1 Cloud uploads measure 529 ms core and 2.405 s listing versus 519 ms
  and 2.343 s with HTTP/2 in a separate eight-pair series. HTTP/2 remains enabled.
  The upload delay cannot be attributed solely to HTTP/2 flow control.

Payload compression is more promising. A separate diagnostic compresses a
copy locally without changing the bytes sent to Cloud. Its final listing trace
batch shrinks from **356,532 to 64,979 bytes** with gzip BestSpeed, an 82%
reduction, in **2.03 ms elapsed**. The diagnostic JSON calls this duration
`cpu_elapsed_ms`, but it uses a monotonic wall clock; it is not a CPU profile.
Every instrumented Cloud upload in that run returns HTTP 201 without transport
error. No network-latency gain from compression has been measured yet.

The inspected OTLP handlers feed the request body directly into protobuf
decoding, and their router has no request-gzip decoder. Its compression
middleware compresses responses. Client-only gzip would therefore break this
receiver. A coordinated change must add bounded request decompression and
malformed-input tests first, then enable compression in the trace/log/metric
exporters, including token refresh. The compression level should be benchmarked
on both CPU usage and final-upload latency. It does not depend on distributed
result caching.

Raw timings, output checks, timing-only timelines, test logs, prototype patch
and binary/profile hashes are in
[`collections-qa-performance-data/cli-boundaries`](collections-qa-performance-data/cli-boundaries/).
