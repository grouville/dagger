# Cloud coalescing review: delivery and critical-path tradeoffs

Read-only review after the local processor tests; no extra live Cloud calls.
The option is a plausible request-count improvement, not yet an upstream-ready
100 ms default for Cloud.

## Delivery ownership

The local producer claim store is **per (recipe digest, client route target)**.
`claimCallPayload`, `takeCallPayloadForWrite`, and `settleCallPayload` in
`engine/server/session.go` move targets through claimed→writing→delivered, or
release failed writes. `sessionLogExporter.Export` in `engine/server/telemetry.go`
settles only the client DB writes it attempted. The proposed delay changes none
of these operations: local processing remains 5 ms.

Cloud instead uses `cloudPayloadOnce` in
`engine/server/session_cloud_telemetry.go`: it marks the digest seen when handed
to the Cloud processor, **before remote delivery**. The lossless ingress queue
and its retry worker therefore own that record from then on. A repeated payload
from a nested CLI or another producer does not rescue a lost queued copy. The
prototype preserves this existing ownership and does not clear claims, introduce
another transport, drop queue entries, or change retry backoff/max attempts.
Its slightly longer in-memory residence increases the unexported window before
a process crash, as any longer batching window would.

The payload processor clones records at ingress; the queue does not rely on the
module runtime remaining alive. One worker preserves the observed payload queue
order; failed batch plus remaining tail are prepended ahead of newly arriving
records. Wider coalescing does not reorder that queue. Ordinary logs use another
queue through a shared serial exporter; spans use another exporter. There is
**no existing global payload-before-span or payload-before-ordinary-log ordering
barrier**. Matching both intervals at 100 ms does not create one.

## Visibility and cleanup

A span can become visible before a recipe dependency arrives. A 100 ms payload
window can increase that interval by up to 95 ms before contention/network/retry
costs. Cloud rendering must handle eventual recipe arrival; this source review
has not validated the Cloud UI's refresh behavior. Do not describe matching the
span/log interval as proof of UI equivalence.

The main client explicitly flushes Cloud while token-refresh attachables are
available, then begins closing and stops services. Cleanup can still emit new
telemetry after that first flush. The final session telemetry barrier runs after
producers/cleanup are drained and shuts down providers. Cloud pipeline Shutdown
stops and drains the payload worker before shutting down its shared exporter.
Both ForceFlush and Shutdown bypass coalescing timers; the prototype preserves
those barriers. It does not detach work from the session or extend credentials'
lifetime. Existing outage bounds, retry exhaustion losses and the requirement
that producers stop before final Shutdown remain unchanged.

Additional prepared fake-transport tests (`session_coalescing_test.go`,
`server-test-overlay.json`) cover the Cloud once-per-digest wrapper itself:
queued duplicates, first explicit flush, new cleanup payload after first flush,
final shutdown before its timer, and retry ownership when duplicate emissions
are suppressed. **Prepared only; not executed during the exclusive live trial.**

## Why normal direct Cloud can become slower

Coalescing amortizes requests only if new records arrive in its window. It can
also remove useful overlap with actual work. Example with one payload at t=0,
80 ms HTTP latency, command work ending at t=90 ms:

- 5 ms delay: export starts at 5 ms, finishes at 85 ms; final flush at 90 ms is done.
- 100 ms delay: final flush at 90 ms starts the pending export immediately; the
  command now waits until 170 ms.

This example is a model, not a measured Dagger result. It shows why unchanged
immediate flushing does not guarantee unchanged command latency. Several short
payload bursts and shared ordinary-log export contention can make the outcome
less obvious. More records can also be queued at shutdown, increasing memory and
final-drain work, even if total requests decrease. A fast relay response is the
case most likely to expose 5 ms request amplification; normal direct Cloud has
natural coalescing during each in-flight HTTP call already.

## Smallest useful next matched experiment

Use results of the approved 40-command relay trial to decide whether request
amplification exists. Do not change the engine mid-trial or spend unused commands
on another configuration without coordinating its stated scope.

1. First run the prepared wrapper tests locally, plus a deterministic fake
   exporter matrix with both near-zero and observed HTTP service times. Keep the
   same ordered arrival schedule and workload completion timestamp. Compare
   request count, bytes/records, first payload availability, last payload delivery,
   and time blocked in final flush. Include a last burst <100 ms before finish.
   This can falsify the direct-Cloud benefit without live requests.
