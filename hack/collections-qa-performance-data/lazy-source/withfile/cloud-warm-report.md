# Warm production-Cloud diagnostic after the pending-source withFile change

The additional series does **not** justify a blanket warm no-regression claim. Four of five ordinary pairs were slower for the candidate. In the separate profiled pair, engine query work was essentially unchanged; most of the CLI difference occurred after the last recorded engine operation. That interval has no Cloud exporter/shutdown instrumentation here, so its cause remains unassigned.

All 12 commands succeeded with the same 14 listing rows and unchanged original fixture. Five alternating ordinary pairs were followed by one separate candidate-first profiled pair. The CLI, normal production endpoint/authentication, command and engine binaries were held fixed. Engines retained different prior histories; no cold claim is made. No additional Cloud commands were run for this analysis.

| Ordinary pair | Order | Baseline | Candidate | Candidate − baseline |
| --- | --- | ---: | ---: | ---: |
| 0 | base → candidate | 3.916 s | 2.743 s | -1.173 s |
| 1 | candidate → base | 2.231 s | 2.345 s | +0.114 s |
| 2 | base → candidate | 2.313 s | 2.325 s | +0.013 s |
| 3 | candidate → base | 2.135 s | 3.232 s | +1.097 s |
| 4 | base → candidate | 2.438 s | 2.830 s | +0.391 s |

Medians: **2.313 → 2.743 s**. The median *paired difference* is **+0.114 s**; it is a different statistic from subtracting the two medians. The earlier separate three-pair Cloud series also had the candidate slower in all three pairs. Neither series establishes whether the cause is the patch, retained history or uninstrumented exit behavior.

| Separate profiled pair | Baseline | Candidate | Difference |
| --- | ---: | ---: | ---: |
| Whole CLI | 2229.8 ms | 2633.0 ms | +403.3 ms |
| CLI start → first recorded engine operation | 134.9 ms | 164.4 ms | +29.5 ms |
| First → last recorded engine operation | 1394.0 ms | 1389.5 ms | -4.5 ms |
| Last recorded operation → CLI exit | 700.8 ms | 1079.2 ms | +378.3 ms |
| Union of session.query intervals | 1366.5 ms | 1363.5 ms | -3.1 ms |

The first/last operation envelope and query union are two views of overlapping work, not additive costs. Same-host CLI and profiler UNIX anchors place all recorded operations inside the command; neither profile dropped events or reported open operations. The roughly 378 ms extra post-operation interval accounts for most of this pair’s 403 ms CLI gap, without identifying its cause.

Both profiles contain **248 session queries, six module runtime executions, seven Git advertisements and 11 Dang telemetry flush phases**. Operation counts are 20,752 and 20,755. The only class-count differences are one extra `Query.__objectTypeDef` call, one extra `TypeDef.withObject` execution and one extra `dagql.publishResult` operation in the candidate. Cache hit/joined counts differ slightly; no additional compilation or execution process appears.

`Workspace.artifacts` changes from 586.5 to 699.0 ms while `Artifacts.__itemsJSON` changes from 760.0 to 647.1 ms. These offsetting discovery/expansion shifts leave the total query union flat. Dang telemetry flushing has 32.8/33.4 ms of union time inside the operation envelope; it is not the unrecorded end-of-command export tail. There are no Cloud, shutdown or exporter phases in either wcprof capture.

Engine CPU medians are **4.970 → 4.406 CPU-seconds**, with no cgroup CPU throttling in any sample. Disk-write median is zero on both sides. The first baseline/candidate calls read 63.5/31.0 MB, then subsequent ordinary calls read roughly 0.34–1.42 MB each; this first-pair storage-read difference is real context, not proof of the 3.916 s baseline cause. One later pair writes 11.2/9.8 MB, which can include delayed background writeback.

Host CPU pressure totals range from about 82–174 ms per command bracket; host I/O pressure is mostly 2.6–5.1 ms after the first pair (56.3/19.1 ms), and memory pressure is negligible. These host-wide counters cannot assign delays to these commands, and CPU/IO/PSI time must not be summed with CLI time. The slow 3.232 s candidate sample does not have unusually high engine CPU, write bytes or recorded host I/O pressure.

A later read-only numeric MemStats snapshot found different lifetime histories (214 versus 163 GCs; 55.5 versus 31.6 GB allocated over each engine lifetime) and roughly 997 versus 649 MB heap allocations at observation. The latest GCs occurred after the profiled commands, and no forced GC was requested. These are **not** per-command deltas and provide no evidence that GC caused the measured warm difference. Per-command GC/heap counters or an aligned runtime trace would be needed to evaluate that hypothesis.

Safe export: `cloud-warm-analysis.json` contains numeric counters, phase durations and operation-class aggregates only. Raw wcprof string tables, call metadata, stdout/stderr, trace IDs and credentials remain outside this evidence export.
