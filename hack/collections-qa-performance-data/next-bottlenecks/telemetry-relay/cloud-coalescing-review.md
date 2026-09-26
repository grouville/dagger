# Cloud payload coalescing: candidate after transport-count evidence

Source finding: `engine/telemetry/callpayloadbatch.go` gives every payload
processor the same 5 ms coalescing delay. `run` arms it both on the first wake
and for records that arrive during an export pass. `engine/server/session_cloud_telemetry.go:newCloudLogPipeline`
uses this local-oriented processor for Cloud too, with a 512-record export
limit. Ordinary Cloud logs and live spans use the 100 ms `NearlyImmediate`
interval. An explicit flush/shutdown drains immediately; retry uses a separate
50 ms–2 s exponential backoff.

An approximately 88 ms Cloud request creates implicit producer-side batching:
new payload records accumulate while its previous export is in progress. A
local durable acceptance response in a few milliseconds can remove that
accumulation period. The next 5 ms timer can then issue many smaller requests.
This is a plausible cause, not a measured amplification ratio until the v2
synchronous/asynchronous transport-count trial completes.

If counts confirm amplification, a minimal engine experiment is:

- Add an `exportDelay time.Duration` field to the payload processor, defaulting
  to the existing 5 ms constant.
- Add `WithCallPayloadExportDelay(duration)` as an option; ignore nonpositive
  values consistently with the max-batch-size option.
- Replace the two coalescing timer arms with the configured delay; preserve
  retry timers and explicit ForceFlush/Shutdown behavior.
- Configure only the Cloud pipeline with `telemetry.NearlyImmediate` (100 ms).
  The local client DB and live CLI path keep their existing 5 ms latency.

This does not change payload content, ordering, de-duplication, queue ownership,
retry guarantees, cache identities, or the flush barrier. Cloud may see the
first payload in a burst up to 95 ms later, comparable to its ordinary log/span
publication interval. That tradeoff must be measured, including the final
remote drain and Cloud rendering expectations. Increasing delay must not just
hide additional work after command exit.

Focused deterministic tests can extend the existing `testing/synctest` suite:

1. A configured 100 ms processor has not exported at 5 ms; records emitted
   during that window coalesce into one export at 100 ms.
2. Records arriving during a blocked export wait for the configured window
   after it returns; they do not drain in one-request-per-arrival passes.
3. ForceFlush and Shutdown drain queued records immediately even with a long
   configured delay, while preserving batch bounds and record order.
4. Failed exports retain their retry schedule and ordering; configuring a
   longer coalescing delay does not replace or bypass the retry backoff.
5. Default/invalid-option tests preserve the existing 5 ms local behavior.

No implementation or benchmark of this candidate has been performed by this
review. The v2 trial's isolated pairs will compare exact requests/bytes per
command. Sustained blocks will distinguish a faster CLI boundary from growing
Cloud backlog; interval exports there can belong to preceding commands.
