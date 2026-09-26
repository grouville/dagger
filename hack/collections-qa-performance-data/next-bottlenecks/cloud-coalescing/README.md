# Isolated Cloud payload coalescing candidate

Status: source overlay and local deterministic tests pass. No live Cloud engine
benchmark has been performed for this change. Do not claim user latency savings.

`WithCallPayloadExportDelay(time.Duration)` configures the existing payload
processor's two burst-coalescing timer arms. Default and nonpositive-option
behavior remains 5 ms. The Cloud pipeline alone opts into the existing
`telemetry.NearlyImmediate` interval (100 ms). The local session DB/client path
keeps 5 ms. Explicit ForceFlush/Shutdown still drain immediately; export batch
bounds, ordering, sequential export, retry backoff, and drop policy are unchanged.

The motivation is possible request amplification with a low-latency durable
relay: faster export completion can prevent records from naturally accumulating
behind an in-flight HTTP call. A 5 ms wake timer may then produce many small
requests. The coalescing option addresses that mechanism without requiring a
relay, changing cache identities or bypassing the final flush barrier.

A deterministic fake-exporter workload emits 40 records at 11 ms intervals.
The original 5 ms setting makes 40 export calls; 100 ms coalescing makes four,
with the same 40 delivered records. This is a deliberately controlled arrival
pattern, **not a measured Cloud amplification ratio**. Real endpoint request
counts, command latency, final drain time, bytes, and Cloud rendering behavior
still need comparison.

Tradeoff: a burst's first Cloud payload can become available up to 95 ms later,
which needs Cloud UX validation. Ordinary Cloud logs/spans already use 100 ms,
but that fact alone does not prove the payload UI tradeoff acceptable. A wider
window can also move pending work into final synchronous flush; warm command
latency must be measured, not inferred from fewer requests.

`TestCallPayload*` passed with this overlay (`unit.log`, 0.215 s), including the
existing suite and new deterministic tests for:

- 100 ms initial coalescing and records arriving during an active export;
- immediate ForceFlush/Shutdown with a one-hour configured delay;
- bounded batches and preserved delivery order;
- unchanged 50 ms retry backoff despite 100 ms coalescing;
- default/zero/negative options retaining the local 5 ms behavior;
- the bounded fake-exporter request-count experiment.

Reproduction:

```sh
CGO_ENABLED=0 go test \
  -modfile=/tmp/collections-perf/post-rebase-io/build.mod \
  -overlay=/tmp/collections-perf/sdk-edit-audit/cloud-coalescing/overlay.json \
  ./engine/telemetry -run '^TestCallPayload' -count=1 -v
```

Files: `prototype.patch`, `overlay.json`, `source-manifest.json`, source/test
copies, `prepare.py`, and `unit.log`. The option was tested through the real
processor and fake exporters; the changed Cloud pipeline has not been rebuilt
as a full engine. Shared source is untouched.
