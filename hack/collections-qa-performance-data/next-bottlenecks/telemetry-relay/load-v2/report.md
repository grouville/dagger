# Durable relay: faster CLI exit, more Cloud requests

The asynchronous relay reduced median CLI listing time from **2.189 s to 1.634 s** (554 ms, 25.3%). But the eight measured asynchronous commands sent **750/396 = 1.89× as many Cloud requests**, with only 1.52% more encoded body bytes. The sustained asynchronous block accumulated a backlog. This is a useful handoff prototype, not yet a production performance win.

The user explicitly approved this forty-command Cloud experiment. Both modes used the same task-owned engine, frozen TS-static greetings fixture, CLI, private relay, original `https://api.dagger.cloud` destination, and normal `check -l --all` command. The synchronous relay forwarded requests and waited for Cloud; the asynchronous relay acknowledged durable local persistence and delivered later. This trial has no direct-to-Cloud arm.

## Isolated commands

Two warm-up pairs are excluded below. Eight measured pairs alternate mode order and fully drain between commands. Timings include complete new CLI execution through exit.

| Metric | Synchronous relay | Asynchronous relay |
| --- | ---: | ---: |
| Median CLI wall time | 2.189 s | 1.634 s |
| Median additional observed drain wait | 0.321 s | 3.962 s |
| Median export requests per command | 49 | 94.5 |
| Median encoded export bytes per command | 2,228,274 | 2,262,939 |

The drain-wait field starts inside the polling routine after post-exit stats/output bookkeeping and subtracts its 200 ms settling allowance. It is **not** an exact CLI-exit-to-Cloud-acceptance interval. The post-exit queue snapshot is likewise sampled after an HTTP roundtrip, not atomically at process exit.

Totals across eight measured commands per mode (integer counts; ratios use totals):

| Signal | Sync requests | Async requests | Request ratio | Sync body bytes | Async body bytes | Byte ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Logs | 157 | 475 | 3.025× | 5,279,662 | 5,363,486 | 1.016× |
| Traces | 127 | 163 | 1.283× | 10,109,614 | 10,296,680 | 1.019× |
| Metrics | 112 | 112 | 1.000× | 2,443,868 | 2,443,868 | 1.000× |
| All | 396 | 750 | 1.894× | 17,833,144 | 18,104,034 | 1.015× |

Logs account for most request amplification: 157→475 requests while log body bytes grow only 1.6%. Metrics are unchanged. Request bytes are HTTP body sizes, not total network traffic including headers/TLS. These counters measure exported work; they do not measure Cloud CPU cost.

## Ten-command bursts

The driver ran ten synchronous commands followed by ten asynchronous commands. There was no intentional sleep or Cloud drain between commands inside a block; local stats and output bookkeeping introduce a small gap. Each block drained fully afterward. Fixed block order is a limitation; do not interpret this single pair as a stable throughput estimate.

| Metric | Synchronous block | Asynchronous block |
| --- | ---: | ---: |
| Wall time through last CLI exit | 23.260 s | 16.387 s |
| Additional observed drain wait | 0.426 s | 9.753 s |
| Complete observed block, including stable-zero window | 23.890 s | 26.348 s |
| Export requests | 488 | 926 |
| Encoded export body bytes | 22,241,833 | 22,554,648 |
| Pending requests at final post-exit sample | 0 | 314 |

Synchronous `Pending == 0` reflects bypassing the durable queue; its post-exit samples still contain 1–2 active upstream requests. Asynchronous post-exit samples contain four active upstream requests throughout this block. Zero pending alone would therefore be an insufficient full-drain check.

The asynchronous block reached its last CLI exit sooner but reached the complete observed delivery boundary later: **26.348 s versus 23.890 s**, both including the 200 ms stable-zero interval. All asynchronous pending records eventually drained.

| Async command | CLI duration (s) | Pending at post-exit sample | Pending bytes | Oldest pending age (s) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.597 | 65 | 1,783,710 | 0.992 |
| 2 | 1.770 | 97 | 2,312,789 | 2.417 |
| 3 | 1.564 | 124 | 3,413,590 | 3.499 |
| 4 | 1.559 | 151 | 4,536,095 | 3.346 |
| 5 | 1.641 | 177 | 5,565,013 | 3.593 |
| 6 | 1.599 | 204 | 6,482,615 | 4.849 |
| 7 | 1.644 | 228 | 7,264,830 | 5.197 |
| 8 | 1.806 | 253 | 7,902,185 | 5.349 |
| 9 | 1.572 | 284 | 9,151,037 | 5.523 |
| 10 | 1.592 | 314 | 9,856,241 | 6.738 |

