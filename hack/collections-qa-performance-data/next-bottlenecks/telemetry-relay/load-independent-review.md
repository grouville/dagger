# Independent review of the 40-command relay experiment

Reviewed `run_load.py`, `load-driver-review.md`, the relevant counter/transport
code in `main.go`, and only the small numeric result files under
`ts-static-load-v2`. No engine calls, builds, reruns, spool access, credential
access, or administrative requests were made for this review.

The observed CLI improvement is real, but the experiment also demonstrates
accumulating delivery work. It does not establish a production-ready faster
telemetry path or sustained capacity.

## Verified observations

All forty commands exited successfully and produced the exact expected stdout
SHA `c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`.
The sixteen measured isolated commands were balanced by order; four warmups
were excluded. All eight matched pairs had lower async CLI time.

| Boundary | Synchronous forwarding | Durable asynchronous relay |
| --- | ---: | ---: |
| Isolated CLI median, eight commands/mode | 2.188695 s | 1.634452 s |
| Ten-command block, last CLI exit | 23.259916 s | 16.387011 s |
| Same block, complete drain including 200 ms observation window | 23.890012 s | 26.348496 s |
| Last CLI exit to observed stable drain, including observation window | 0.630096 s | 9.961485 s |
| Fully drained block export requests | 488 | 926 |
| Fully drained block HTTP request body bytes | 22,241,833 | 22,554,648 |
| Fully drained block log export requests | 197 | 582 |

The isolated CLI medians improve by approximately 25.3%. In the single pair of
ten-command blocks, all delivery takes approximately 10.3% longer with the
async relay despite earlier CLI exits. The fixed sync-then-async block order
prevents treating that percentage as an order-independent causal estimate.

Async post-exit pending-record samples are
`65, 97, 124, 151, 177, 204, 228, 253, 284, 314`. Their oldest pending age grows
from 0.99 s to 6.74 s overall; individual age samples need not be monotonic.
Serialized spool bytes grow from 1.78 MB to 9.86 MB. These are sampled values,
not continuous peak measurements. CleanupPending is zero at all ten samples,
so the pending records were awaiting upstream acknowledgement, not merely
local deletion. All four async workers were exporting at each sample.

Both blocks start and finish with zero pending records, bytes, cleanup, and
active transports. The async block accepts and delivers all 926 records.
Across the complete experiment Accepted=Delivered=1,864 counts only async
records; the 2,852 total upstream requests also include synchronous forwarding.
No retries, transport failures, storage errors, or non-2xx responses appear.

For all 100 recorded relay snapshots, both accounting invariants hold:

```text
Pending == Accepted - Delivered + CleanupPending
ExportRequests - Export2xx == ExportActive
```

The second equality applies to this error-free trial. The synchronous queue
has zero Pending by construction; it still has one or two active upstream
exports at each burst post-exit sample. Zero synchronous Pending is therefore
not evidence that Cloud delivery has completed at CLI exit.

## Connection setup is not the measured bottleneck

Every upstream export in both measured isolated series and both burst blocks
reuses a connection. Their TCP-connect and TLS-handshake counter deltas are
exactly zero. Mean connection acquisition is below 0.001 ms/request.

| Mean time/request | Sync isolated | Async isolated | Sync block | Async block |
| --- | ---: | ---: | ---: | ---: |
| Start to response headers | 107.36 ms | 101.29 ms | 113.75 ms | 98.23 ms |
| Start to response-body close | 107.38 ms | 101.31 ms | 113.77 ms | 98.25 ms |

The recurring cost is waiting for the upstream response on an already reused
connection. This does not distinguish network RTT from Cloud processing;
server-side timings would be needed for that attribution. Header duration
already includes connection acquisition/TCP/TLS. Aggregate request durations
sum overlapping requests and must not be added to CLI wall time.

Request amplification is consistent across both measurements: isolated totals
396 to 750 requests (+89.4%) and burst totals 488 to 926 (+89.8%). Body bytes
increase only 1.5% and 1.4%, respectively. Log request counts roughly triple.
This is consistent with faster acknowledgements producing smaller export
batches; semantic log/span counts were not recorded, so the counters alone
cannot prove identical telemetry content or locate the batching decision.

## Measurement boundaries and limits

- CLI duration is measured directly around subprocess execution and correctly
  ends at CLI exit. It is a responsiveness result, not a Cloud-completion
  result.
- `relay_at_exit` is a stats response obtained after the exit timestamp. Call
  it a **post-exit sample**; its delay is not recorded. Empty samples cannot
  prove emptiness at the exact instant of exit.
- `delivery_wait_after_exit_seconds` starts later, inside `drained()`, after
  the stats request and output writes. It also subtracts 200 ms. It is an
  **additional observed drain wait**, not an exact exit-to-acceptance latency.
  For the blocks, subtracting `seconds_to_last_cli_exit` from
  `seconds_to_full_drain_including_settle` preserves the actual observation
  boundary, including bookkeeping and the final 200 ms settle window.
- Each isolated command begins after a complete drain. Burst interval deltas
  may include previous commands' exports. Only the fully drained block totals
  provide correctly attributed block-average requests and bytes per command,
  assuming producers do not submit new telemetry after the stable window.
- The 200 ms stable-empty check is an observation window, not proof that a
  producer can never emit a later retry. No protocol-level end marker is
  validated by this driver.
- Ten serial commands demonstrate backlog growth in this observed user loop.
  They do not establish a steady-state arrival/service rate, long-run queue
  stability, behavior at the 128 MiB admission limit, or arbitrary concurrency.
  Async commands offer work more rapidly because they finish earlier.
- Burst order is fixed, synchronous first and asynchronous second. Common
  relay transport state persists across both. The separately balanced pairs
  support CLI latency comparisons better than the one-block-per-mode totals.
- There are bookkeeping gaps between burst commands: observed gaps are about
  4–17 ms for sync and 4–7 ms for async. This is a serial user-loop test, not a
  synthetic zero-gap saturation test. Backlog still grows with those gaps.
- `ExportPeak` is cumulative across modes, not a reset per-block peak. The
  exported requests/elapsed-second metric includes CLI computation, inter-run
  bookkeeping, final drain, and settling; it is not isolated relay capacity.
- Export byte counters measure HTTP bodies, not wire bytes or semantic event
  counts. Pending Bytes measures serialized spool records, a different unit.
- Delivered means async upstream HTTP acceptance with no rejected items in
  the decoded OTLP response, not verified later Cloud storage/rendering.
  Synchronous forwarding records completed 2xx status without independently
  decoding partial-success bodies. This trial records zero response bytes in
  both modes. Neither aggregate equality nor correct CLI output proves that
  every intended telemetry event was emitted, or proves global exactly-once
  delivery across crashes.

## Implication

Keep the measured responsiveness win separate from delivery completion.
Do not present this relay as ready to ship on the basis of faster CLI exits:
the observed loop accumulates outstanding records and nearly doubles upstream
request count for almost the same payload volume. The next candidate should
address batching/backpressure while retaining ordered, durable delivery, then
repeat both exit and fully drained boundaries. More worker concurrency alone
would move more requests to Cloud without removing the amplification.
