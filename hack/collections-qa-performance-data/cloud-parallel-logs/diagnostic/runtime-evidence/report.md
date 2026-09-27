Independent session log exporters: passive transport diagnostic

Keep this candidate isolated. The ordinary 32-command Cloud comparison was mixed, including three artifact-listing regressions. This follow-up proves that the split writers overlap and that the artifact request stream becomes more fragmented in this sample; it does not establish a general latency improvement or prove the cause of the earlier regressions.

Both engines use frozen HEAD 21939, the same lazy-core/SDK/Dang/source-lazy stack and the baseline span serializer. The only behavior difference is the independent ordinary-log/payload-log exporters. Both carry the same passive numeric hooks. Each individual exporter stays serial; the candidate permits two simultaneous log exports. The four-resource race test separately verifies that spans, ordinary logs, payload logs and metrics drain and shut down once.

Eight calls passed: two local generation primers, two local artifact primers, one Cloud generation pair, and one reverse-order Cloud artifact pair. All four local calls emitted zero observed Cloud HTTP. Every observed engine HTTP request returned 201, all reused connections, no TCP/TLS setup, zero transport errors, zero diagnostic drops. Every call reached the observed quiet checkpoint. Quiet is not Cloud database readback or proof that no other queue could later produce work.

| Flow and channel | Baseline requests / records | Independent requests / records | Declared bytes, baseline → independent |
| --- | ---: | ---: | ---: |
| Native generation, ordinary | 6 / 21 | 4 / 21 | 5760 → 5214 |
| Native generation, payload | 4 / 58 | 5 / 58 | 22247 → 22518 |
| Artifacts, ordinary | 8 / 343 | 20 / 343 | 91139 → 94360 |
| Artifacts, payload | 8 / 1415 | 13 / 1418 | 568108 → 570567 |

Artifact log requests rise 16 → 33 (+106.3%) while log records rise 1758 → 1761 (+0.17%) and declared request bytes rise 659247 → 664927 (+0.86%). The 343 ordinary records are exactly equal by count, spread across 2.5 times as many requests. These counters do not compare record identities or assert full trace equivalence. The nearly unchanged byte/record volume and smaller batches establish observed request fragmentation; one pair cannot establish its stable rate across environments. Generation keeps 79 log records on both sides and 10 → 9 requests, so amplification is workload-dependent.

The shared serial gate disappears as intended. Summed gate waits across all log calls go 907.7 → 0.031 ms in generation and 1661.2 → 0.096 ms in artifact listing. These are overlapping aggregate waits, not time that can be subtracted from CLI duration. Both candidate channels remain individually serial and overlap each other; the baseline log exports never overlap.

| Instrumented flow | CLI baseline → independent | Main engine Cloud flush | Critical flush branch |
| --- | ---: | ---: | --- |
| Native generation | 2844 → 1725 ms | 560 → 185 ms | Baseline ordinary logs; candidate traces |
| Artifacts | 2518 → 3063 ms | 657 → 470 ms | Traces on both sides |

The artifact diagnostic therefore does not reproduce the earlier ordinary Cloud-flush regression. Its candidate callback instead lasts 2015 ms versus 1552 ms, and CLI telemetry shutdown 409 ms versus 160 ms. Five candidate and one baseline metric requests finish after CLI exit; all log/trace requests finish before exit. They drain within the extra observation window, outside the CLI timer. Metrics were already intentionally outside the foreground session flush in both variants.

Disk state materially limits the latency comparison. These retained diagnostic volumes had not previously run the artifact SDK stack: the explicit local artifact primers took 39.06 and 33.43 s. Total sampled engine writes for this diagnostic were 2.296 GB. During the later candidate artifact command, the engine still wrote 245.8 MB and host I/O PSI some increased 1.260 s; the baseline artifact command wrote 0 bytes and PSI increased 0.013 s. Generation also overlapped high I/O pressure. PSI is a host-wide pressure counter, not direct per-command blocked time or proof of a specific storage cause. No forced GC, page-cache reset, or new-volume cold claim applies. These timings are retained for accountability but cannot isolate an exporter latency effect.

All source files, output bytes and original engine binaries were restored; the two verified owned engines are stopped, their volumes retained, and no resources deleted. Four additional authorized Cloud commands bring the cumulative matrix count 202 → 206 of 220. The candidate does not change configured queue capacities or drop policies and introduces no detached exporter. These observations do not establish absence of every possible queue loss: delivery evidence here is successful HTTP plus local lifecycle tests, not stored-record readback.

Disposition: do not upstream the split-writer candidate on these results. A follow-up would need batching/backpressure that remains efficient when the shared gate is removed, plus stable disk conditions and per-flow ordinary comparisons. Do not substitute a larger global timer without direct small-command latency evidence. The existing upstream OTel processor fixes being investigated by the parent are a separate change and may alter the batching/flush behavior; keep attribution separate.