2. If live counts justify it, the smallest convincing wall test is **four
   alternating matched pairs per transport** (5/100 ms,100/5 ms repeated), with
   unchanged frozen engine/module/CLI and unchanged payload batch limit. Test
   direct Cloud separately from asynchronous relay: eight direct commands plus
   eight relay commands. Warm-up commands, if needed, count explicitly toward
   any approved limit. Keep paired exact output checks and drain each session's
   telemetry before assigning it delivery metrics.
3. Record per-command payload and ordinary-log requests/bytes, trace requests,
   command time, actual query completion, Cloud-flush duration, receipt and remote
   completion timestamps, retry/drop counters, and final queue depth. Use medians
   and raw pairs; verify no missing/duplicate payload digests and no retained
   queue after drain. Do not treat fewer HTTP calls as a latency win by itself.
4. Ship a Cloud default only if it reduces meaningful request work without
   materially worsening direct command latency or first recipe visibility.
   Otherwise retain the generic option but configure it only for a transport
   whose explicit contract and measurements justify the wider window. Avoid
   guessing that arbitrary localhost URLs are durable/fast relays.

A 25–50 ms compromise or full-batch immediate wake is a later experiment if the
5/100 ms comparison exposes the expected tradeoff, not part of the current patch.

## Record outbox versus durable HTTP packet spool

The current relay persists already formed HTTP requests. It correctly preserves
the exporter packet's sequence, identity and retry unit, but therefore also
preserves any too-small packet boundaries caused by fast local acknowledgement.
Durability and concurrency remove remote waits from the command; they do not
undo request amplification. Increasing relay workers can mask that cost while
raising Cloud concurrency rather than removing work.

An engine-owned **record outbox** can accept immutable telemetry records through
a durable checkpoint and form bounded OTLP requests at delivery time. Its remote
worker can read the next committed row range, accumulate a batch, publish, and
advance a durable acknowledgement cursor only after a valid remote response.
That separates local acceptance latency from remote batch size. Existing client
stores are a possible source, but their current flush/spill behavior is not a
crash-durable acknowledgement contract; see the parent `engine-handoff-review.md`.
Pins/cursors, storage quotas, final producer completion, retained credential
rights, retry/partial-success policy and restart behavior remain required.

Batches must stay within compatible tenant/auth, writer/export sequence, signal,
and resource/scope semantics. Preserve per-writer record order and use a stable
idempotency identity for each retried delivery batch. A receiver-visible export
sequence cannot simply be discarded when combining stored packets. Arbitrary
concatenation of serialized OTLP bodies is not a correct substitute for this
record-level design. Decoding/merging packets in the relay would introduce a new
OTLP batching/acknowledgement layer and needs its own protocol proof; it is not
part of the minimal delay option.

The smallest next candidate is therefore **an explicit experimental choice on a
known asynchronous-acceptance pipeline**, using the existing positive-delay
option and leaving ordinary direct Cloud at 5 ms. The matched experiment can
select this option on an isolated engine whose driver routes to the known async
relay; the driver controls that fact, rather than the engine guessing from the
URL or HTTP status. A production setting would need an explicit negotiated
acceptance contract/capability or configured transport policy before selecting
a wider window. Even for the relay, shifting batches earlier in the engine can
increase durable-acceptance delay by up to 95 ms, so measure the final command
boundary as well as requests. The preferred eventual architecture batches
committed outbox records at remote delivery, retaining quick local durable
acceptance without forcing every producer to wait out the remote window.

## Relay fairness observation (source only)

`relay-v2-source.go:next` scans the `writers` slice from index zero for every
selection. `finish` removes a writer only when its queue empties. Earlier writers
that remain ready can therefore repeatedly get the available workers before
later writers. Per-writer FIFO is preserved, and retry-blocked writers are
skipped, but bounded fairness across ready writers is not guaranteed. With a
sustained arrival stream and enough early ready writers, later writers can wait
arbitrarily long. This is not proof that fairness explains the live trial.

A future focused fake test should keep early writers nonempty while a later
writer has work, then assert that the later writer receives service after a
bounded number of earlier completions. A rotating selection cursor/ready deque
can preserve each writer's FIFO without preferring slice insertion order.
Do not change worker count, fairness, delay, and persistence simultaneously in a
matched experiment; they answer different performance questions.
