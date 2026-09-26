# Local durable OTLP relay experiment

This Linux prototype measures a different acknowledgement boundary: the CLI
waits until a private local daemon persists telemetry, then the daemon delivers
it to the original Cloud endpoint. It does not make remote delivery complete
when the CLI exits. `sync` mode uses the same daemon and connections but waits
for the Cloud response. Run commands serially and drain between mode changes.

Build and fake-transport tests, from `/home/dagger/dag`:

```sh
go test -race -count=1 /tmp/collections-perf/telemetry-relay/main.go /tmp/collections-perf/telemetry-relay/main_test.go
go build -o /tmp/collections-perf/telemetry-relay/relay /tmp/collections-perf/telemetry-relay/main.go
```

Launch with the existing private administrative token file and a fresh
task-owned spool directory:

```sh
relay --listen PRIVATE_BRIDGE_IP:6199 --target https://api.dagger.cloud --spool PRIVATE_SPOOL_DIRECTORY --admin-file PRIVATE_ADMIN_FILE
```

Default mode is asynchronous, including after restart. `--paused` persists
accepted requests while suspending outbound work, for the process-crash replay
test. The ready message, errors, and stats contain no request headers or bodies.

Set `DAGGER_CLOUD_URL` to the private bridge endpoint so both the CLI and engine
can reach it. The unauthenticated HEAD probe returns locally in both relay
modes. Thus direct versus synchronous relay includes connection reuse and
probe effects; synchronous versus asynchronous relay is the closer comparison
for changing the acknowledgement boundary.

Administrative endpoints require `X-Relay-Admin` from the private file:

* `GET /relay/stats` returns integer counters and timings.
* `POST /relay/mode?value=sync` or `value=async` changes mode only with an empty
  queue. Do not change mode while a command is running.
* `POST /relay/pause` and `/relay/resume` suspend or resume dispatch. Terminal
  rejected writers remain blocked after resume and across restart.

For every measured asynchronous command, require the exact listing output and
exit status, then separately measure the time to `Pending == 0`, `Bytes == 0`,
and `CleanupPending == 0`. Require `Failed == 0` and `StorageErrors == 0`
throughout. Across a drained trial, new `Accepted` must equal new `Delivered`.
`Delivered` counts fully accepted upstream responses, not just attempted writes.
`OldestPendingNS` and `CleanupPending` are instantaneous gauges; other main
counts are cumulative for this daemon process. Counters restart on restart;
recovered records are included in `Accepted`.

`Recovered` and `RecoveredBytes` are immutable startup counters, captured before
the daemon starts listening. For the SIGKILL replay proof, count JSON files and
sum their file sizes after the killed process has exited; record only those
integers, without reading or archiving filenames or payloads. Require these
counts to equal `Recovered`/`RecoveredBytes` after restart. Current `Pending`
and `Bytes` may already be larger because paused dispatch still accepts new
requests. The final drained snapshot must have `Delivered == Accepted` and
`Accepted >= Recovered`.

## Correctness implemented

* An exclusive OS lock protects spool ownership. On startup, abandoned temporary
  files are removed only after acquiring the lock; durable records and failure
  markers are recovered.
* Acceptance writes mode-0600 records inside the mode-0700 spool, syncs file,
  renames, and syncs directory before returning 200. A rename followed by a
  failed directory sync stays indexed but unacknowledged; a client retry can
  confirm the directory sync without duplicating the record.
* Four workers schedule per-writer queue heads. Only the selected payload is
  read, outside the acceptance mutex. Retry deadlines belong to the writer,
  so another worker cannot bypass HTTP `Retry-After`. Other writers can advance.
* HTTP 429/502/503/504 and I/O failures retry. Permanent rejection, partial OTLP
  success, and invalid encoded success responses create terminal failure
  evidence and block that writer. No accepted subset is repeatedly resent.
* Empty protobuf, gzip, and JSON success responses are understood. Response
  decoding is bounded to 1 MiB. Passthrough preserves the query and strips
  hop-by-hop and administrative headers.
* Once Cloud acknowledges a record, unlink retries never resend its payload.
  A directory-sync failure after successful unlink increments `StorageErrors`
  and fails the trial; it never requeues a nonexistent file.
* Pending record bytes are capped at 128 MiB. Small lock/failure-marker files
  are additional metadata. Recent delivered-key tombstones are capped at 4096;
  restart and tombstone eviction can permit duplicates, matching at-least-once
  delivery. Acceptance ordering remains stable across clock rollback.

## Remaining prototype limitations