Interval export counts during a burst can include earlier commands. Only the final drained block totals provide exact per-command averages. Queue growth is observed here; no unbounded steady-state extrapolation is claimed.

## Correctness and lifecycle

- **40/40** commands returned the exact expected listing and exit status: four warmups, sixteen measured-pair commands, and twenty burst commands.
- Final asynchronous counters: **1864 accepted = 1864 delivered**. Synchronous forwarding accounts separately for **988** requests; it does not increment durable acceptance/delivery counters.
- Across both modes, **2852 export requests = 2852 completed 2xx responses**. Response bodies were empty; no transport errors, non-2xx responses, retries, terminal failures, or storage errors were recorded.
- Final pending records, bytes, cleanup, and active transports were all zero. The driver exited successfully and its own relay process was confirmed stopped. The benchmark engine was left running and unchanged.
- The existing v2 source passed twenty race-enabled local fake-transport tests before the run. This trial adds measured load evidence, not a new crash-recovery proof; the prior v1 SIGKILL replay proof remains separate.
- Cloud acceptance does not prove subsequent rendering, and at-least-once replay does not promise global exactly-once delivery. No tokens, config, payloads, or private spool were read for analysis or archived.

## Connection and accounting evidence

All measured pairs and both sustained blocks reused existing upstream connections: 100% reuse with zero new connect/TLS counters. Mean response-header waits were approximately 98–114 ms per request; connection acquisition was below 0.001 ms per request. Connection setup is therefore not the recurring cost in these samples. The counters do not separate network transit from Cloud server processing.

All 100 saved command snapshots satisfy both `Pending = Accepted − Delivered + CleanupPending` and `ExportRequests − Export2xx = ExportActive`. The independent read-only audit is `../load-independent-review.md`.

## Next upstream direction

The data supports investigating producer batching before increasing replay concurrency. The existing call-payload processor coalesces for 5 ms, including on the Cloud path; ordinary Cloud logs/spans use 100 ms. Fast local acknowledgements plausibly remove the approximately one-network-roundtrip accumulation window, producing smaller payload batches. Transport counts establish amplification by signal, but do not yet attribute each individual log request to a particular processor.

A focused candidate is a configurable payload coalescing delay: retain 5 ms for local client persistence, use 100 ms only for Cloud, and keep ForceFlush/Shutdown immediate plus retry ordering unchanged. The prepared option already has deterministic local tests. A universal 100 ms Cloud default is not justified: it can move a short direct export into shutdown and worsen latency. First evaluate the option on an explicitly known asynchronous-acceptance path; keep ordinary direct Cloud unchanged until separately measured. See the source-backed `../../cloud-coalescing/correctness-review.md` in the archive. No such delay change is included in this measurement. Longer term, reuse the engine’s telemetry store for durable handoff with an explicit durability/checkpoint/authentication contract rather than upstreaming this separate JSON-spool service as-is.

## Reproduction and provenance

- Driver: `../run_load.py`; exact source hash in `provenance.json`.
- Raw integer samples: `results.json`; paired and burst summaries in their corresponding JSON files.
- Independent output/accounting/process checks: `verification.json` and `process-stop-check.json`.
- CLI SHA-256: `aea19ce8b7849905113c388b353b6a686aca6a55fbb0fe714f406a5bb8d2356d`.
- Root fixture `dagger.toml`/`dagger.lock` hashes were added to `verification.json` only after the run; the original driver did not capture these before execution. The earlier fixture/engine manifest is `/tmp/collections-perf/sdk-edit-audit/ts-static/engine-manifest.json`.
- Frozen engine SHA-256, checked before launch: `a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5`.
- Relay SHA-256: `c8bd428bd08c2ad2d6fc36ff90469a8e75f4a5a7e5deb5aad258112868593ae5`.
- Relay source SHA-256: `e84947c852c45aa911b490f993ec80fde7696b48e79c9389f995b149d5c20af9`.
- Relay tests SHA-256: `51452265740534b6ce940ecc91431c6968c06e5b2d92e0f5576ee34b25abc4a6`.
- Source/test/proof archive: `../relay-v2-source.go`, `../relay-v2-source_test.go`, `../relay-v2-validation.json`.
- Expected stdout SHA-256: `c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`.
