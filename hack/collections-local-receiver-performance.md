# Measure telemetry against a local Cloud receiver

The initial 24-command receiver experiment ran locally, with **no telemetry sent
to production Cloud**. A subsequent matched comparison used seven ordinary
production commands; its results are below. One CLI command can produce many exports:
the three measured greetings-api listings sent 90, 93 and 93 POSTs each.
Command count alone is therefore a poor load limit.

The experiment uses the real API OTLP handlers, organization-token authentication,
subscription checks and PostgreSQL/ClickHouse stores. It does not instantiate
the full Cloud application, JWT/OIDC startup, workers or external integrations.
The receiver and fresh databases run on an internal Docker network. The owned
benchmark engine temporarily joins that network; its original routes are
verified before and after. No existing Cloud token or database is reused.

The API is limited to 2 CPUs/1 GiB, PostgreSQL to 2 CPUs/2 GiB, and ClickHouse
to 4 CPUs/4 GiB. This is a local ingestion experiment, not a production capacity
or network-latency benchmark. The private API source, harness, credentials,
database records and raw profiles remain outside the public repository.

## Warm command overhead

Twenty-four commands cover six warmups and three alternating pairs for each
flow. Both sides use the same CLI, retained experimental engine and copied
greetings-api source. One side disables external export; the other sends normal
telemetry to the real local receiver. This isolates local export overhead; it
does not compare an implementation before and after an optimization.

| Flow | Export disabled | Local API enabled |
| --- | ---: | ---: |
| Core `api call version` | 377 ms | 378 ms |
| `dagger ws ls` | 232 ms | 237 ms |
| `dagger check -l --all` on greetings-api | 1,444 ms | 1,573 ms |

Values are medians of three unprofiled samples per side, from process spawn to
a dedicated blocking waiter's observation of exit. The listing samples vary:
1.43–1.90 s disabled and 1.56–1.79 s enabled. Three pairs do not establish a small
percentage effect. The exact 14-row listing matches throughout, other outputs
match between modes, and source hashes are preserved. Two separate wcprof
captures have zero dropped events and zero open operations at capture.

The receiver observer must distinguish CLI exit from later engine completion.
A calibration saw one trace export after a core command exited. A scoped local
database query confirmed that its only span was `wcprof.session_complete`.
The engine emits this carrier during background session reaping. It was not
an export from the following command with telemetry disabled.

Measured samples consequently have a bounded 250 ms observed quiet interval
between them, outside the CLI timer. That wait is recorded separately. It is
not a proof that every asynchronous task has drained, and these are isolated
warm invocations rather than a sustained maximum-throughput loop.

The separate core profile records 21,489 operations in a 222 ms engine interval;
the final version query itself takes about 0.4 ms. The CLI first loads the full
type-definition graph in [module_inspect.go](../internal/cmd/dagger/module_inspect.go).
This is a concrete target for requesting less metadata. Overlapping operation
durations are not an additive CPU or latency budget. In the listing capture,
six runtimes overlap across 449 ms of a 1.96 s engine interval; reducing runtime
startup alone would still leave other work.

## Matched local versus production comparison

A separate series alternates five warm pairs of the exact same
`dagger check -l --all` command on the same greetings-api copy, CLI binary and
retained engine. It uses the unchanged local receiver binary and the real
`https://api.dagger.cloud` endpoint. No builds or competing benchmark runs occur
during the series. Exact 14-row output and preserved source hashes pass for
every listing.

| Endpoint | Median | Minimum–maximum | Samples |
| --- | ---: | ---: | ---: |
| Real local ingestion | 1.721 s | 1.593–2.314 s | 5 |
| Production Cloud | 2.064 s | 1.950–2.261 s | 5 |

The observed median difference is **344 ms, or 16.7% of production time**.
The median paired difference is 357 ms. Local was slower in two pairs, so this
is a noisy matched estimate, not a guaranteed saving. Use these paired-series
numbers to compare endpoints; the earlier local-only median of 1.57 s came
from a different series.

The comparison includes one initial production core call verifying normal
Cloud authentication, two listing warmups, and ten measured listings. That
is **seven production commands**, paced with at least one second between
commands, plus six local commands. Listing diagnostics remain empty as in the
normal UX. The owned engine's corresponding log window contains no telemetry
warnings/errors or rate-limit warnings; this is not server-side delivery proof.

Production uses the normal existing CLI login. Local mode uses an empty CLI
configuration and its generated organization token. Analytics and update checks
are disabled on both sides. The observed difference therefore combines network,
TLS, authentication and receiver/deployment behavior; it does not isolate WAN
latency or server CPU. These are warm experimental-stack timings, not cold-start
results or timings from a released engine.

The actual target remains **2.064 s to 0.500 s in production**: about **1.56 s
still to remove**. Moving the receiver nearby is useful for isolating costs,
but the local result itself remains more than a second above the target.

## Acceptance, stored data and limits

The measured interval contains 433 POSTs: 120 trace, 257 log and 56 metric
requests. Every POST returned 201; the observer lost no records and saw no
requests during the settled exporter-disabled controls. Median handler times
were 6.8 ms for traces, 3.6 ms for logs and 4.2 ms for metrics. These overlapping
durations must not be added to infer CLI latency.

The real receiver uses asynchronous ClickHouse insertion. HTTP 201 establishes
acceptance, not durable storage. Before the CLI trial, invalid-token rejection,
valid-token authentication and exact synthetic trace/structured-log readback
passed. Both synthetic records were visible 145 ms after the final acceptance,
with a 50 ms polling interval; this is one diagnostic, not a distribution.

After the real trial, all 257 log export keys were visible, with 7,556 rows.
Of these, 5,684 had the real call-payload content-type marker and a nonempty raw
body. This demonstrates transport presence, not semantic validation of every
call. Some earlier trace export keys were no longer visible. The trace table
can replace previous span updates, so request-key counts alone cannot prove
loss or completeness. Metric rows lack export-key attribution. No full-workload
durability or completeness claim follows from the counters.

Two observer assumptions were corrected during calibration and their original
evidence retained privately: the CLI intentionally permits 401 from its
unauthenticated reachability HEAD, and real call payloads are identified by
content type rather than the synthetic log's chosen scope name. Neither
calibration is included in the timing comparison.

The local API and databases were stopped after readback; their volumes and
evidence were preserved, and the engine's original network attachments restored.
Shareable numeric evidence is in
[local-receiver/summary.json](collections-qa-performance-data/next-bottlenecks/local-receiver/summary.json).

## What this establishes

Core calls and workspace navigation can finish below 500 ms while using the
real local ingestion path. The mixed-SDK listing remains about 1.5 s even with
nearby ingestion, so eliminating remote export latency alone will not reach
the target. Continue reducing module/schema work and allocation, while testing
batching or asynchronous handoff locally. The matched production check above
provides the current real-endpoint baseline for validating further changes.

These are warm results on the retained experimental SDK stack. They do not
change the previous cold-start findings or predict Kyle's machine timings.