This is not an upstream service implementation. Spooling an OAuth Authorization
header freezes an access token; production needs a credential resolver and
rejection/recovery policy. A short trial must drain while its token is valid.
The inbound bridge is a task-private interface, not a generally exposed API.
Mode changes assume an idle producer. The queue metadata scheduler still scans
writer heads; production backlog fairness and metadata budgeting need design.
SIGKILL replay proves process-crash recovery, not physical power-loss behavior.
Disk errors intentionally fail the experiment instead of silently relaxing its
delivery checks. Retained failures require explicit operator investigation.

**Never print, copy, or archive the administrative token or spool contents.**
Archive source, tests, integer stats, listing output, and timings only. Keep a
daemon with pending accepted data available for delivery; stop it only after
drain, or as part of the controlled durable-recovery test.

## Transport counters added after the first measured trial

`relay-v1-source.go`, `relay-v1-source_test.go`, and `relay-v1-validation.json`
preserve the exact source hashes of the original 18-test binary. New transport
counters require a new binary and new measurements; they do not retroactively
supply the missing synchronous request counts from the original trial.

Both relay modes now count `ExportRequests`, `ExportRequestBytes`, response
bytes, status classes, network/read errors, and signal-specific request/byte
counts. `ExportDurationNS` includes response consumption through close;
`ExportHeaderNS` ends when headers arrive. Connection acquisition, connect, TLS,
and reuse counters characterize pool effects without recording destinations.
`ExportPeak` is a process-wide high-water mark, so its delta is not a per-command
peak. `ExportActive` is an instantaneous gauge. Queue starts, age at dispatch,
and payload-read time describe asynchronous replay; repeated attempts count
again. These sums are not disjoint wall-clock components.

Direct mode bypasses the relay entirely. Diagnostic overlays under
`export-counts/` prepare opt-in `_DAGGER_CLOUD_EXPORT_COUNTS=1` counters at the
real CLI/engine export transport for a later all-mode comparison. They must be
built into both binaries and enabled in both processes. Each exporter emits one
`CLOUD_EXPORT_COUNTS` JSON summary on shutdown; fields contain integers and a
fixed signal name, with no IDs, payloads, headers, or destinations. Those
unbuilt diagnostic overlays have not yet been validated and are separate from
the relay's tested counters. Request byte counts are encoded HTTP body sizes;
response byte counts follow the transport's decompression behavior.

## Sustained delivery measurement

`run_load.py --engine ENGINE --trial FRESH_NAME` starts the tested instrumented
relay with a fresh private spool. It runs two unmeasured warm-up pairs, eight
alternating synchronous/asynchronous pairs with a drain between commands, then
ten synchronous and ten asynchronous commands without waiting for Cloud between
commands. Local stats snapshots and output bookkeeping add a small inter-command
gap; no deliberate sleep or drain is inserted in either sustained block.

Isolated pairs provide exact per-command export request and byte totals. In a
sustained asynchronous block, an export during one command can belong to an
earlier command. Interpret per-command snapshots as queue progress; divide the
final fully drained block totals by ten for the average export load per command.
Pending counts, bytes, and oldest pending age after each exit reveal accumulating
backlog. A fast CLI exit must be reported together with final drain time and
Cloud work, not as free end-to-end acceleration.

The driver rejects non-2xx exports, transport/storage errors, terminal failures,
and incorrect listing output. Drained means pending records, bytes, cleanup, and
active requests are zero and cumulative counters have been stable for 200 ms.
It leaves a daemon with pending accepted data running for investigation/delivery.
`relay-v2-source.go`, `relay-v2-source_test.go`, and `relay-v2-validation.json`
preserve the exact instrumented source and 20-test proof.


## Completed instrumented load trial

The explicitly approved forty-command run is recorded in
[the load report](load-v2/report.md), with paired and burst counters, exact-output
checks, complete final drain and process-stop verification. The CLI median improves
2.189 → 1.634 s, but requests increase 1.89× with only 1.52% more body bytes. Ten
consecutive asynchronous commands leave 314 pending batches at the last post-exit
sample. This establishes backlog in that observed workload, not sustained capacity.
[Independent measurement review](load-independent-review.md) documents timer and
sampling boundaries. The earlier approval-rejection JSON is a historical record;
the user subsequently authorized the test and automatic review accepted it.

A separate rotating-writer-cursor correction fixes a locally reproduced fairness
bug; see [the isolated patch](../relay-fairness/README.md). It was not applied to
the measured v2 binary, and no extra Cloud commands were used. The batching review
also explains why a 100 ms delay must not become the ordinary Cloud default without
measuring direct-command latency and recipe visibility.
