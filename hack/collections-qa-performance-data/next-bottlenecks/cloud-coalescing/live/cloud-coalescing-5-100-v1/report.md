# Cloud coalescing: reduce downstream work without claiming a faster normal CLI

**100 ms coalescing helped the asynchronous relay’s delivery workload; it did not demonstrate faster synchronous CLI execution. Do not enable it as a global Cloud default.** The only code change is a configurable call-payload coalescing window, defaulting to the existing 5 ms; this isolated candidate selects 100 ms for Cloud only. Local client persistence, batch limits, retries, ordering, cache behavior and explicit flush/shutdown remain unchanged.

## Matched warm results

Four alternating 5/100 ms pairs per transport; two warm-up commands per configuration excluded. Both transports use the unchanged v2 relay and same original Cloud destination. Synchronous forwarding waits for Cloud and exposes request counters; it is not the direct-to-Cloud connection path. Whole CLI times include startup through exit. The complete observed boundary also waits for zero pending/active exports and a 200 ms stable-zero window.

| Transport | Delay | Median CLI (s) | Median complete observed boundary (s) | Total exports across 4 commands | Total encoded body bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| sync | 5 ms | 2.347 | 2.972 | 180 | 8,899,507 |
| sync | 100 ms | 2.377 | 2.840 | 182 | 8,935,416 |
| async | 5 ms | 1.596 | 5.580 | 371 | 9,063,555 |
| async | 100 ms | 1.589 | 2.957 | 244 | 9,001,386 |

For async acceptance, requests fell 371→244 (34.2%), while median CLI time stayed essentially flat 1.596→1.589 s. The complete observed boundary improved 5.580→2.957 s. For synchronous forwarding, requests 180→182 and CLI 2.347→2.377 s show no gain; four samples do not establish a small regression either. The first sync pair was 2.042→2.178 s, illustrating why fewer wake-ups must not be assumed to reduce foreground latency.

Per-signal totals across four measured commands (5 ms→100 ms):

| Transport | Signal | Requests 5 ms | Requests 100 ms | Body bytes 5 ms | Body bytes 100 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| sync | Logs | 71 | 71 | 2,639,259 | 2,637,632 |
| sync | Traces | 53 | 55 | 5,049,472 | 5,058,084 |
| sync | Metrics | 56 | 56 | 1,210,776 | 1,239,700 |
| async | Logs | 236 | 108 | 2,680,205 | 2,646,480 |
| async | Traces | 79 | 80 | 5,150,258 | 5,144,130 |
| async | Metrics | 56 | 56 | 1,233,092 | 1,210,776 |

## Repeated-command delivery

One ten-command block per configuration, no inter-command remote drain. Block order was async 5 ms, async 100 ms, sync 100 ms, sync 5 ms, so this is observed finite-burst behavior, not a replicated steady-state throughput claim. Small local sampling/output gaps exist in both configurations.

| Transport | Delay | Last CLI exit (s) | Complete observed block (s) | Exports | Pending first→last post-exit sample |
| --- | ---: | ---: | ---: | ---: | ---: |
| async | 5 ms | 15.906 | 25.959 | 917 | 58→324 |
| async | 100 ms | 16.546 | 19.045 | 636 | 30→66 |
| sync | 100 ms | 23.520 | 23.954 | 458 | 0→0 |
| sync | 5 ms | 24.809 | 25.225 | 464 | 0→0 |

Async full-block time fell 25.959→19.045 s (26.6%). Queue growth was reduced, not eliminated: 58→324 pending batches at 5 ms versus 30→66 at 100 ms. The latter still accumulates work; increasing worker count has not been tested or used to hide it. Sync pending is always zero because it bypasses the durable queue; active upstream requests are separately included in the drain condition.

