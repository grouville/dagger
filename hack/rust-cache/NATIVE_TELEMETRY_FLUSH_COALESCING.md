# Coalesce session telemetry flushes

The improved Go listing still requests a telemetry flush after every Dang module invocation. Each session flush visits every live client metric runtime. A complete listing makes 1,764 session-flush requests and about 1.37 million client metric-flush attempts, despite starting no test workloads.

The prototype combines overlapping requests per session. Every caller receives a ticket after emitting its telemetry. A successful flush covers only tickets issued before it started. Later callers wait for another pass; a failed flush does not satisfy them. Waiting callers can cancel, and canceling the active caller leaves other callers able to retry. Trace, log and metric providers are unchanged.

The deterministic race tests cover late emissions, coalescing, retries and cancellation. Real export checks retain all sixteen emitted spans and log records plus a gauge metric. Existing checks also pass for protected call payloads, bounded Cloud waits and metric-runtime reclamation. Fresh-input Go package ownership and real collection test execution pass. The six native Rust histories remain reusable across the graceful engine replacement.

Two opposite run orders complete successfully with identical 4,398 rows:

| Order | Without coalescing | With coalescing | Client flush attempts without → with |
| --- | ---: | ---: | ---: |
| Control, candidate | 82.99 s | 80.91 s | 1,371,149 → 404,647 |
| Candidate, control | 84.46 s | 82.08 s | 1,365,512 → 508,183 |

Every command uses a new CLI and a fresh Go source edit, with the same selected Go module and ordinary garbage collection. Telemetry remains enabled. The declaration-reuse prototype is enabled in both arms; the known-ID shortcut and metadata read-ahead are disabled. No caches are reset.

Median engine CPU falls from 273.56 to 257.15 seconds and allocated bytes from 43.37 to 40.88 GB. These are cumulative CPU/allocation measurements, not command latency or peak memory. The observed full-command gain is only about two seconds, despite removing most of the redundant flush work. This is a small optimization, not the solution to slow listing. The experiment remains off by default and has no PR.

The first real-export test used an integer counter and failed with coalescing both enabled and disabled. The passing export test uses the gauge format exercised by the existing telemetry suite. Both failed attempts are retained; the counter round-trip issue needs separate investigation.

[Source and complete attempts](experiments/telemetry-flush-coalescing/) preserve the overlays, cancellation tests, exported-signal checks, engine identity, native history checks and all benchmark output.
