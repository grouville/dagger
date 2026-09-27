# Fresh-volume follow-up: explicit ancestor metadata

All four commands returned the exact same 14-row `dagger check -l --all` listing. Both newly created containers and volumes were removed; the fixture was unchanged. No Cloud telemetry was enabled.

| Variant | First call on a new volume | Immediate warm repeat | Engine start to ready, excluded |
| --- | ---: | ---: | ---: |
| Baseline | 24.938 s | 1.623 s | 0.264 s |
| Explicit ancestor metadata | 24.568 s | 1.516 s | 0.245 s |

This single baseline-first pair does not demonstrate a general cold-start improvement. The roughly 0.37 s difference is small relative to the approximately 25 s first-call workload, and the order can benefit the candidate through host pages or remote services. The engine image, SDK blobs and generated source fixture were retained; each engine used a newly created Dagger volume and its first Dagger command was the listing. CLI time includes full process exit but excludes engine provisioning/startup. There was no hidden Dagger primer before either first call, no explicit image build/pull during setup, no host page-cache flush and no distributed-cache configuration.

The engine used 87.82 CPU-seconds during baseline cold and 87.97 during candidate cold. The ancestor change therefore does not remove the bulk of this cold workload. These are cumulative engine-cgroup counters, not wall time or an attribution to a specific compiler/process.

| CLI interval | Engine reads | Engine writes | Host Dirty at entry→exit | Host I/O full-pressure delta |
| --- | ---: | ---: | ---: | ---: |
| Baseline cold | 269.6 MiB | 668.1 MiB | 6.4→919.3 MiB | 145.3 ms |
| Baseline warm | 0.1 MiB | 535.1 MiB | 920.1→390.8 MiB | 24.2 ms |
| Candidate cold | 161.1 MiB | 1286.3 MiB | 5.5→300.1 MiB | 194.0 ms |
| Candidate warm | 0.3 MiB | 0 MiB | 300.5→307.1 MiB | 2.5 ms |

The write counters have an important boundary effect: the baseline's immediate warm interval contains 535 MiB of engine-attributed writes while host Dirty falls sharply, whereas the candidate records its writes largely before cold exit. This is consistent with deferred writeback from the preceding cold work. It does not prove the precise producing call of every byte, and it would be wrong to call all 535 MiB warm-listing write amplification. Both warm times can also include different amounts of outstanding cold I/O; their 107.6 ms difference is not a clean isolated saving from the ancestor change.

The NVMe device's mean write await was about 3.10 ms in baseline cold, 5.06 ms in its warm repeat, and 2.00 ms in candidate cold. These are whole-host device counters and include unrelated work. There was no large host I/O-pressure stall comparable to the previously observed multi-second disk contention in this pair. The 4-call result helps explain why interval counters and disk state must be retained; it cannot resolve the historical 27-versus-45-second variability on its own.

The run enforced a 16 GiB free-space floor, a sampled 8 GiB cumulative engine-write guard and a 300 s command timeout. No guard fired. It recorded about 2.43 GiB of engine writes before final stop samples. The guard is not a storage quota; stop-time writeback can follow the last sample. Raw stdout/stderr, fixture source and resource identifiers remain private. The shareable projection contains only fixed variant labels, binary/source/image pins, exact-output hashes, timing/counter summaries and cleanup assertions.