| Command | Async 5 ms pending | Async 100 ms pending | Oldest 5 ms (s) | Oldest 100 ms (s) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 58 | 30 | 1.050 | 0.739 |
| 2 | 89 | 38 | 2.090 | 0.898 |
| 3 | 118 | 42 | 3.198 | 0.939 |
| 4 | 147 | 43 | 3.395 | 0.942 |
| 5 | 170 | 44 | 3.509 | 1.094 |
| 6 | 198 | 42 | 4.674 | 0.943 |
| 7 | 228 | 49 | 4.962 | 1.118 |
| 8 | 257 | 54 | 5.115 | 1.713 |
| 9 | 290 | 54 | 5.599 | 1.814 |
| 10 | 324 | 66 | 6.637 | 2.008 |

## Profiling and boundaries

Four separate profiled commands preserve CPU/runtime traces and wcprof captures; they are excluded from the paired timing statistics. Each wcprof capture has zero dropped events and 248 `session.serveQuery` operations. The async query-interval unions are 1.335 s at 5 ms and 1.384 s at 100 ms in these single profiles: this change does not remove discovery work. Nested durations are not added together. `wcprof-phases.json` documents the union calculation; `wcprof-index.json` documents the dump’s flush semantics. Transport counters provide the direct evidence for Cloud work and drain behavior.

Engine startup-to-ready was 1.91 s for the candidate and 3.77 s for control, outside all CLI measurements and followed by warm-ups. This is an existing-volume restart, not a new-volume cold-start benchmark. Host/engine I/O-full pressure, device read/write counters, and dirty/writeback snapshots accompany every invocation; compilation, binary backups/copies and restarts occurred outside measurements.

| Configuration | Measured CLI samples | Host I/O-full total (s) | Engine I/O-full total (s) |
| --- | ---: | ---: | ---: |
| sync/5 ms | 4 | 0.006785 | 0.000000 |
| sync/100 ms | 4 | 0.017884 | 0.001439 |
| async/5 ms | 4 | 0.074438 | 0.000800 |
| async/100 ms | 4 | 0.050723 | 0.000611 |

Post-exit snapshots are sampled after process exit, not atomic exit-state measurements. This driver records that sampling delay explicitly. Unlike the earlier relay driver, complete-boundary and exit-to-stable-zero fields now retain all elapsed bookkeeping and the full 200 ms stable window. They prove an observed empty state after accepted responses, not Cloud rendering or global exactly-once delivery.

## Correctness and proposed disposition

- 68/68 exact listing outputs and successful exits: 8 warmups, 16 measured commands, 40 burst commands, 4 profiled commands.
- 4246 exports completed with 2xx responses; 2625 asynchronous accepted records were delivered. Synchronous forwarding accounts separately for 1621 requests. Final pending/bytes/cleanup/active/error/retry counters are zero; own relay stopped with exit 0.
- 23 focused local top-level tests passed, including configured/default delay, immediate flush/shutdown, retry backoff, bounded batch order, queued once-per-digest claims, and cleanup emissions after initial flush. The unchanged relay had its separate 20 race-enabled fake-transport tests.
- Original task-owned binaries were backed up and verified before replacement; both volumes and the frozen control executable were preserved. Candidate SHA and source/fixture/CLI hashes are in provenance and validation files.
- Archive the configurable-delay prototype and keep the existing 5 ms behavior in normal source. Do not add an unused public option or ship the experimental 100 ms global Cloud selection solely on this experiment. A known durable-acceptance transport can evaluate it explicitly; do not guess that localhost URLs have that contract.
- Wider batching can postpone first recipe availability by up to 95 ms, unmeasured in the Cloud UI here. Prefer eventual engine-owned durable record handoff that forms larger remote batches after local acceptance; the current packet spool freezes producer batch boundaries.
- No 25 ms search was run: 100 ms did not prove a meaningful direct-latency benefit or a large consistent regression, and another arbitrary window would not resolve the architectural transport distinction. More ordinary-transport samples and recipe-visibility checks are needed before choosing a default.

Artifacts: `results.json`, `paired-summary.json`, `burst-summary.json`, `verification.json`, `provenance.json`, `wcprof-index.json`, `wcprof-phases.json`; sources and test proof are one directory above. Archive only these, expected command output, and optional compressed wcprof captures. Never archive relay config, token, or private spool.
