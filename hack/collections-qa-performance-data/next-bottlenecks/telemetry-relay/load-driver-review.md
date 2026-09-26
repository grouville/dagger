# Instrumented load-driver audit

The prepared driver measures forty serial normal listing commands: four
warmups, sixteen balanced sync/async measurements, and two ten-command blocks.
This pre-run audit is retained after the explicitly authorized experiment completed. See `ts-static-load-v2/report.md` and `load-independent-review.md` for measured results and subsequent boundary checks.

Accounting checks already present:

- Exact expected stdout plus exit status for every invocation.
- No terminal/storage/transport errors or non-2xx export responses.
- Final asynchronous accepted delta equals delivered delta and is positive.
- Export request delta equals completed 2xx response delta and is positive in
  either mode.
- Drain requires zero pending records, bytes, cleanup, and active transports;
  cumulative counters must remain stable for 200 ms.
- Burst snapshots record queue count, bytes, and oldest age. They are interval
  counters, not a false attribution of preceding-session exports to the current
  command. Final drained totals divided by ten give exact averages.
- Engine/workspace/CLI references match the preceding trial. The new driver
  does not restart, replace, or delete the engine. Only its own drained relay
  process is stopped; a pending/unknown delivery state preserves it.
- Binary and source hashes must match the archived 20-test v2 validation.
  The configured destination must remain the original api.dagger.cloud.

Limits of these checks:

- HTTP acceptance proves reception, not successful later rendering/storage by
  Cloud. The relay rejects partial success but does not query Cloud afterward.
- Two hundred milliseconds of stable emptiness is an observation window, not
  a protocol proof that a disconnected producer can never submit a later
  retry. Dagger's completed CLI/engine session barriers are still relevant.
- Deduplication tombstones are bounded. At-least-once delivery remains the
  guarantee across crash or tombstone eviction; equal counters alone do not
  prove global exactly-once delivery.
- Startup checks child liveness plus empty fresh stats. A process-instance ID
  in stats would make ownership checks stronger if concurrent launch attempts
  ever became part of the experiment. The current exclusive slot avoids that.
- Local stats/file bookkeeping adds a small gap between burst commands. Start
  and exit timestamps preserve that gap, and both modes use the same harness.
- A ten-command burst can demonstrate growing backlog. It cannot by itself
  establish steady-state throughput under arbitrary offered load.

# Safe fake-upstream sustained test proposal

Use the existing in-process `testTransport` and synthetic three-byte bodies;
no Dagger engine, workspace payload, actual credential, or network endpoint.
Prepare ten synthetic sessions with separate ordered trace/log writers. Block
upstream responses behind a channel while accepting a bounded finite burst.
Assert that four workers never produce more than four simultaneous transports,
that accepted entries remain pending with correct byte accounting, and that a
writer's second request cannot overtake its first. Release responses, verify
per-writer ordering and exact body/header forwarding using synthetic values,
then require every accepted record delivered and the queue fully empty.

Add a quota-boundary case by making the spool limit injectable in tests, using
small records and a tiny limit. Fill the budget, require the next submission to
return 503 without an accepted increment, drain enough capacity, and retry the
same synthetic request successfully. That proves bounded admission and no
false acceptance without a 128 MiB disk fixture. Include cancellation/restart
with a pending finite burst using the already-tested recovery path.

This test would establish scheduling, admission, and delivery invariants; it
would not substitute synthetic transport latency for measured Cloud behavior.
Operationally, if arrival rate exceeds service capacity, the queue grows until
admission applies backpressure. More workers are not a correctness fix for
batch amplification. A Cloud-only coalescing option is the candidate to test
once actual request/byte ratios show whether amplification occurs.
